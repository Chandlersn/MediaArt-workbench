"""
Finances API routes module.
"""

import json
import logging
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_auth, require_permission

logger = logging.getLogger(__name__)


class FinancesRouter:
    """Router for finance-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle finance-related requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path in ('/api/finances', '/api/finances/list'):
                return self.list_finances(request_context)
            elif method == 'GET' and path.startswith('/api/finances/'):
                finance_id = path.split('/')[-1]
                return self.get_finance(finance_id, request_context)
            elif method == 'POST' and path == '/api/finances':
                return self.create_finance(request_context)
            elif method == 'PUT' and path.startswith('/api/finances/'):
                finance_id = path.split('/')[-1]
                return self.update_finance(finance_id, request_context)
            elif method == 'DELETE' and path.startswith('/api/finances/'):
                finance_id = path.split('/')[-1]
                return self.delete_finance(finance_id, request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling finance request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('finances', 'view')
    def list_finances(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get all finance records with optional filtering."""
        query_params = request_context.get('query_params', {})
        search = query_params.get('search', [''])[0]
        type_filter = query_params.get('type', ['all'])[0]

        finances = data_store.finances.get_all(order_by='date DESC')

        if search:
            search_lower = search[0].lower() if isinstance(search, list) else search.lower()
            finances = [f for f in finances if search_lower in f.get('description', '').lower()]

        if type_filter and type_filter != 'all':
            finances = [f for f in finances if f.get('type') == type_filter]

        return {
            'status': 200,
            'body': {'success': True, 'data': finances, 'total': len(finances)},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('finances', 'view')
    def get_finance(self, finance_id, request_context=None) -> Dict[str, Any]:
        """Get a specific finance record by ID."""
        finance = data_store.finances.get_by_id(finance_id)
        if finance:
            return {
                'status': 200,
                'body': {'success': True, 'data': finance},
                'headers': {'Content-Type': 'application/json'}
            }
        return {
            'status': 404,
            'body': {'success': False, 'message': 'Finance record not found'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('finances', 'edit')
    def create_finance(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new finance record."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        finance_id = data_store.finances.create(data)
        return {
            'status': 201,
            'body': {'success': True, 'id': finance_id, 'message': 'Finance record created'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('finances', 'edit')
    def update_finance(self, finance_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Update a finance record."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        success = data_store.finances.update(finance_id, data)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Finance record updated' if success else 'Finance record not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('finances', 'delete')
    def delete_finance(self, finance_id, request_context=None) -> Dict[str, Any]:
        """Delete a finance record."""
        success = data_store.finances.delete(finance_id)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Finance record deleted' if success else 'Finance record not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }
