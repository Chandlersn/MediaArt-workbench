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

目录约定（位于归档目录 MediaArt_Archives/ 下，与归档管理共用同一套分类）：

    项目： 01_项目资料/<项目名>/<序号_类型>/<文件>
    机构： 03_合作机构/<机构名>/<序号_类型>/<文件>
    选手： 02_选手档案/<选手名>/<序号_类型>/<文件>

分类与目录口径来自 server/archive/taxonomy.py 的单一权威定义。
⚠️ 本模块此前误用 resources/ 根目录（数据实际在归档），导致详情页「资料区」恒为空，
   现已修正为读取归档目录。

下载类接口返回文件，可能带中文文件名，必须用 _content_disposition 构造响应头
（send_header 以 latin-1 发送，中文名会抛 UnicodeEncodeError 并打成 500）。
"""

import os
import json
import uuid
import logging
import mimetypes
from typing import Dict, Any, List, Optional
from urllib.parse import unquote

from server.database.store import data_store
from server.resources.routes import get_archives_dir, _content_disposition
from server.archive.taxonomy import strip_seq, MATERIAL_TYPE_TO_SUBDIR
from server.utils.auth_middleware import extract_user_from_request
from server.utils.trash import send_to_trash

logger = logging.getLogger(__name__)

JSON_HEADERS = {'Content-Type': 'application/json'}

# kind -> 归档一级分类
_SUB = {'project': '01_项目资料', 'org': '03_合作机构', 'player': '02_选手档案'}


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
    value = value.split('/')[-1]
    return value.replace('..', '').strip()


def _safe_under(base: str, *parts: str) -> Optional[str]:
    base = os.path.abspath(base)
    comps = [_safe_component(p) for p in parts]
    target = os.path.abspath(os.path.join(base, *comps))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _iso(ts: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).isoformat()


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


class MaterialsRouter:
    """Router for material scan/download/delete and player import endpoints."""

    def __init__(self):
        # 资料实体目录位于归档目录下（此前误接 resources/，故详情页恒为空）
        self.root = get_archives_dir()

    def _entity_dir(self, kind: str, name: str) -> Optional[str]:
        """解析 <归档分类>/<实体名> 目录，越界或非法返回 None。"""
        return _safe_under(self.root, _SUB[kind], _safe_component(name))

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

            # 机构 / 项目批量导入
            if norm == '/api/import-organizations' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.import_organizations(request_context)
            if norm == '/api/import-projects' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.import_projects(request_context)

            return _ok({'success': False, 'error': 'Method Not Allowed'}, 405)
        except Exception as e:
            logger.error(f"处理资料请求失败: {e}", exc_info=True)
            return _ok({'success': False, 'error': 'Internal Server Error', 'message': str(e)}, 500)

    # ---------- 扫描 ----------
    def scan(self, kind: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """列出 <归档分类>/<实体名>/ 下各二级目录（序号_类型）中的文件。

        新上传保留准确类型；历史文件无元信息时按目录类型兜底。
        """
        name = _qp(request_context, 'name', '')
        base = self._entity_dir(kind, name)
        materials: List[Dict[str, Any]] = []
        if base and os.path.isdir(base):
            from server.materials.metadata import load_metadata, get_metadata
            metadata = load_metadata()
            for sub in sorted(os.listdir(base)):
                sub_dir = os.path.join(base, sub)
                if not os.path.isdir(sub_dir):
                    continue
                mtype = strip_seq(sub)
                for f in _flist(sub_dir):
                    # 赛段只存在于文件名中（{主体}_{赛段}__{类型}_{序号}.ext）——
                    # 三级目录已不含赛段层，故从文件名回解，供详情页「按赛段分组」。
                    stage = ''
                    if kind == 'player' and '__' in f['name']:
                        # 赛段约定写在 `__` 之前：{主体}_{赛段}__{标题}_{日期}.ext
                        head = f['name'].rsplit('.', 1)[0].split('__', 1)[0]
                        if head.startswith(name + '_'):
                            stage = head[len(name) + 1:]
                    exact = get_metadata(os.path.join(sub_dir, f['name']), metadata)
                    materials.append({
                        'type': (exact.get('type') or mtype) if exact else mtype,
                        'file_name': f['name'],
                        'name': f['name'],
                        'upload_date': f['upload_date'],
                        'stage': exact.get('stage', stage) if exact else stage,
                    })
        return _ok({'success': True, 'materials': materials})

    # ---------- 定位文件 ----------
    def locate(self, kind: str, entity_name: str, file_name: str,
               material_type: str = '') -> Optional[str]:
        """在归档中定位某实体的资料文件。

        供下载/删除与 system 路由的文本预览共用，避免各自实现一套定位逻辑
        （此前文本预览用硬编码的 resources/ 目录找，永远找不到归档文件）。
        """
        root = self._entity_dir(kind, entity_name)
        fn = _safe_component(unquote(file_name or ''))
        mt = unquote(material_type or '').strip()
        if not root or not os.path.isdir(root) or not fn:
            return None
        # 精确类型优先；无元信息的旧文件才用目录名称/别名匹配。
        # 传了类型却只找到其他类型时不能回退，否则会下载/删除同名的另一份资料。
        subs = [d for d in sorted(os.listdir(root)) if os.path.isdir(os.path.join(root, d))]
        candidates = [(sub, os.path.join(root, sub, fn)) for sub in subs]
        candidates.append(('', os.path.join(root, fn)))
        candidates = [(sub, path) for sub, path in candidates if os.path.isfile(path)]
        if not mt:
            return candidates[0][1] if candidates else None
        from server.materials.metadata import load_metadata, get_metadata
        metadata = load_metadata()
        exact_matches, legacy_matches = [], []
        alias_dir = MATERIAL_TYPE_TO_SUBDIR.get(_SUB[kind], {}).get(mt)
        for sub, path in candidates:
            exact = get_metadata(path, metadata)
            if exact and exact.get('type'):
                if exact['type'] == mt:
                    exact_matches.append(path)
            elif sub == mt or strip_seq(sub) == mt or (alias_dir and sub == alias_dir):
                legacy_matches.append(path)
        matches = exact_matches or legacy_matches
        return matches[0] if len(matches) == 1 else None

    def _locate(self, kind: str, request_context: Dict[str, Any]) -> Optional[str]:
        if kind == 'project':
            name = _qp(request_context, 'projectName', '')
        elif kind == 'org':
            name = _qp(request_context, 'orgName', '')
        else:
            name = _qp(request_context, 'playerName', '')
        return self.locate(kind, name,
                           _qp(request_context, 'fileName', ''),
                           _qp(request_context, 'materialType', ''))

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
                    'Content-Disposition': _content_disposition(disp, os.path.basename(target)),
                }
            }
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)

    def delete(self, kind: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
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
            rid = send_to_trash(target)
            if not rid:
                return _ok({'success': False, 'message': '删除失败，原文件已保留'}, 500)
            return _ok({'success': True, 'message': '已移入回收站'})
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)

    # ---------- 选手导入 ----------
    def import_players(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        from server.utils.validators import validate_person_fields
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
            phone_val = (row.get('phone') or row.get('电话') or '').strip()
            idcard_val = (row.get('idCard') or row.get('身份证') or '').strip()
            err = validate_person_fields({'phone': phone_val, 'idCard': idcard_val})
            if err:
                failed += 1
                errors.append(f"{name}: {err}")
                continue
            record = {
                'id': str(uuid.uuid4()),
                'name': name,
                'gender': row.get('gender') or row.get('性别') or '',
                'category': row.get('category') or row.get('类别') or '',
                'level': row.get('level') or row.get('级别') or '',
                'phone': phone_val,
                'note': row.get('note') or row.get('备注') or '',
                'stage': row.get('stage') or row.get('阶段') or '初赛',
            }
            if idcard_val:
                record['idCard'] = idcard_val
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

    def import_organizations(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """批量导入机构。

        与 import_players 同构：逐行独立处理，单行失败不影响其余行，
        最后统一返回 imported / failed / errors，让用户看到「哪几行没进来」。
        ⚠️ 名称重复时跳过并计入 failed —— 机构名是人工识别的唯一依据，
        静默产生两个同名机构会让后续关联选错对象。
        """
        body = request_context.get('body', b'')
        payload = json.loads(body) if body else {}
        rows = payload.get('organizations') or []

        existing_names = {(o.get('name') or '').strip() for o in data_store.organizations.get_all()}

        imported = 0
        failed = 0
        errors: List[str] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                failed += 1
                continue
            name = (row.get('name') or row.get('机构名称') or row.get('名称') or '').strip()
            if not name:
                failed += 1
                errors.append(f"第 {i + 1} 行缺少机构名称")
                continue
            if name in existing_names:
                failed += 1
                errors.append(f"{name}: 机构已存在，已跳过")
                continue

            record = {
                'id': str(uuid.uuid4()),
                'name': name,
                'type': (row.get('type') or row.get('机构类型') or row.get('类型') or '').strip(),
                'level': (row.get('level') or row.get('合作级别') or row.get('级别') or '普通合作').strip(),
                'contact': (row.get('contact') or row.get('联系人') or '').strip(),
                'phone': (row.get('phone') or row.get('联系电话') or row.get('电话') or '').strip(),
                'address': (row.get('address') or row.get('地址') or '').strip(),
                'note': (row.get('note') or row.get('备注') or '').strip(),
            }
            try:
                data_store.organizations.create(record)
                existing_names.add(name)
                imported += 1
            except Exception as e:
                failed += 1
                errors.append(f"{name}: {e}")
        return _ok({'success': True, 'imported': imported, 'failed': failed, 'errors': errors})

    def import_projects(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """批量导入项目。

        机构关联（org_ids）在导入时不解析名称 —— 名称可能打错或有别名，
        静默匹配失败会写入错误的关联。用户导入后到详情页手动挂机构更可靠。
        """
        body = request_context.get('body', b'')
        payload = json.loads(body) if body else {}
        rows = payload.get('projects') or []

        existing_names = {(p.get('name') or '').strip() for p in data_store.projects.get_all()}

        imported = 0
        failed = 0
        errors: List[str] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                failed += 1
                continue
            name = (row.get('name') or row.get('项目名称') or row.get('名称') or '').strip()
            if not name:
                failed += 1
                errors.append(f"第 {i + 1} 行缺少项目名称")
                continue
            if name in existing_names:
                failed += 1
                errors.append(f"{name}: 项目已存在，已跳过")
                continue

            record = {
                'id': str(uuid.uuid4()),
                'name': name,
                'type': (row.get('type') or row.get('项目类型') or row.get('类型') or '').strip(),
                'status': (row.get('status') or row.get('状态') or '筹备中').strip(),
                'start_date': (row.get('start_date') or row.get('开始日期') or row.get('起始日期') or '').strip(),
                'end_date': (row.get('end_date') or row.get('结束日期') or row.get('截止日期') or '').strip(),
                'manager': (row.get('manager') or row.get('负责人') or '').strip(),
                'description': (row.get('description') or row.get('项目描述') or row.get('描述') or '').strip(),
                'org_ids': [],
            }
            try:
                data_store.projects.create(record)
                existing_names.add(name)
                imported += 1
            except Exception as e:
                failed += 1
                errors.append(f"{name}: {e}")
        return _ok({'success': True, 'imported': imported, 'failed': failed, 'errors': errors})
