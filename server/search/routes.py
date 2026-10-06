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
from server.search import index

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

        ALL_MODULES = list(index.MODULE_ORDER) + ['files']
        if modules_param:
            modules = [m for m in modules_param.split(',') if m in ALL_MODULES]
            if not modules:
                modules = ALL_MODULES
        else:
            modules = ALL_MODULES

        results: Dict[str, List[Dict[str, Any]]] = {}
        entity_l = entity.lower()
        PER_MODULE_CAP = 50
        targets = [m for m in modules if m != 'files']

        # 走 FTS5 索引：不再把实体表整表读进内存逐条匹配。
        # 索引过期时（数据保存过）在这里一次性重建 —— 重建要落盘，必须包事务。
        conn = data_store.db.get_connection()
        with data_store.db.transaction(immediate=True):
            index.ensure_fresh(conn)
        rows = index.search(conn, q) if q else index.all_docs(conn)

        for r in rows:
            module = r.get('module')
            if module not in targets:
                continue
            bucket = results.get(module)
            if bucket is not None and len(bucket) >= PER_MODULE_CAP:
                continue
            category = (r.get('category') or '')
            if type_filter and type_filter != category.lower():
                continue
            if entity_l and entity_l not in (r.get('entity_names') or '').lower():
                continue
            if not self._date_in_range(r.get('doc_date') or '', date_from, date_to):
                continue
            results.setdefault(module, []).append({
                'id': r.get('doc_id'),
                'title': r.get('display_title') or '(未命名)',
                'sub': r.get('display_sub') or '',
                'route': r.get('route') or '',
                'category': category,
                'modified': 0,
            })

        # 文件（归档 + 素材库）保持实时扫描：文件系统变化不受快照保存控制，
        # 建索引会失真（用户在资源管理器里拖个文件进来，索引就过期了）。
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
