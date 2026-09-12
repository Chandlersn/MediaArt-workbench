"""
Knowledge API routes module.

知识库后端：支持 5 类语义化类型（guide / troubleshoot / case / tip / reference），
结构化内容存于 fields（JSON），并对标题 / 标签 / 结构化字段提供服务端检索。

鉴权说明：本仓库 server/utils/auth_middleware.py 的 require_auth / require_permission
为函数式装饰器（首个位置参数即 request_context），直接套在实例方法上会因 self 占位
而误把 router 实例当 request_context。为避免改动 Auth 核心骨架，这里在 handle_request
内联完成「认证 + 权限」判定（语义与装饰器一致），方法本身不挂装饰器。
"""

import json
import logging
from typing import Dict, Any, List
from server.database.store import data_store
from server.utils.auth_middleware import extract_user_from_request
from server.utils.permissions import has_permission

logger = logging.getLogger(__name__)

# 与前端 KNOWLEDGE_TYPE_ORDER 保持一致
VALID_TYPES = ['guide', 'troubleshoot', 'case', 'tip', 'reference']
# 旧类型 → 新类型迁移
LEGACY_TYPE_MAP = {'solutions': 'guide', 'practices': 'tip', 'training': 'reference'}

# 写操作对应的权限点（映射到矩阵动作）
_MUTATING_PERMISSION = {'POST': 'edit', 'PUT': 'edit', 'DELETE': 'delete'}


class KnowledgeRouter:
    """Router for knowledge-related API endpoints."""

    def _auth(self, request_context: Dict[str, Any]) -> Dict[str, Any] | None:
        """内联鉴权 + 写操作权限判定。返回 None 表示通过，否则返回错误响应。"""
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

        perm = _MUTATING_PERMISSION.get(request_context.get('method', 'GET'))
        if perm and not has_permission(user.get('role', 'viewer'), 'knowledge', perm):
            return {
                'status': 403,
                'body': {
                    'success': False,
                    'message': f'权限不足，需要 {perm} 权限',
                    'error': 'FORBIDDEN',
                    'required_permission': perm,
                    'user_role': user.get('role', 'viewer')
                },
                'headers': {'Content-Type': 'application/json'}
            }
        return None

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        auth_err = self._auth(request_context)
        if auth_err:
            return auth_err

        try:
            if method == 'GET' and path == '/api/knowledge':
                return self.list_knowledge(request_context)
            elif method == 'GET' and path.startswith('/api/knowledge/'):
                knowledge_id = path.split('/')[-1]
                return self.get_knowledge(knowledge_id)
            elif method == 'POST' and path == '/api/knowledge':
                return self.create_knowledge(request_context)
            elif method == 'PUT' and path.startswith('/api/knowledge/'):
                knowledge_id = path.split('/')[-1]
                return self.update_knowledge(knowledge_id, request_context)
            elif method == 'DELETE' and path.startswith('/api/knowledge/'):
                knowledge_id = path.split('/')[-1]
                return self.delete_knowledge(knowledge_id)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling knowledge request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    def _normalize_type(self, t: str) -> str:
        if t in VALID_TYPES:
            return t
        return LEGACY_TYPE_MAP.get(t, 'guide')

    def _build_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        item = {
            'title': data.get('title', ''),
            'type': self._normalize_type(data.get('type', 'guide')),
            'description': data.get('description', ''),
            'author': data.get('author', ''),
            'tags': data.get('tags') or [],
            'fields': data.get('fields') or {},
            'links': data.get('links') or []
        }
        if data.get('id'):
            item['id'] = data['id']
        return item

    def list_knowledge(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        query_params = request_context.get('query_params', {})
        search = (query_params.get('search', [''])[0] or '').strip().lower()
        tag = (query_params.get('tag', [''])[0] or '').strip()
        type_filter = query_params.get('type', ['all'])[0]

        flat = []
        knowledge = data_store._load_knowledge()
        for t, items in knowledge.items():
            for it in items:
                flat.append({**it, 'kind': t})

        if type_filter and type_filter != 'all':
            flat = [k for k in flat if k.get('type') == type_filter or k.get('kind') == type_filter]

        if tag:
            flat = [k for k in flat if tag in (k.get('tags') or [])]

        if search:
            def matches(k):
                if search in (k.get('title') or '').lower():
                    return True
                if search in (k.get('description') or '').lower():
                    return True
                if any(search in t.lower() for t in (k.get('tags') or [])):
                    return True
                fields = k.get('fields') or {}
                return any(search in str(v).lower() for v in fields.values() if isinstance(v, str))
            flat = [k for k in flat if matches(k)]

        return {
            'status': 200,
            'body': {'success': True, 'data': flat, 'total': len(flat)},
            'headers': {'Content-Type': 'application/json'}
        }

    def get_knowledge(self, knowledge_id, request_context=None):
        knowledge = data_store._load_knowledge()
        for t, items in knowledge.items():
            for it in items:
                if it.get('id') == knowledge_id:
                    return {
                        'status': 200,
                        'body': {'success': True, 'data': {**it, 'kind': t}},
                        'headers': {'Content-Type': 'application/json'}
                    }
        return {
            'status': 404,
            'body': {'success': False, 'message': 'Knowledge item not found'},
            'headers': {'Content-Type': 'application/json'}
        }

    def create_knowledge(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        item = self._build_item(data)
        knowledge_id = data_store.knowledge.create(item)
        return {
            'status': 201,
            'body': {'success': True, 'id': knowledge_id, 'message': 'Knowledge item created'},
            'headers': {'Content-Type': 'application/json'}
        }

    def update_knowledge(self, knowledge_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        item = self._build_item(data)
        item['id'] = knowledge_id
        success = data_store.knowledge.update(knowledge_id, item)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Knowledge item updated' if success else 'Knowledge item not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }

    def delete_knowledge(self, knowledge_id, request_context=None):
        success = data_store.knowledge.delete(knowledge_id)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Knowledge item deleted' if success else 'Knowledge item not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }
