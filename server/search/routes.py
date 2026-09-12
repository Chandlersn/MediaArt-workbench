"""
Global search API routes module.

全局搜索：跨 项目 / 选手 / 机构 / 财务 / 知识库 的关键词检索，
返回按模块分组的命中结果，供前端顶部搜索框调用。

鉴权说明：同 KnowledgeRouter —— 不在方法上挂函数式装饰器，改为在 handle_request
内联完成认证判定，避免 self 被误当 request_context。
"""

import json
import logging
from typing import Dict, Any, List
from server.database.store import data_store
from server.utils.auth_middleware import extract_user_from_request

logger = logging.getLogger(__name__)


class SearchRouter:
    """Router for global search API endpoints."""

    def _auth(self, request_context: Dict[str, Any]) -> Dict[str, Any] | None:
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

    def search(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        query_params = request_context.get('query_params', {})
        q = (query_params.get('q', [''])[0] or '').strip()
        if not q:
            return {
                'status': 200,
                'body': {'success': True, 'query': q, 'total': 0, 'results': {}},
                'headers': {'Content-Type': 'application/json'}
            }

        results: Dict[str, List[Dict[str, Any]]] = {}

        # 项目
        projects = data_store.projects.get_all() if hasattr(data_store.projects, 'get_all') else []
        for p in projects:
            if self._match([p.get('name'), p.get('type'), p.get('manager'), p.get('description')], q):
                results.setdefault('projects', []).append({
                    'id': p.get('id'), 'title': p.get('name') or '(未命名)',
                    'sub': p.get('type') or '', 'route': f"/projects/{p.get('id')}"
                })

        # 选手
        players = data_store.players.get_all() if hasattr(data_store.players, 'get_all') else []
        for p in players:
            if self._match([p.get('name'), p.get('category'), p.get('phone'), p.get('note'), p.get('stage')], q):
                results.setdefault('players', []).append({
                    'id': p.get('id'), 'title': p.get('name') or '(未命名)',
                    'sub': p.get('category') or '', 'route': f"/players/{p.get('id')}"
                })

        # 机构
        orgs = data_store.organizations.get_all() if hasattr(data_store.organizations, 'get_all') else []
        for o in orgs:
            if self._match([o.get('name'), o.get('type'), o.get('contact'), o.get('phone'), o.get('note')], q):
                results.setdefault('organizations', []).append({
                    'id': o.get('id'), 'title': o.get('name') or '(未命名)',
                    'sub': o.get('type') or '', 'route': f"/organizations/{o.get('id')}"
                })

        # 财务（无详情页，跳转到财务列表）
        finances = data_store.finances.get_all() if hasattr(data_store.finances, 'get_all') else []
        for f in finances:
            if self._match([f.get('title'), f.get('category'), f.get('note'), f.get('type')], q):
                results.setdefault('finances', []).append({
                    'id': f.get('id'), 'title': f.get('title') or '(无摘要)',
                    'sub': f"{f.get('type') or ''} {f.get('category') or ''}".strip(),
                    'route': '/finance'
                })

        # 知识库
        knowledge = data_store._load_knowledge()
        for t, items in knowledge.items():
            for it in items:
                hay = [it.get('title'), it.get('description'),
                       ' '.join(it.get('tags') or [])]
                fields = it.get('fields') or {}
                hay += [str(v) for v in fields.values() if isinstance(v, str)]
                if self._match(hay, q):
                    results.setdefault('knowledge', []).append({
                        'id': it.get('id'), 'title': it.get('title') or '(未命名)',
                        'sub': t, 'route': f"/knowledge/{it.get('id')}"
                    })

        total = sum(len(v) for v in results.values())
        return {
            'status': 200,
            'body': {'success': True, 'query': q, 'total': total, 'results': results},
            'headers': {'Content-Type': 'application/json'}
        }
