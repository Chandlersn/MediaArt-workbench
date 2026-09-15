"""
Global search API routes module.

全局搜索：跨 项目 / 选手 / 机构 / 财务 / 知识库 的关键词检索，
返回按模块分组的命中结果，供前端顶部搜索框调用。

鉴权说明：同 KnowledgeRouter —— 不在方法上挂函数式装饰器，改为在 handle_request
内联完成认证判定，避免 self 被误当 request_context。
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from server.database.store import data_store
from server.utils.auth_middleware import extract_user_from_request
from server.archive.taxonomy import ARCHIVE_TOP_DIRS

logger = logging.getLogger(__name__)


class SearchRouter:
    """Router for global search API endpoints."""

    def _auth(self, request_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user = extract_user_from_request(request_context)
        if not user:
            return {
                'status': 401,
                'body': {
                    'success': False,
                    'message': '认证失败，Token 无效或缺失',
                    'error': 'UNAUTHORIZED'
                },
                'headers': {'Content-Type': 'application/json'}
            }
        request_context['user'] = user
        return None

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        auth_err = self._auth(request_context)
        if auth_err:
            return auth_err

        if method == 'GET' and path == '/api/search':
            return self.search(request_context)
        return {
            'status': 405,
            'body': {'success': False, 'error': 'Method Not Allowed'},
            'headers': {'Content-Type': 'application/json'}
        }

    def _match(self, fields: List[str], q: str) -> bool:
        ql = q.lower()
        return any(ql in (str(f) or '').lower() for f in fields if f is not None)

    # 文件扩展名 → 类别（用于 files 分组的 type 维度与筛选）
    EXT_CATEGORY = {
        'mp4': '视频', 'mov': '视频', 'avi': '视频', 'mkv': '视频', 'webm': '视频',
        'flv': '视频', 'wmv': '视频', 'm4v': '视频',
        'jpg': '图片', 'jpeg': '图片', 'png': '图片', 'gif': '图片', 'bmp': '图片',
        'webp': '图片', 'svg': '图片', 'tiff': '图片',
        'mp3': '音频', 'wav': '音频', 'ogg': '音频', 'm4a': '音频', 'flac': '音频', 'aac': '音频',
        'pdf': '文档', 'doc': '文档', 'docx': '文档', 'xls': '文档', 'xlsx': '文档',
        'ppt': '文档', 'pptx': '文档', 'txt': '文档', 'md': '文档', 'markdown': '文档',
        'csv': '文档', 'json': '文档', 'xml': '文档', 'rtf': '文档',
        'zip': '压缩包', 'rar': '压缩包', '7z': '压缩包', 'tar': '压缩包', 'gz': '压缩包',
        'js': '代码', 'ts': '代码', 'vue': '代码', 'py': '代码', 'java': '代码',
        'c': '代码', 'cpp': '代码', 'h': '代码', 'cs': '代码', 'go': '代码', 'rs': '代码',
        'html': '代码', 'css': '代码', 'sql': '代码', 'sh': '代码',
    }

    def _file_category(self, ext: str) -> str:
        return self.EXT_CATEGORY.get(ext, '其他')

    def _date_in_range(self, date_val: str, date_from: str, date_to: str) -> bool:
        if not date_from and not date_to:
            return True
        s = (date_val or '')[:10]
        if not s:
            return True
        if date_from and s < date_from:
            return False
        if date_to and s > date_to:
            return False
        return True

    def _collect_files(self, q: str, type_filter: str, entity: str,
                       date_from: str, date_to: str) -> List[Dict[str, Any]]:
        """walk 归档目录 + 素材库，按文件名(含相对路径)匹配 q，并按 type/entity/date 过滤。"""
        from server.resources.routes import get_archives_dir, RESOURCES_DIR
        hits: List[Dict[str, Any]] = []
        limit = 200
        ql = q.lower()
        entity_l = entity.lower()
        roots = [('archive', get_archives_dir()), ('resource', RESOURCES_DIR)]
        for kind, base in roots:
            if not os.path.isdir(base):
                continue
            base_norm = os.path.normpath(base)
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for name in files:
                    if name.startswith('.'):
                        continue
                    if ql and ql not in name.lower():
                        continue
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, base_norm).replace('\\', '/')
                    ext = os.path.splitext(name)[1].lstrip('.').lower()
                    cat = self._file_category(ext)
                    if type_filter and type_filter != cat.lower():
                        continue
                    if entity_l:
                        parts = rel.split('/')
                        ent = parts[1] if kind == 'archive' and len(parts) > 1 and parts[0] in ARCHIVE_TOP_DIRS else ''
                        if kind != 'archive' or entity_l not in ent.lower():
                            continue
                    try:
                        mtime = os.path.getmtime(full)
                        mdate = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                        size = os.path.getsize(full)
                    except OSError:
                        mtime, mdate, size = 0, '', 0
                    if not self._date_in_range(mdate, date_from, date_to):
                        continue
                    route = '/archive' if kind == 'archive' else '/resources'
                    hits.append({
                        'id': rel, 'title': name, 'sub': os.path.dirname(rel) or '/',
                        'route': route, 'path': rel, 'kind': 'file',
                        'category': cat, 'size': size, 'modified': mtime, 'source': kind,
                    })
                    if len(hits) >= limit:
                        return hits
        return hits

    def search(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        query_params = request_context.get('query_params', {}) or {}
        q = (query_params.get('q', [''])[0] or '').strip()
        modules_param = (query_params.get('modules', [''])[0] or '').strip()
        type_filter = (query_params.get('type', [''])[0] or '').strip().lower()
        entity = (query_params.get('entity', [''])[0] or '').strip()
        date_from = (query_params.get('dateFrom', [''])[0] or '').strip()
        date_to = (query_params.get('dateTo', [''])[0] or '').strip()

        ALL_MODULES = ['projects', 'players', 'organizations', 'finances', 'knowledge', 'files']
        if modules_param:
            modules = [m for m in modules_param.split(',') if m in ALL_MODULES]
            if not modules:
                modules = ALL_MODULES
        else:
            modules = ALL_MODULES

        has_q = bool(q)
        results: Dict[str, List[Dict[str, Any]]] = {}

        # 实体名称映射（选手归属解析：project_id / org_id → 名称）
        proj_map = {p.get('id'): (p.get('name') or '') for p in (data_store.projects.get_all() or [])}
        org_map = {o.get('id'): (o.get('name') or '') for o in (data_store.organizations.get_all() or [])}

        def type_of(mod: str, it: Dict[str, Any], explicit_type: Optional[str] = None) -> str:
            if explicit_type is not None:
                return explicit_type
            if mod == 'projects':
                return it.get('type') or ''
            if mod == 'players':
                return it.get('category') or ''
            if mod == 'organizations':
                return it.get('type') or ''
            if mod == 'finances':
                return it.get('type') or it.get('category') or ''
            if mod == 'files':
                return it.get('category', '')
            return ''

        def entity_names(mod: str, it: Dict[str, Any]) -> List[str]:
            if mod == 'players':
                names = []
                pid = it.get('project_id')
                oid = it.get('org_id')
                if pid and proj_map.get(pid):
                    names.append(proj_map[pid])
                if oid and org_map.get(oid):
                    names.append(org_map[oid])
                return names
            if mod in ('projects', 'organizations'):
                return [it.get('name', '')]
            if mod == 'files':
                parts = it.get('path', '').split('/')
                if len(parts) > 1 and parts[0] in ARCHIVE_TOP_DIRS:
                    return [parts[1]]
                return []
            return []

        def date_of(mod: str, it: Dict[str, Any]) -> str:
            if mod == 'files':
                return datetime.fromtimestamp(it.get('modified', 0)).strftime('%Y-%m-%d') if it.get('modified') else ''
            for k in ('created_at', 'updated_at', 'start_date', 'date'):
                v = it.get(k)
                if v:
                    return str(v)[:10]
            return ''

        def passes(mod: str, it: Dict[str, Any], explicit_type: Optional[str] = None) -> bool:
            if type_filter and type_filter != type_of(mod, it, explicit_type).lower():
                return False
            if entity:
                ens = [e.lower() for e in entity_names(mod, it)]
                if not any(entity.lower() in e for e in ens):
                    return False
            if not self._date_in_range(date_of(mod, it), date_from, date_to):
                return False
            return True

        PER_MODULE_CAP = 50

        # 项目
        if 'projects' in modules:
            for p in (data_store.projects.get_all() or []):
                if has_q and not self._match([p.get('name'), p.get('type'), p.get('manager'), p.get('description')], q):
                    continue
                if not passes('projects', p):
                    continue
                results.setdefault('projects', []).append({
                    'id': p.get('id'), 'title': p.get('name') or '(未命名)',
                    'sub': p.get('type') or '', 'route': f"/projects/{p.get('id')}",
                    'category': p.get('type') or '', 'modified': 0,
                })
                if len(results['projects']) >= PER_MODULE_CAP:
                    break

        # 选手
        if 'players' in modules:
            for p in (data_store.players.get_all() or []):
                if has_q and not self._match([p.get('name'), p.get('category'), p.get('phone'), p.get('note'), p.get('stage')], q):
                    continue
                if not passes('players', p):
                    continue
                results.setdefault('players', []).append({
                    'id': p.get('id'), 'title': p.get('name') or '(未命名)',
                    'sub': p.get('category') or '', 'route': f"/players/{p.get('id')}",
                    'category': p.get('category') or '', 'modified': 0,
                })
                if len(results['players']) >= PER_MODULE_CAP:
                    break

        # 机构
        if 'organizations' in modules:
            for o in (data_store.organizations.get_all() or []):
                if has_q and not self._match([o.get('name'), o.get('type'), o.get('contact'), o.get('phone'), o.get('note')], q):
                    continue
                if not passes('organizations', o):
                    continue
                results.setdefault('organizations', []).append({
                    'id': o.get('id'), 'title': o.get('name') or '(未命名)',
                    'sub': o.get('type') or '', 'route': f"/organizations/{o.get('id')}",
                    'category': o.get('type') or '', 'modified': 0,
                })
                if len(results['organizations']) >= PER_MODULE_CAP:
                    break

        # 财务（无详情页，跳转到财务列表）
        if 'finances' in modules:
            for f in (data_store.finances.get_all() or []):
                if has_q and not self._match([f.get('title'), f.get('category'), f.get('note'), f.get('type')], q):
                    continue
                if not passes('finances', f):
                    continue
                results.setdefault('finances', []).append({
                    'id': f.get('id'), 'title': f.get('title') or '(无摘要)',
                    'sub': f"{f.get('type') or ''} {f.get('category') or ''}".strip(),
                    'route': '/finance',
                    'category': f.get('type') or f.get('category') or '', 'modified': 0,
                })
                if len(results['finances']) >= PER_MODULE_CAP:
                    break

        # 知识库
        if 'knowledge' in modules:
            knowledge = data_store._load_knowledge()
            for t, items in knowledge.items():
                for it in items:
                    if has_q:
                        hay = [it.get('title'), it.get('description'), ' '.join(it.get('tags') or [])]
                        hay += [str(v) for v in (it.get('fields') or {}).values() if isinstance(v, str)]
                        if not self._match(hay, q):
                            continue
                    if not passes('knowledge', it, explicit_type=t):
                        continue
                    results.setdefault('knowledge', []).append({
                        'id': it.get('id'), 'title': it.get('title') or '(未命名)',
                        'sub': t, 'route': f"/knowledge/{it.get('id')}",
                        'category': t, 'modified': 0,
                    })
                    if len(results['knowledge']) >= PER_MODULE_CAP:
                        break

        # 文件（归档 + 素材库）
        if 'files' in modules:
            files = self._collect_files(q, type_filter, entity, date_from, date_to)
            if files:
                results['files'] = files

        # facets：各模块命中数 + 各类型聚合计数
        facets = {
            'modules': {k: len(v) for k, v in results.items()},
            'types': {},
        }
        for v in results.values():
            for it in v:
                c = (it.get('category') or '').strip()
                if c:
                    facets['types'][c] = facets['types'].get(c, 0) + 1

        total = sum(len(v) for v in results.values())
        return {
            'status': 200,
            'body': {
                'success': True, 'query': q, 'total': total,
                'results': results, 'facets': facets,
                'applied': {
                    'modules': modules, 'type': type_filter,
                    'entity': entity, 'dateFrom': date_from, 'dateTo': date_to,
                },
            },
            'headers': {'Content-Type': 'application/json'}
        }
