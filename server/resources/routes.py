# -*- coding: utf-8 -*-
"""Resources API routes module（资源中心 + 数据全量读写 + 备份恢复 + 同步 + 文件上下行）。

本模块是模块化后端里「数据与文件」的中枢，`server/api/router.py` 把下列路径全部指向它：

    数据管理
      GET    /api/data/load              全量数据读取
      POST   /api/data/save              全量数据落库（系统唯一写路径）
      POST   /api/data/backup            用当前数据创建备份
      GET    /api/data/list-backups      备份列表
      POST   /api/data/restore           从备份恢复
      GET    /api/data/sync/status       旧 JSON ↔ SQLite 同步状态
      POST   /api/data/sync/import       JSON → SQLite 迁移
      POST   /api/data/sync/export       SQLite → JSON 导出

    文件管理
      GET    /api/list-files?folder=     素材库文件列表
      POST   /api/upload                 文件上传（素材库 / 归档 / 模板 / 项目·选手·机构资料）
      GET    /api/get-file?path=         文件下载（二进制）
      DELETE /api/delete-file?path=      删除文件（进回收站）
      POST   /api/open-resource          用系统默认程序打开素材
      POST   /api/open-folder            打开本地文件夹

除路由外，本模块还对外导出四个共享符号，被其他模块复用（不要改名，否则会断链）：

    RESOURCES_DIR            素材库根目录（导入时按 config.json 解析一次）
    get_resources_dir()      同上，函数式读取（便于运行期取用）
    get_archives_dir()       归档根目录：config.json 的 archivePath，否则 MediaArt_Archives/
    _sanitize_filename()     清洗单个文件/目录名（archive 重命名用）
    _content_disposition()   构造带 UTF-8 文件名的响应头（materials 下载用）
    _resolve_material_path() 相对路径 → 绝对路径（归档优先，system 文本预览用）

⚠️ 本模块曾在仓库中长期缺失：`.gitignore` 里 `resources/` 少了前导斜杠，把
   `server/resources/` 一并忽略，导致该目录从未被提交。修复方式是把规则锚定成
   `/resources/`（只匹配仓库根目录的同名素材夹）。
"""

import os
import re
import json
import uuid
import logging
import mimetypes
import platform
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, quote

from server.config import BASE_DIR
from server.database.store import data_store
from server.archive.taxonomy import ARCHIVE_TOP_DIRS, resolve_subdir_for_type
from server.utils.auth_middleware import extract_user_from_request
from server.utils.permissions import has_permission
from server.utils.trash import send_to_trash

logger = logging.getLogger(__name__)

JSON_HEADERS = {'Content-Type': 'application/json'}

# ---------- 目录常量 ----------
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_JSON = os.path.join(DATA_DIR, 'config.json')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')
LEGACY_JSON = os.path.join(DATA_DIR, 'workbench_data.json')

DEFAULT_RESOURCES_DIR = os.path.join(BASE_DIR, 'resources')
DEFAULT_ARCHIVE_DIR = os.path.join(BASE_DIR, 'MediaArt_Archives')

# kind -> 归档一级分类（与 materials 路由、taxonomy 保持一致）
_ENTITY_TOP_DIR = {
    'project': '01_项目资料',
    'player': '02_选手档案',
    'org': '03_合作机构',
}

# 备份目录名形如 2026-09-29_20-15-30，也兼容 migration_ 前缀
_BACKUP_NAME_RE = re.compile(r'^(?:\w+_)?(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})(?:-(\d{2}))?$')


# ==================== 响应与取值小工具 ====================

def _ok(body: Any, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    h = dict(JSON_HEADERS)
    if headers:
        h.update(headers)
    return {'status': status, 'body': body, 'headers': h}


def _qp(request_context: Dict[str, Any], key: str, default: str = '') -> str:
    qp = request_context.get('query_params', {}) or {}
    val = qp.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


def _json_body(request_context: Dict[str, Any]) -> Any:
    """解析 JSON 请求体；无法解析返回 None（调用方据此返回 400）。"""
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


def _perm(request_context: Dict[str, Any], module: str, action: str) -> Optional[Dict[str, Any]]:
    user = request_context.get('user', {}) or {}
    if not has_permission(user.get('role', 'viewer'), module, action):
        return _ok({'success': False, 'message': f'权限不足，需要 {module}:{action} 权限',
                    'error': 'FORBIDDEN'}, 403)
    return None


# ==================== 路径与文件名工具（对外导出） ====================

def _sanitize_filename(name: str) -> str:
    """清洗单个文件 / 目录名：去路径分隔、非法字符与穿越片段。

    只保留最后一段，因此对 ``../../etc/passwd`` 这类输入返回 ``passwd``。
    """
    name = unquote(name or '')
    name = name.replace('\\', '/').split('/')[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', '_', name)
    name = name.replace('..', '').strip().strip('.')
    return name


def _safe_component(value: str) -> str:
    """清洗单层路径名，杜绝穿越（与 materials 路由同口径）。"""
    value = (value or '').replace('\\', '/').strip().strip('/')
    value = value.split('/')[-1]
    return value.replace('..', '').strip()


def _safe_rel(rel: str) -> Optional[str]:
    """把相对路径归一化为 '/' 分隔且不含穿越的字符串；非法返回 None。"""
    rel = unquote(rel or '').replace('\\', '/').strip().strip('/')
    if not rel:
        return ''
    parts: List[str] = []
    for seg in rel.split('/'):
        seg = seg.strip()
        if not seg or seg == '.':
            continue
        if seg == '..':
            return None
        parts.append(seg)
    return '/'.join(parts)


def _safe_under(base: str, *parts: str) -> Optional[str]:
    """在 ``base`` 下安全拼接若干层目录，越界返回 None。"""
    base = os.path.abspath(base)
    comps = [_safe_component(p) for p in parts if p]
    target = os.path.abspath(os.path.join(base, *comps))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _content_disposition(disposition: str, filename: str) -> str:
    """构造带 UTF-8 文件名的 Content-Disposition（RFC 5987）。

    ``send_header`` 以 latin-1 编码发送，中文名会抛 UnicodeEncodeError 并打成 500，
    因此 ASCII 回退名 + ``filename*=UTF-8''`` 双写。
    """
    filename = filename or 'download'
    ascii_name = filename.encode('ascii', 'ignore').decode('ascii').strip() or 'download'
    ascii_name = ascii_name.replace('"', '').replace('\\', '')
    # 纯中文文件名去掉非 ASCII 后可能只剩扩展名（"测试.pdf" → ".pdf"），
    # 此时补一个可读的主干，避免出现 filename=".pdf" 这种畸形回退名。
    if ascii_name.startswith('.'):
        ascii_name = 'download' + ascii_name
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


# ==================== 目录解析（对外导出） ====================

def _load_config_json() -> Dict[str, Any]:
    """读取 BASE/data/config.json（与 system 路由共用同一份配置）。"""
    try:
        if os.path.exists(CONFIG_JSON):
            with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
                return json.load(f) or {}
    except Exception as e:
        logger.warning(f"读取 config.json 失败: {e}")
    return {}


def _configured_dir(key: str, default: str) -> str:
    """取配置里的目录；为空则退回默认值。相对路径按仓库根解析。"""
    value = (_load_config_json().get(key) or '').strip()
    if not value:
        return default
    if not os.path.isabs(value):
        value = os.path.join(BASE_DIR, value)
    return os.path.normpath(value)


def get_resources_dir() -> str:
    """素材库根目录：config.json 的 resourcesPath，否则 BASE/resources。"""
    return _configured_dir('resourcesPath', DEFAULT_RESOURCES_DIR)


def get_archives_dir() -> str:
    """归档根目录：config.json 的 archivePath，否则 BASE/MediaArt_Archives。"""
    return _configured_dir('archivePath', DEFAULT_ARCHIVE_DIR)


# 导入期解析一次。后端不做热重载（见 README），改配置后重启即可生效；
# 这与 archive/routes.py 的 ARCHIVE_DIR 取法保持一致。
RESOURCES_DIR = get_resources_dir()


def _resolve_material_path(rel: str) -> Optional[str]:
    """相对路径 → 绝对路径（归档优先，其次素材库）。

    判定顺序：
      1. 以归档一级分类名开头（01_项目资料/…）→ 直接落在归档目录下
      2. 在归档目录下确实存在 → 归档
      3. 否则 → 素材库目录下（templates/… 等尚未存在的路径也走这里）
    """
    norm = _safe_rel(rel)
    if norm is None:
        return None
    arch = get_archives_dir()
    res = get_resources_dir()
    if not norm:
        return res
    segments = norm.split('/')
    if segments[0] in ARCHIVE_TOP_DIRS:
        return os.path.join(arch, *segments)
    cand_arch = os.path.join(arch, *segments)
    if os.path.exists(cand_arch):
        return cand_arch
    return os.path.join(res, *segments)


# ==================== multipart 解析 ====================

def _parse_multipart(body: bytes, content_type: str) -> Tuple[Dict[str, str], Optional[str], Optional[bytes]]:
    """极简 multipart/form-data 解析（纯标准库，零依赖）。

    返回 ``(文本字段字典, 文件名, 文件内容)``；非 multipart 或解析失败返回空。
    """
    if 'multipart/form-data' not in (content_type or ''):
        return {}, None, None

    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part[len('boundary='):].strip().strip('"')
            break
    if not boundary:
        return {}, None, None

    delim = b'--' + boundary.encode('utf-8')
    fields: Dict[str, str] = {}
    filename: Optional[str] = None
    content: Optional[bytes] = None

    for chunk in body.split(delim):
        if not chunk or chunk.strip() in (b'', b'--'):
            continue
        if b'\r\n\r\n' not in chunk:
            continue
        raw_headers, payload = chunk.split(b'\r\n\r\n', 1)
        if payload.endswith(b'\r\n'):
            payload = payload[:-2]
        header_str = raw_headers.decode('utf-8', errors='replace')
        name_match = re.search(r'name="([^"]*)"', header_str)
        if not name_match:
            continue
        field = name_match.group(1)
        file_match = re.search(r'filename="([^"]*)"', header_str)
        if file_match is not None:
            # 浏览器即使未选文件也会带 filename=""，此时视为无文件
            filename = unquote(file_match.group(1))
            content = payload
        else:
            fields[field] = payload.decode('utf-8', errors='replace')

    return fields, filename, content


def _compose_filename(original: str, title: str = '', subject: str = '', stage: str = '') -> str:
    """按约定拼出落盘文件名。

    选手资料约定为 ``{主体}_{赛段}__{标题}.ext``——materials 的 scan() 依赖
    ``__`` 之前那段来还原赛段，用于详情页「按赛段分组」。
    """
    safe_original = _sanitize_filename(original) or f"upload_{uuid.uuid4().hex[:8]}"
    base, ext = os.path.splitext(safe_original)
    base = _sanitize_filename(title) or base
    subject = _sanitize_filename(subject)
    stage = _sanitize_filename(stage)
    if subject and stage:
        return f"{subject}_{stage}__{base}{ext}"
    if subject:
        return f"{subject}__{base}{ext}"
    return f"{base}{ext}"


def _split_backup_name(name: str) -> Tuple[str, str]:
    """把备份目录名拆成 (日期, 时间)，无法识别返回 ('', '')。"""
    m = _BACKUP_NAME_RE.match(name or '')
    if not m:
        return '', ''
    date, hh, mm, ss = m.groups()
    return date, f"{hh}:{mm}:{ss or '00'}"


def _open_in_os(path: str) -> bool:
    """用系统默认程序打开路径；无头环境失败也返回 False 而不抛异常。"""
    try:
        system = platform.system()
        if system == 'Windows':
            os.startfile(path)  # noqa: 仅 Windows 存在
        elif system == 'Darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return True
    except Exception as e:
        logger.warning(f"打开路径失败（可忽略）: {e}")
        return False


# ==================== 路由 ====================

class ResourcesRouter:
    """Router for data load/save/backup and resource file endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')
        norm = path.split('?')[0]

        try:
            # ---------- 数据管理 ----------
            if norm == '/api/data/load' and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                return self.load_data()

            if norm == '/api/data/save' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'edit')):
                    return p
                return self.save_data(request_context)

            if norm == '/api/data/backup' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'edit')):
                    return p
                return self.backup(request_context)

            if norm == '/api/data/list-backups' and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                return self.list_backups()

            if norm == '/api/data/restore' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                # 恢复会覆盖全库，按规范要求 admin（只有 admin 有 settings:edit）
                if (p := _perm(request_context, 'settings', 'edit')):
                    return p
                return self.restore(request_context)

            if norm == '/api/data/delete-backup' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                # 与「恢复备份」同为系统管理动作，要求 admin
                if (p := _perm(request_context, 'settings', 'edit')):
                    return p
                return self.delete_backup(request_context)

            if norm == '/api/data/sync/status' and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                return self.sync_status()

            if norm == '/api/data/sync/import' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'settings', 'edit')):
                    return p
                return self.sync_import()

            if norm == '/api/data/sync/export' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'settings', 'edit')):
                    return p
                return self.sync_export()

            # ---------- 文件管理 ----------
            if norm in ('/api/list-files', '/api/resources') and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'view')):
                    return p
                return self.list_files(request_context)

            if norm == '/api/upload' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'edit')):
                    return p
                return self.upload(request_context)

            if norm == '/api/get-file' and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'view')):
                    return p
                return self.get_file(request_context)

            if norm == '/api/delete-file' and method == 'DELETE':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'delete')):
                    return p
                return self.delete_file(request_context)

            if norm == '/api/open-resource' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'view')):
                    return p
                return self.open_resource(request_context)

            if norm == '/api/open-folder' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'resources', 'view')):
                    return p
                return self.open_folder(request_context)

            return _ok({'success': False, 'error': 'Not Found',
                        'message': f'未处理的资源接口: {method} {norm}'}, 404)

        except Exception as e:
            logger.error(f"处理资源请求失败 {method} {norm}: {e}", exc_info=True)
            return _ok({'success': False, 'error': 'Internal Server Error',
                        'message': str(e)}, 500)

    # ---------- 数据管理 ----------

    def load_data(self) -> Dict[str, Any]:
        """全量读取。前端 dataService.load() 取 res.data。"""
        data = data_store.load_all_data()
        return _ok({'success': True, 'data': data, 'exists': True})

    def save_data(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """全量落库（系统唯一写路径）。"""
        payload = _json_body(request_context)
        if not isinstance(payload, dict):
            return _ok({'success': False, 'message': '请求体必须是 JSON 对象'}, 400)
        if data_store.save_all_data(payload):
            return _ok({'success': True, 'message': '数据保存成功'})
        return _ok({'success': False, 'message': '部分数据未能写入，请查看服务端日志'}, 500)

    def backup(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """用请求体里的数据创建一份备份目录 data/backup/<时间戳>/。"""
        payload = _json_body(request_context)
        if not isinstance(payload, dict):
            return _ok({'success': False, 'message': '请求体必须是 JSON 对象'}, 400)

        name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        target = os.path.join(BACKUP_DIR, name)
        try:
            os.makedirs(target, exist_ok=True)
            with open(os.path.join(target, 'workbench_data.json'), 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"创建备份失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'创建备份失败: {e}'}, 500)

        # 顺手轮转，避免手动备份无限增长（与启动期维护同一套规则）
        try:
            from server.database.maintenance import rotate_backups
            rotate_backups(BACKUP_DIR, keep=20)
        except Exception as e:
            logger.warning(f"备份轮转跳过: {e}")

        return _ok({'success': True, 'message': '备份创建成功', 'backup_name': name})

    def list_backups(self) -> Dict[str, Any]:
        """列出 data/backup 下的备份目录。"""
        backups: List[Dict[str, Any]] = []
        if os.path.isdir(BACKUP_DIR):
            try:
                names = sorted(os.listdir(BACKUP_DIR), reverse=True)
            except OSError as e:
                logger.warning(f"读取备份目录失败: {e}")
                names = []
            for name in names:
                path = os.path.join(BACKUP_DIR, name)
                if not os.path.isdir(path):
                    continue
                has_json = os.path.isfile(os.path.join(path, 'workbench_data.json'))
                has_db = os.path.isfile(os.path.join(path, 'workbench.db'))
                date, time_str = _split_backup_name(name)
                backups.append({
                    'name': name,
                    'date': date,
                    'time': time_str,
                    'has_data': has_json or has_db,
                })
        return _ok({'success': True, 'backups': backups})

    def restore(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """从备份恢复。

        只把备份内容**读出来返回**，不直接写库——前端拿到 data 后会
        合并进内存快照再走 /api/data/save，避免两套写路径并存。
        仅当备份里只有 workbench.db（无 JSON）时才走文件级回滚。
        """
        payload = _json_body(request_context)
        raw_name = (payload or {}).get('backup_name', '') if isinstance(payload, dict) else ''
        name = _sanitize_filename(raw_name)
        if not name:
            return _ok({'success': False, 'message': '缺少备份名称'}, 400)

        backup_path = os.path.join(BACKUP_DIR, name)
        if not os.path.isdir(backup_path):
            return _ok({'success': False, 'message': f'备份不存在: {name}'}, 404)

        json_path = os.path.join(backup_path, 'workbench_data.json')
        if os.path.isfile(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                return _ok({'success': False, 'message': f'备份文件损坏: {e}'}, 500)
            return _ok({'success': True, 'message': '备份恢复成功', 'data': data})

        if os.path.isfile(os.path.join(backup_path, 'workbench.db')):
            try:
                from server.database.migrate import DataMigrator
                if DataMigrator().rollback_from_backup(name):
                    return _ok({'success': True, 'message': '备份恢复成功',
                                'data': data_store.load_all_data()})
            except Exception as e:
                logger.error(f"数据库备份回滚失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': '恢复数据库备份失败'}, 500)

        return _ok({'success': False, 'message': '备份中没有任何数据文件'}, 404)

    def delete_backup(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """删除一份备份。

        备份目录在 data/backup/ 下，属于用户数据；删除走回收站（`send_to_trash`），
        误删可从回收站恢复 —— 与项目里其他删除行为保持一致。
        仅允许删除 backup 目录的**直接子项**，杜绝借备份名做路径穿越。
        """
        payload = _json_body(request_context)
        raw_name = (payload or {}).get('name', '') if isinstance(payload, dict) else ''
        name = _sanitize_filename(raw_name)
        if not name:
            return _ok({'success': False, 'message': '缺少备份名称'}, 400)

        backup_root = os.path.abspath(BACKUP_DIR)
        target = os.path.abspath(os.path.join(backup_root, name))
        # 必须是 backup 目录的直接子项（父目录正好是 backup_root）
        if os.path.dirname(target) != backup_root or not os.path.isdir(target):
            return _ok({'success': False, 'message': f'备份不存在: {name}'}, 404)

        try:
            if send_to_trash(target):
                return _ok({'success': True, 'message': '备份已删除，可在回收站中恢复'})
            return _ok({'success': False, 'message': '删除失败'}, 500)
        except Exception as e:
            logger.error(f"删除备份失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'删除失败: {e}'}, 500)

    # ---------- 旧 JSON ↔ SQLite 同步 ----------

    def sync_status(self) -> Dict[str, Any]:
        from server.database.migrate import DataMigrator
        try:
            status = DataMigrator().get_migration_status()
        except Exception as e:
            logger.error(f"读取同步状态失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': str(e)}, 500)
        return _ok({'success': True, 'status': status})

    def sync_import(self) -> Dict[str, Any]:
        """把遗留 JSON 数据导入 SQLite（会先自动备份）。"""
        from server.database.migrate import DataMigrator, JSON_FILE
        migrator = DataMigrator()
        if not migrator.check_json_exists():
            return _ok({'success': False, 'message': f'未找到 JSON 数据文件: {JSON_FILE}'}, 404)
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f) or {}
        except Exception as e:
            return _ok({'success': False, 'message': f'读取 JSON 失败: {e}'}, 500)

        records = {k: len(v) for k, v in raw.items() if isinstance(v, list)}
        if not migrator.migrate_json_to_sqlite(create_backup=True):
            return _ok({'success': False, 'message': '迁移失败，请查看服务端日志'}, 500)
        return _ok({'success': True, 'message': '迁移成功', 'records': records})

    def sync_export(self) -> Dict[str, Any]:
        """把 SQLite 数据导出为 JSON（会先自动备份）。"""
        from server.database.migrate import DataMigrator, JSON_FILE
        migrator = DataMigrator()
        if not migrator.export_sqlite_to_json(create_backup=True):
            return _ok({'success': False, 'message': '导出失败，请查看服务端日志'}, 500)
        return _ok({'success': True, 'message': '导出成功', 'path': JSON_FILE})

    # ---------- 文件管理 ----------

    def list_files(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """列出素材库文件。

        ``folder`` 为空 → 递归收集全部文件（资源中心要按类型筛选，需看到分类子目录）；
        指定目录 → 只列该目录的直接子项（含子目录，便于逐层浏览）。
        """
        folder = _qp(request_context, 'folder', '')
        norm = _safe_rel(folder)
        if norm is None:
            return _ok({'success': False, 'message': '非法路径'}, 400)

        root = get_resources_dir()
        base = os.path.join(root, *norm.split('/')) if norm else root
        files: List[Dict[str, Any]] = []

        if os.path.isdir(base):
            if norm:
                for name in sorted(os.listdir(base)):
                    fp = os.path.join(base, name)
                    try:
                        st = os.stat(fp)
                    except OSError:
                        continue
                    files.append({
                        'name': name,
                        'path': f"{norm}/{name}",
                        'size': st.st_size if os.path.isfile(fp) else 0,
                        'modifiedTime': int(st.st_mtime * 1000),
                        'type': 'file' if os.path.isfile(fp) else 'folder',
                    })
            else:
                for dirpath, dirnames, filenames in os.walk(base):
                    dirnames.sort()
                    for name in sorted(filenames):
                        fp = os.path.join(dirpath, name)
                        try:
                            st = os.stat(fp)
                        except OSError:
                            continue
                        rel = os.path.relpath(fp, root).replace('\\', '/')
                        files.append({
                            'name': name,
                            'path': rel,
                            'size': st.st_size,
                            'modifiedTime': int(st.st_mtime * 1000),
                            'type': 'file',
                        })

        return _ok({'success': True, 'files': files})

    def upload(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """文件上传，按表单字段分流到素材库 / 归档 / 资料目录。

        字段约定（来自各前端页面）：
          - ``targetPath``            素材库（或归档）相对目录，如 ``templates``、``images``
          - ``projectName``           项目资料 → 01_项目资料/<项目名>/<类型目录>/
          - ``playerName``            选手资料 → 02_选手档案/<姓名>/<类型目录>/
          - ``orgName``               机构资料 → 03_合作机构/<机构名>/<类型目录>/
          - ``materialType``/``title``/``stage``  配合上面的资料类型与命名
        """
        body = request_context.get('body', b'') or b''
        headers = request_context.get('headers', {}) or {}
        content_type = headers.get('Content-Type', headers.get('content-type', ''))

        if 'multipart/form-data' not in (content_type or ''):
            return _ok({'success': False, 'message': 'Content-Type 必须是 multipart/form-data'}, 400)

        fields, raw_filename, file_data = _parse_multipart(body, content_type)
        if not file_data or not raw_filename:
            return _ok({'success': False, 'message': '未收到文件'}, 400)

        title = (fields.get('title') or '').strip()
        material_type = (fields.get('materialType') or '').strip()

        dest_dir: Optional[str] = None
        final_name = _sanitize_filename(raw_filename)

        for kind, field in (('project', 'projectName'),
                            ('player', 'playerName'),
                            ('org', 'orgName')):
            entity = (fields.get(field) or '').strip()
            if not entity:
                continue
            top = _ENTITY_TOP_DIR[kind]
            sub = resolve_subdir_for_type(top, material_type)
            dest_dir = _safe_under(get_archives_dir(), top, entity, sub)
            final_name = _compose_filename(
                raw_filename, title=title, subject=entity,
                stage=(fields.get('stage') or '').strip() if kind == 'player' else '')
            break

        if dest_dir is None:
            # 素材库 / 归档 / 模板：按 targetPath 落位
            target = _safe_rel(fields.get('targetPath', ''))
            if target is None:
                return _ok({'success': False, 'message': '非法目标路径'}, 400)
            if target.split('/', 1)[0] in ARCHIVE_TOP_DIRS:
                dest_dir = _safe_under(get_archives_dir(), target)
            else:
                dest_dir = _safe_under(get_resources_dir(), target)
            final_name = _compose_filename(raw_filename, title=title)

        if not dest_dir:
            return _ok({'success': False, 'message': '目标路径越界'}, 400)

        try:
            os.makedirs(dest_dir, exist_ok=True)
            file_path = os.path.join(dest_dir, final_name)
            with open(file_path, 'wb') as f:
                f.write(file_data)
        except Exception as e:
            logger.error(f"写入上传文件失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'保存文件失败: {e}'}, 500)

        return _ok({'success': True, 'message': 'File uploaded successfully',
                    'path': final_name})

    def get_file(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """下载 / 预览文件，返回二进制。"""
        rel = _qp(request_context, 'path', '')
        target = _resolve_material_path(rel)
        if not target or not os.path.isfile(target):
            return _ok({'success': False, 'message': '文件不存在'}, 404)
        try:
            with open(target, 'rb') as f:
                data = f.read()
        except Exception as e:
            return _ok({'success': False, 'message': f'读取文件失败: {e}'}, 500)

        ctype = mimetypes.guess_type(target)[0] or 'application/octet-stream'
        return {
            'status': 200,
            'body': data,
            'headers': {
                'Content-Type': ctype,
                'Content-Disposition': _content_disposition('inline', os.path.basename(target)),
                'Cache-Control': 'no-store',
            },
        }

    def delete_file(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """删除文件（进回收站，可恢复）。"""
        rel = _qp(request_context, 'path', '')
        target = _resolve_material_path(rel)
        if not target or not os.path.exists(target):
            return _ok({'success': False, 'message': '文件不存在'}, 404)
        try:
            if send_to_trash(target):
                return _ok({'success': True, 'message': 'File deleted'})
            return _ok({'success': False, 'message': '删除失败'}, 500)
        except Exception as e:
            logger.error(f"删除文件失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'删除失败: {e}'}, 500)

    def open_resource(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """用系统默认程序打开素材文件。"""
        payload = _json_body(request_context)
        rel = (payload or {}).get('path', '') if isinstance(payload, dict) else ''
        target = _resolve_material_path(rel)
        if not target or not os.path.exists(target):
            return _ok({'success': False, 'message': '文件不存在'}, 404)
        _open_in_os(target)
        return _ok({'success': True, 'message': f'Opened: {rel}'})

    def open_folder(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """打开本地素材文件夹（path 为空即素材库根目录）。"""
        payload = _json_body(request_context)
        rel = (payload or {}).get('path', '') if isinstance(payload, dict) else ''
        norm = _safe_rel(rel)
        if norm is None:
            return _ok({'success': False, 'message': '非法路径'}, 400)
        root = get_resources_dir()
        target = os.path.join(root, *norm.split('/')) if norm else root
        if not os.path.isdir(target):
            os.makedirs(target, exist_ok=True)
        _open_in_os(target)
        return _ok({'success': True, 'message': '已打开本地文件夹', 'path': target})
