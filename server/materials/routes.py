"""
Materials API routes module（项目 / 机构 / 选手 资料）。

补齐模块化后端缺失的「资料扫描 / 下载 / 删除」接口，前端 ProjectDetailView /
OrganizationDetailView / PlayerDetailView / PlayersView 依赖：

    GET    /api/scan-project-files?name=          项目资料清单
    GET    /api/scan-org-files?name=              机构资料清单
    GET    /api/scan-player-files?name=           选手资料清单
    GET    /api/download-project-material?projectName&fileName&materialType
    GET    /api/download-player-material?playerName&fileName&materialType
    GET    /api/get-org-material?orgName&fileName&materialType
    DELETE /api/delete-project-material  {projectName,fileName}
    DELETE /api/delete-org-material      {orgName,fileName,materialType}
    DELETE /api/delete-player-material   {playerName,fileName}
    POST   /api/import-players           {players:[...]}

目录约定（均位于资源根目录下，与资源中心共用）：
    项目： resources/projects/<项目名>/<资料类型>/<文件>
    机构： resources/organizations/<机构名>/<资料类型>/<文件>
    选手： resources/players/<选手名>/<阶段>/<资料类型>/<文件>

下载类接口通过浏览器 <a> 标签直连（不带 Authorization 头），因此不做强制鉴权，
仅做路径安全校验；扫描/删除/导入等操作仍要求登录。
"""

import os
import json
import uuid
import logging
import mimetypes
from typing import Dict, Any, List, Optional
from urllib.parse import unquote

from server.database.store import data_store
from server.resources.routes import get_resources_dir
from server.utils.auth_middleware import extract_user_from_request

logger = logging.getLogger(__name__)

JSON_HEADERS = {'Content-Type': 'application/json'}
_SUB = {'project': 'projects', 'org': 'organizations', 'player': 'players'}


def _ok(body: Any, status: int = 200) -> Dict[str, Any]:
    return {'status': status, 'body': body, 'headers': dict(JSON_HEADERS)}


def _qp(request_context: Dict[str, Any], key: str, default: str = '') -> str:
    qp = request_context.get('query_params', {}) or {}
    val = qp.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


def _safe_component(value: str) -> str:
    """清洗单层路径名，杜绝穿越。"""
    value = (value or '').replace('\\', '/').strip().strip('/')
    # 只取最后一段并去除 .. 等危险片段
    value = value.split('/')[-1]
    return value.replace('..', '').strip()


def _safe_under(base: str, *parts: str) -> Optional[str]:
    base = os.path.abspath(base)
    comps = [_safe_component(p) for p in parts]
    target = os.path.abspath(os.path.join(base, *comps))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _flist(dirpath: str) -> List[Dict[str, Any]]:
    out = []
    if not os.path.isdir(dirpath):
        return out
    for fn in sorted(os.listdir(dirpath)):
        fp = os.path.join(dirpath, fn)
        if os.path.isfile(fp):
            try:
                st = os.stat(fp)
            except OSError:
                continue
            out.append({'name': fn, 'size': st.st_size,
                        'mtime': int(st.st_mtime * 1000),
                        'upload_date': _iso(st.st_mtime)})
    return out


def _iso(ts: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).isoformat()


class MaterialsRouter:
    """Router for material scan/download/delete and player import endpoints."""

    def __init__(self):
        self.root = get_resources_dir()

    def _auth(self, request_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user = extract_user_from_request(request_context)
        if not user:
            return _ok({'success': False, 'message': '认证失败，Token 无效或缺失',
                        'error': 'UNAUTHORIZED'}, 401)
        request_context['user'] = user
        return None

    # ---------- 分发 ----------
    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')
        norm = path.split('?')[0]

        try:
            # 扫描（需登录）
            if norm == '/api/scan-project-files' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.scan('project', request_context)
            if norm == '/api/scan-org-files' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.scan('org', request_context)
            if norm == '/api/scan-player-files' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.scan('player', request_context)

            # 下载 / 预览（需登录；前端统一用 getBlob 带 Authorization 头请求）
            if norm == '/api/download-project-material' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.download('project', request_context)
            if norm == '/api/download-player-material' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.download('player', request_context)
            if norm == '/api/get-org-material' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.download('org', request_context)

            # 删除（需登录）
            if norm == '/api/delete-project-material' and method == 'DELETE':
                if (a := self._auth(request_context)):
                    return a
                return self.delete('project', request_context)
            if norm == '/api/delete-org-material' and method == 'DELETE':
                if (a := self._auth(request_context)):
                    return a
                return self.delete('org', request_context)
            if norm == '/api/delete-player-material' and method == 'DELETE':
                if (a := self._auth(request_context)):
                    return a
                return self.delete('player', request_context)

            # 选手批量导入
            if norm == '/api/import-players' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.import_players(request_context)

            return _ok({'success': False, 'error': 'Method Not Allowed'}, 405)
        except Exception as e:
            logger.error(f"处理资料请求失败: {e}", exc_info=True)
            return _ok({'success': False, 'error': 'Internal Server Error', 'message': str(e)}, 500)

    # ---------- 扫描 ----------
    def scan(self, kind: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        name = _qp(request_context, 'name', '')
        comp = _safe_component(name)
        base = _safe_under(self.root, _SUB[kind], comp)
        materials: List[Dict[str, Any]] = []
        if base and os.path.isdir(base):
            if kind == 'player':
                for stage in sorted(os.listdir(base)):
                    stage_dir = os.path.join(base, stage)
                    if not os.path.isdir(stage_dir):
                        continue
                    for mtype in sorted(os.listdir(stage_dir)):
                        type_dir = os.path.join(stage_dir, mtype)
                        if not os.path.isdir(type_dir):
                            continue
                        for f in _flist(type_dir):
                            materials.append({
                                'type': mtype,
                                'file_name': f['name'],
                                'upload_date': f['upload_date'],
                                'stage': '' if stage == '_general' else stage,
                            })
            else:
                for mtype in sorted(os.listdir(base)):
                    type_dir = os.path.join(base, mtype)
                    if not os.path.isdir(type_dir):
                        continue
                    for f in _flist(type_dir):
                        item = {'type': mtype, 'upload_date': f['upload_date'],
                                'file_name': f['name'], 'name': f['name']}
                        materials.append(item)
        return _ok({'success': True, 'materials': materials})

    # ---------- 定位文件 ----------
    def _locate(self, kind: str, request_context: Dict[str, Any]) -> Optional[str]:
        if kind == 'project':
            name = _qp(request_context, 'projectName', '')
        elif kind == 'org':
            name = _qp(request_context, 'orgName', '')
        else:
            name = _qp(request_context, 'playerName', '')
        file_name = _safe_component(unquote(_qp(request_context, 'fileName', '')))
        material_type = _safe_component(unquote(_qp(request_context, 'materialType', '')))

        root = _safe_under(self.root, _SUB[kind], _safe_component(name))
        if not root or not os.path.isdir(root) or not file_name:
            return None
        if kind == 'player':
            # players/<name>/<stage>/<type>/<file>
            for stage in os.listdir(root):
                stage_dir = os.path.join(root, stage)
                if not os.path.isdir(stage_dir):
                    continue
                if material_type:
                    cand = os.path.join(stage_dir, material_type, file_name)
                    if os.path.isfile(cand):
                        return cand
                else:
                    for mtype in os.listdir(stage_dir):
                        cand = os.path.join(stage_dir, mtype, file_name)
                        if os.path.isfile(cand):
                            return cand
            return None
        # project / org: <name>/<type>/<file>
        if material_type:
            cand = os.path.join(root, material_type, file_name)
            return cand if os.path.isfile(cand) else None
        for mtype in os.listdir(root):
            cand = os.path.join(root, mtype, file_name)
            if os.path.isfile(cand):
                return cand
        return None

    def download(self, kind: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        target = self._locate(kind, request_context)
        if not target:
            return _ok({'success': False, 'message': '文件不存在'}, 404)
        try:
            with open(target, 'rb') as f:
                data = f.read()
            ctype = mimetypes.guess_type(target)[0] or 'application/octet-stream'
            disp = 'inline' if _qp(request_context, 'preview', '') == 'true' else 'attachment'
            return {
                'status': 200,
                'body': data,
                'headers': {
                    'Content-Type': ctype,
                    'Content-Disposition': f'{disp}; filename="{os.path.basename(target)}"',
                }
            }
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)

    def delete(self, kind: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        # 复用 _locate 的参数命名：把 body 塞进 query_params 视图
        merged = dict(request_context)
        qp = dict(request_context.get('query_params', {}) or {})
        if kind == 'project':
            qp['projectName'] = [data.get('projectName', '')]
        elif kind == 'org':
            qp['orgName'] = [data.get('orgName', '')]
        else:
            qp['playerName'] = [data.get('playerName', '')]
        qp['fileName'] = [data.get('fileName', '')]
        if data.get('materialType'):
            qp['materialType'] = [data.get('materialType')]
        merged['query_params'] = qp
        target = self._locate(kind, merged)
        if not target:
            return _ok({'success': False, 'message': '文件不存在'}, 404)
        try:
            os.remove(target)
            return _ok({'success': True, 'message': '已删除'})
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)

    # ---------- 选手导入 ----------
    def import_players(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        payload = json.loads(body) if body else {}
        rows = payload.get('players') or []
        imported = 0
        failed = 0
        errors: List[str] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                failed += 1
                continue
            name = (row.get('name') or row.get('姓名') or '').strip()
            if not name:
                failed += 1
                errors.append(f"第 {i + 1} 行缺少姓名")
                continue
            record = {
                'id': str(uuid.uuid4()),
                'name': name,
                'gender': row.get('gender') or row.get('性别') or '',
                'category': row.get('category') or row.get('类别') or '',
                'level': row.get('level') or row.get('级别') or '',
                'phone': row.get('phone') or row.get('电话') or '',
                'note': row.get('note') or row.get('备注') or '',
                'stage': row.get('stage') or row.get('阶段') or '初赛',
            }
            # org_id / project_id 有外键约束：留空会触发 FOREIGN KEY 失败，故仅在非空时写入
            if row.get('org_id'):
                record['org_id'] = row['org_id']
            if row.get('project_id'):
                record['project_id'] = row['project_id']
            try:
                data_store.players.create(record)
                imported += 1
            except Exception as e:
                failed += 1
                errors.append(f"{name}: {e}")
        return _ok({'success': True, 'imported': imported, 'failed': failed, 'errors': errors})
