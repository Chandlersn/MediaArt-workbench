# -*- coding: utf-8 -*-
"""资料提交免登录链接（公开提交入口）。

⚠️ 已暂缓（2026-09-30）：本模块面向「多设备 / 多人协作」场景——生成的链接指向
   `window.location.origin`（本地即 localhost），外部人员无法访问，与项目当前
   「个人本地使用」的定位不符。**代码保留备用，管理端入口已从详情页移除**，
   目前前端无任何页面引用；后端路由与公开接口仍可用（不影响本地功能）。

   若将来要做线上 / 多端协作，恢复方式：把选手、机构详情页的入口按钮加回即可。

管理端（需登录 + 权限）：
    POST   /api/submit-links               生成链接
    GET    /api/submit-links               列表（可按 entityType / entityId 过滤）
    DELETE /api/submit-links/<token>       撤销（软撤销）

公开端（免登录，仅凭 token）：
    GET    /api/public/submit/<token>      查看待交清单与已交状态
    POST   /api/public/submit/<token>      上传一个文件

设计要点：
- **token 由服务端签发**（secrets.token_urlsafe），前端既不生成也不持有；
  `submit_links` 表刻意不纳入 `POST /api/data/save` 的全量快照，避免被前端覆盖。
- **落盘路径由服务端推导**：前端只传「资料类型」，路径由 taxonomy 决定，
  并经 `_safe_under()` 二次校验，杜绝越权写入其他实体目录。
- 因为开了免登录写入口，本模块自带：限流、文件类型白名单、大小上限、过期与撤销。
- **与现有缺料检测天然打通**：文件落到
  `<归档>/<一级分类>/<实体名>/<类型目录>/` 后，`/api/scan-player-files`
  会自动扫到，前端 `calculateMissingMaterials()` 无需任何改动即变绿。
"""

import os
import json
import time
import uuid
import logging
import secrets
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from server.database.store import data_store
from server.archive.taxonomy import SUBDIRS, strip_seq, resolve_subdir_for_type
from server.utils.auth_middleware import extract_user_from_request
from server.utils.permissions import has_permission
from server.resources.routes import (
    _ok, _parse_multipart, _safe_under, _sanitize_filename, _compose_filename,
    get_archives_dir,
)

logger = logging.getLogger(__name__)

# ---------- 常量 ----------

# entity_type -> 归档一级分类（与 materials 路由、taxonomy 保持一致）
_ENTITY_TOP_DIR = {'player': '02_选手档案', 'org': '03_合作机构'}
# entity_type -> 权限模块名
_ENTITY_MODULE = {'player': 'players', 'org': 'organizations'}

DEFAULT_EXPIRES_DAYS = 7
MAX_EXPIRES_DAYS = 365

MAX_FILE_BYTES = 50 * 1024 * 1024  # 单文件 50MB

# 允许上传的扩展名白名单（图片 / 文档 / 音视频 / 压缩包）
ALLOWED_EXTS = {
    # 图片
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'heic', 'tif', 'tiff',
    # 文档
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'csv',
    'rtf', 'odt', 'ods', 'odp',
    # 音频
    'mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'wma',
    # 视频
    'mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'webm', 'm4v',
    # 压缩包
    'zip', 'rar', '7z', 'tar', 'gz',
}

# 限流参数（token 维度 + IP 维度）
_TOKEN_LIMIT = 30      # 每 token 每小时最多 30 次提交
_IP_LIMIT = 120        # 每 IP 每小时最多 120 次请求
_RATE_WINDOW = 3600


# ---------- 限流（进程内滑动窗口，线程安全） ----------

_RL_LOCK = threading.Lock()
_RL_BUCKETS: Dict[str, List[float]] = {}


def _rate_ok(key: str, limit: int, window: int = _RATE_WINDOW) -> bool:
    """滑动窗口限流。返回 True 表示放行。"""
    now = time.time()
    with _RL_LOCK:
        bucket = [t for t in _RL_BUCKETS.get(key, []) if now - t < window]
        if len(bucket) >= limit:
            _RL_BUCKETS[key] = bucket
            return False
        bucket.append(now)
        _RL_BUCKETS[key] = bucket
        # 顺手清理过大的表，避免长期运行内存增长
        if len(_RL_BUCKETS) > 5000:
            for k in [k for k, v in _RL_BUCKETS.items() if not v or now - v[-1] > window]:
                _RL_BUCKETS.pop(k, None)
        return True


# ---------- 小工具 ----------

def _client_ip(request_context: Dict[str, Any]) -> str:
    addr = request_context.get('client_address')
    if isinstance(addr, (tuple, list)) and addr:
        return str(addr[0])
    return ''


def _qp(request_context: Dict[str, Any], key: str, default: str = '') -> str:
    qp = request_context.get('query_params', {}) or {}
    val = qp.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


def _json_body(request_context: Dict[str, Any]) -> Any:
    body = request_context.get('body', b'') or b''
    if isinstance(body, (bytes, bytearray)):
        if not body:
            return {}
        try:
            return json.loads(body.decode('utf-8'))
        except Exception:
            return None
    if isinstance(body, (dict, list)):
        return body
    return None


def _auth(request_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    user = extract_user_from_request(request_context)
    if not user:
        return _ok({'success': False, 'message': '认证失败，Token 无效或缺失',
                    'error': 'UNAUTHORIZED'}, 401)
    request_context['user'] = user
    return None


def _perm_any(request_context: Dict[str, Any],
              pairs: List[Tuple[str, str]]) -> Optional[Dict[str, Any]]:
    """任一 (module, action) 命中即放行。"""
    user = request_context.get('user', {}) or {}
    role = user.get('role', 'viewer')
    if any(has_permission(role, m, a) for m, a in pairs):
        return None
    desc = ' 或 '.join(f'{m}:{a}' for m, a in pairs)
    return _ok({'success': False, 'message': f'权限不足，需要 {desc} 权限',
                'error': 'FORBIDDEN'}, 403)


def _loads(value: Any) -> Optional[List[str]]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else None
        except Exception:
            return None
    return None


def _parse_expiry(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace('Z', '')
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _now_text() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ---------- 表访问 ----------

_table_ready = False


def _ensure_table() -> None:
    """兜底建表。

    schema.sql 在每次启动时执行，正常无需走到这里；此处仅防御「进程内新增表」
    或旧库未重启的场景。DDL 必须走 transaction() 才会落库。
    """
    global _table_ready
    if _table_ready:
        return
    try:
        with data_store.db.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS submit_links (
                    token          TEXT PRIMARY KEY,
                    entity_type    TEXT NOT NULL,
                    entity_id      TEXT NOT NULL,
                    entity_name    TEXT NOT NULL,
                    stage          TEXT,
                    required_types TEXT,
                    expires_at     TEXT,
                    max_uses       INTEGER DEFAULT 0,
                    used_count     INTEGER DEFAULT 0,
                    revoked        INTEGER DEFAULT 0,
                    created_by     TEXT,
                    created_at     TEXT,
                    updated_at     TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_submit_links_entity "
                "ON submit_links(entity_type, entity_id)"
            )
        _table_ready = True
    except Exception as e:
        logger.error(f"创建 submit_links 表失败: {e}", exc_info=True)


def _find_link(token: str) -> Optional[Dict[str, Any]]:
    _ensure_table()
    return data_store.db.fetchone("SELECT * FROM submit_links WHERE token = ?", (token,))


def _list_links(entity_type: str = '', entity_id: str = '') -> List[Dict[str, Any]]:
    _ensure_table()
    where, params = [], []
    if entity_type:
        where.append("entity_type = ?")
        params.append(entity_type)
    if entity_id:
        where.append("entity_id = ?")
        params.append(entity_id)
    sql = "SELECT * FROM submit_links"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    return data_store.db.fetchall(sql, tuple(params))


def _link_to_api(row: Dict[str, Any]) -> Dict[str, Any]:
    """DB 行 → 管理端展示结构（驼峰 + path）。"""
    token = row.get('token') or ''
    expires_at = row.get('expires_at') or ''
    exp = _parse_expiry(expires_at)
    return {
        'token': token,
        'entityType': row.get('entity_type') or '',
        'entityId': row.get('entity_id') or '',
        'entityName': row.get('entity_name') or '',
        'stage': row.get('stage') or '',
        'requiredTypes': _loads(row.get('required_types')) or [],
        'expiresAt': expires_at,
        'expired': bool(exp and datetime.now() > exp),
        'maxUses': row.get('max_uses') or 0,
        'usedCount': row.get('used_count') or 0,
        'revoked': bool(row.get('revoked')),
        'createdBy': row.get('created_by') or '',
        'createdAt': row.get('created_at') or '',
        'path': f'/#/submit/{token}',
    }


def _bump_used(token: str) -> None:
    with data_store.db.transaction() as conn:
        conn.execute(
            "UPDATE submit_links SET used_count = COALESCE(used_count, 0) + 1, "
            "updated_at = ? WHERE token = ?",
            (_now_text(), token),
        )


def _write_audit(entity_type: str, entity: Dict[str, Any], material_type: str,
                 filename: str, ip: str) -> None:
    """服务端直接写审计日志（不依赖前端 payload，可信）。"""
    try:
        with data_store.db.transaction() as conn:
            conn.execute(
                "INSERT INTO audit_logs (id, user_id, username, action, resource_type, "
                "resource_id, details, ip_address, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    '',
                    entity.get('name') or '外部提交',
                    '资料提交',
                    'submit',
                    entity.get('id') or '',
                    json.dumps({
                        'entityType': entity_type,
                        'entityName': entity.get('name') or '',
                        'materialType': material_type,
                        'fileName': filename,
                        'source': 'public-submit-link',
                    }, ensure_ascii=False),
                    ip,
                    _now_text(),
                ),
            )
    except Exception as e:
        logger.warning(f"写提交审计日志失败（不影响提交）: {e}")


# ---------- 实体与资料要求 ----------

def _resolve_entity(entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
    """按 id 取实体（取实时数据，实体改名后仍能正确定位）。"""
    if entity_type == 'player':
        row = data_store.players.get_by_id(entity_id)
        if not row:
            return None
        return {'id': entity_id, 'name': row.get('name') or '',
                'stage': row.get('stage') or '', 'orgId': row.get('orgId') or ''}
    if entity_type == 'org':
        row = data_store.organizations.get_by_id(entity_id)
        if not row:
            return None
        return {'id': entity_id, 'name': row.get('name') or '',
                'stage': '', 'orgId': ''}
    return None


def _required_types(entity_type: str, entity: Dict[str, Any]) -> List[str]:
    """推导「本次应提交哪些资料」。

    选手：读现有 `config.stageMaterials[赛段]`（与缺料检测同口径，含 orgId 适用性过滤）。
    机构：取归档分类 `03_合作机构` 的规范三级目录名（去序号）。
    全部由服务端推导，不接受前端传入，避免构造出与配置不一致的要求清单。
    """
    if entity_type == 'player':
        cfg = {}
        try:
            cfg = data_store._load_config() or {}
        except Exception as e:
            logger.warning(f"读取 config 失败: {e}")
        stage_materials = cfg.get('stageMaterials') or {}
        names = stage_materials.get(entity.get('stage') or '') or []
        if not names:
            return []
        try:
            mts = data_store.material_types.get_all() or []
        except Exception:
            mts = []
        by_name = {m.get('name'): m for m in mts}
        out: List[str] = []
        for name in names:
            mt = by_name.get(name)
            # 与 calculateMissingMaterials 同口径：资料类型绑定了机构时只对该机构选手生效
            if mt and mt.get('orgId') and mt.get('orgId') != entity.get('orgId'):
                continue
            out.append(name)
        return out

    if entity_type == 'org':
        return [strip_seq(s) for s in SUBDIRS.get('03_合作机构', ())]

    return []


def _uploaded_types(entity_type: str, name: str) -> set:
    """扫描归档，返回该实体已提交的资料类型集合。

    直接复用 MaterialsRouter.scan()，保证与前端缺料检测看到的结果**完全一致**。
    """
    if not name:
        return set()
    try:
        from server.materials.routes import MaterialsRouter
        kind = 'player' if entity_type == 'player' else 'org'
        resp = MaterialsRouter().scan(kind, {'query_params': {'name': [name]}})
        body = resp.get('body') or {}
        return {m.get('type') for m in (body.get('materials') or []) if m.get('type')}
    except Exception as e:
        logger.warning(f"扫描已提交资料失败（按未提交处理）: {e}")
        return set()


def _type_icon(name: str) -> str:
    """资料类型 → 图标（取配置，取不到给默认）。"""
    try:
        for mt in (data_store.material_types.get_all() or []):
            if mt.get('name') == name:
                return mt.get('icon') or '📄'
    except Exception:
        pass
    return '📄'


def _target_dir(entity_type: str, entity_name: str, material_type: str) -> Optional[str]:
    """推导落盘目录：<归档>/<一级分类>/<实体名>/<类型目录>/"""
    top = _ENTITY_TOP_DIR.get(entity_type)
    if not top or not entity_name:
        return None
    sub = resolve_subdir_for_type(top, material_type)
    return _safe_under(get_archives_dir(), top, entity_name, sub)


def _validate_link(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """校验 token 可用性；返回错误响应或 None。"""
    if not row:
        return _ok({'success': False, 'message': '链接无效或已被删除'}, 404)
    if row.get('revoked'):
        return _ok({'success': False, 'message': '该链接已被撤销，请联系主办方'}, 403)
    exp = _parse_expiry(row.get('expires_at'))
    if exp and datetime.now() > exp:
        return _ok({'success': False, 'message': '该链接已过期，请联系主办方重新获取'}, 403)
    max_uses = row.get('max_uses') or 0
    if max_uses and (row.get('used_count') or 0) >= max_uses:
        return _ok({'success': False, 'message': '该链接的使用次数已达上限'}, 403)
    return None


# ---------- 路由 ----------

class SubmitRouter:
    """Router for public material submission links."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')
        norm = path.split('?')[0]

        try:
            # ---------- 公开端（免登录，仅凭 token） ----------
            if norm.startswith('/api/public/submit/'):
                token = norm[len('/api/public/submit/'):].strip('/')
                if not token:
                    return _ok({'success': False, 'message': '缺少 token'}, 400)
                if method == 'GET':
                    return self.public_info(token, request_context)
                if method == 'POST':
                    return self.public_upload(token, request_context)
                return _ok({'success': False, 'message': f'不支持的方法: {method}'}, 405)

            # ---------- 管理端（需登录） ----------
            if norm == '/api/submit-links':
                if (a := _auth(request_context)):
                    return a
                if method == 'POST':
                    return self.create_link(request_context)
                if method == 'GET':
                    if (p := _perm_any(request_context,
                                      [('players', 'view'), ('organizations', 'view')])):
                        return p
                    return self.list_links(request_context)
                return _ok({'success': False, 'message': f'不支持的方法: {method}'}, 405)

            if norm.startswith('/api/submit-links/'):
                if (a := _auth(request_context)):
                    return a
                token = norm[len('/api/submit-links/'):].strip('/')
                if method == 'DELETE':
                    return self.revoke_link(token, request_context)
                return _ok({'success': False, 'message': f'不支持的方法: {method}'}, 405)

            return _ok({'success': False, 'message': f'未处理的提交接口: {method} {norm}'}, 404)

        except Exception as e:
            logger.error(f"处理提交请求失败 {method} {norm}: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'服务器内部错误: {e}'}, 500)

    # ---------- 管理端 ----------

    def create_link(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        payload = _json_body(request_context)
        if not isinstance(payload, dict):
            return _ok({'success': False, 'message': '请求体必须是 JSON 对象'}, 400)

        entity_type = (payload.get('entityType') or '').strip()
        entity_id = (payload.get('entityId') or '').strip()
        if entity_type not in _ENTITY_TOP_DIR:
            return _ok({'success': False, 'message': "entityType 必须是 'player' 或 'org'"}, 400)
        if not entity_id:
            return _ok({'success': False, 'message': '缺少 entityId'}, 400)

        # 按实体类型校验权限（选手用 players:edit，机构用 organizations:edit）
        if (p := _perm_any(request_context,
                           [(_ENTITY_MODULE[entity_type], 'edit')])):
            return p

        entity = _resolve_entity(entity_type, entity_id)
        if not entity:
            return _ok({'success': False, 'message': '选手 / 机构不存在'}, 404)
        if not (entity.get('name') or '').strip():
            return _ok({'success': False, 'message': '该实体没有名称，无法生成目录'}, 400)

        try:
            days = int(payload.get('expiresInDays', DEFAULT_EXPIRES_DAYS))
        except (TypeError, ValueError):
            days = DEFAULT_EXPIRES_DAYS
        days = max(1, min(days, MAX_EXPIRES_DAYS))

        required = _required_types(entity_type, entity)
        if not required:
            return _ok({'success': False,
                        'message': '该实体当前没有配置需要提交的资料类型，请先在「资料配置」中设置'}, 400)

        token = secrets.token_urlsafe(32)
        now = datetime.now()
        user = request_context.get('user', {}) or {}
        _ensure_table()
        try:
            with data_store.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO submit_links (token, entity_type, entity_id, entity_name, "
                    "stage, required_types, expires_at, max_uses, used_count, revoked, "
                    "created_by, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        token, entity_type, entity_id, entity.get('name') or '',
                        entity.get('stage') or '',
                        json.dumps(required, ensure_ascii=False),
                        (now + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S'),
                        0, 0, 0,
                        user.get('user_id', ''),
                        now.strftime('%Y-%m-%d %H:%M:%S'),
                        now.strftime('%Y-%m-%d %H:%M:%S'),
                    ),
                )
        except Exception as e:
            logger.error(f"生成提交链接失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'生成失败: {e}'}, 500)

        row = _find_link(token)
        return _ok({'success': True, 'message': '链接已生成',
                    'link': _link_to_api(row) if row else {'token': token}})

    def list_links(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        entity_type = _qp(request_context, 'entityType', '')
        entity_id = _qp(request_context, 'entityId', '')
        rows = _list_links(entity_type, entity_id)
        return _ok({'success': True, 'links': [_link_to_api(r) for r in rows]})

    def revoke_link(self, token: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        row = _find_link(token)
        if not row:
            return _ok({'success': False, 'message': '链接不存在'}, 404)
        module = _ENTITY_MODULE.get(row.get('entity_type') or '', 'players')
        if (p := _perm_any(request_context, [(module, 'edit')])):
            return p
        try:
            with data_store.db.transaction() as conn:
                conn.execute(
                    "UPDATE submit_links SET revoked = 1, updated_at = ? WHERE token = ?",
                    (_now_text(), token),
                )
        except Exception as e:
            return _ok({'success': False, 'message': f'撤销失败: {e}'}, 500)
        return _ok({'success': True, 'message': '链接已撤销'})

    # ---------- 公开端 ----------

    def public_info(self, token: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        ip = _client_ip(request_context)
        if not _rate_ok(f'ip:{ip}', _IP_LIMIT):
            return _ok({'success': False, 'message': '请求过于频繁，请稍后再试'}, 429)

        row = _find_link(token)
        if (err := _validate_link(row)):
            return err

        entity_type = row.get('entity_type') or ''
        entity = _resolve_entity(entity_type, row.get('entity_id') or '')
        if not entity:
            return _ok({'success': False, 'message': '对应的选手 / 机构已不存在'}, 404)

        required = _loads(row.get('required_types')) or _required_types(entity_type, entity)
        uploaded = _uploaded_types(entity_type, entity.get('name') or '')
        items = [{'name': name, 'icon': _type_icon(name), 'done': name in uploaded}
                 for name in required]

        return _ok({
            'success': True,
            'entityType': entity_type,
            'entityName': entity.get('name') or '',
            'stage': entity.get('stage') or '',
            'expiresAt': row.get('expires_at') or '',
            'items': items,
        })

    def public_upload(self, token: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        ip = _client_ip(request_context)
        if not _rate_ok(f'ip:{ip}', _IP_LIMIT):
            return _ok({'success': False, 'message': '请求过于频繁，请稍后再试'}, 429)
        if not _rate_ok(f'tok:{token}', _TOKEN_LIMIT):
            return _ok({'success': False, 'message': '该链接提交过于频繁，请稍后再试'}, 429)

        row = _find_link(token)
        if (err := _validate_link(row)):
            return err

        headers = request_context.get('headers', {}) or {}
        content_type = headers.get('Content-Type', headers.get('content-type', ''))
        if 'multipart/form-data' not in (content_type or ''):
            return _ok({'success': False, 'message': 'Content-Type 必须是 multipart/form-data'}, 400)

        body = request_context.get('body', b'') or b''
        fields, raw_name, file_data = _parse_multipart(body, content_type)
        if not file_data or not raw_name:
            return _ok({'success': False, 'message': '未收到文件'}, 400)

        if len(file_data) > MAX_FILE_BYTES:
            return _ok({'success': False,
                        'message': f'文件超过上限（{MAX_FILE_BYTES // 1024 // 1024}MB）'}, 413)

        ext = os.path.splitext(raw_name)[1].lower().lstrip('.')
        if ext not in ALLOWED_EXTS:
            return _ok({'success': False, 'message': f'不支持的文件类型: .{ext or "未知"}'}, 400)

        entity_type = row.get('entity_type') or ''
        entity = _resolve_entity(entity_type, row.get('entity_id') or '')
        if not entity:
            return _ok({'success': False, 'message': '对应的选手 / 机构已不存在'}, 404)

        material_type = (fields.get('materialType') or '').strip()
        required = _loads(row.get('required_types')) or _required_types(entity_type, entity)
        if material_type not in required:
            return _ok({'success': False,
                        'message': f'资料类型不在本次要求范围内: {material_type or "（空）"}'}, 400)

        dest = _target_dir(entity_type, entity.get('name') or '', material_type)
        if not dest:
            return _ok({'success': False, 'message': '目标路径越界或实体名非法'}, 400)

        filename = _compose_filename(
            raw_name, title=material_type,
            subject=entity.get('name') or '', stage=entity.get('stage') or '')

        try:
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(dest, filename), 'wb') as f:
                f.write(file_data)
        except Exception as e:
            logger.error(f"写入提交文件失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'保存文件失败: {e}'}, 500)

        _bump_used(token)
        _write_audit(entity_type, entity, material_type, filename, ip)

        return _ok({'success': True, 'message': '提交成功',
                    'fileName': filename, 'materialType': material_type})
