"""
Knowledge API routes module.
"""

import json
import logging
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_auth, require_permission

logger = logging.getLogger(__name__)


class KnowledgeRouter:
    """Router for knowledge-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle knowledge-related requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

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

    @require_auth
    def list_knowledge(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get all knowledge items with optional filtering."""
        query_params = request_context.get('query_params', {})
        search = query_params.get('search', [''])[0]
        type_filter = query_params.get('type', ['all'])[0]

        knowledge_items = data_store.knowledge.get_all(order_by='created_at DESC')

        if search:
            search_lower = search[0].lower() if isinstance(search, list) else search.lower()
            knowledge_items = [k for k in knowledge_items if search_lower in k.get('title', '').lower()]

        if type_filter and type_filter != 'all':
            knowledge_items = [k for k in knowledge_items if k.get('type') == type_filter]

        return {
            'status': 200,
            'body': {'success': True, 'data': knowledge_items, 'total': len(knowledge_items)},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_auth
    def get_knowledge(self, knowledge_id, request_context=None):
        """Get a specific knowledge item by ID."""
        knowledge = data_store.knowledge.get_by_id(knowledge_id)
        if knowledge:
            return {
                'status': 200,
                'body': {'success': True, 'data': knowledge},
                'headers': {'Content-Type': 'application/json'}
            }
        return {
            'status': 404,
            'body': {'success': False, 'message': 'Knowledge item not found'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('create')
    def create_knowledge(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new knowledge item."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        knowledge_id = data_store.knowledge.create(data)
        return {
            'status': 201,
            'body': {'success': True, 'id': knowledge_id, 'message': 'Knowledge item created'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('update')
    def update_knowledge(self, knowledge_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Update a knowledge item."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        success = data_store.knowledge.update(knowledge_id, data)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Knowledge item updated' if success else 'Knowledge item not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('delete')
    def delete_knowledge(self, knowledge_id, request_context=None):
        """Delete a knowledge item."""
        success = data_store.knowledge.delete(knowledge_id)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Knowledge item deleted' if success else 'Knowledge item not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }
