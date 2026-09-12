"""
Organizations API routes module.
"""

import json
import logging
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_auth, require_permission

logger = logging.getLogger(__name__)


class OrganizationsRouter:
    """Router for organization-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle organization-related requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path == '/api/organizations/list':
                return self.list_organizations(request_context)
            elif method == 'GET' and path == '/api/organizations':
                return self.list_organizations(request_context)
            elif method == 'GET' and path.startswith('/api/organizations/'):
                org_id = path.split('/')[-1]
                return self.get_organization(org_id, request_context)
            elif method == 'POST' and path == '/api/organizations':
                return self.create_organization(request_context)
            elif method == 'PUT' and path.startswith('/api/organizations/'):
                org_id = path.split('/')[-1]
                return self.update_organization(org_id, request_context)
            elif method == 'DELETE' and path.startswith('/api/organizations/'):
                org_id = path.split('/')[-1]
                return self.delete_organization(org_id, request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling organization request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('organizations', 'view')
    def list_organizations(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get all organizations with optional filtering."""
        query_params = request_context.get('query_params', {})
        search = query_params.get('search', [''])[0]
        type_filter = query_params.get('type', ['all'])[0]

        orgs = data_store.organizations.get_all(order_by='created_at DESC')

        if search:
            search_lower = search[0].lower() if isinstance(search, list) else search.lower()
            orgs = [o for o in orgs if search_lower in o.get('name', '').lower()]

        if type_filter and type_filter != 'all':
            orgs = [o for o in orgs if o.get('type') == type_filter]

        return {
            'status': 200,
            'body': {'success': True, 'data': orgs, 'total': len(orgs)},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('organizations', 'view')
    def get_organization(self, org_id, request_context=None) -> Dict[str, Any]:
        """Get a specific organization by ID."""
        org = data_store.organizations.get_by_id(org_id)
        if org:
            return {
                'status': 200,
                'body': {'success': True, 'data': org},
                'headers': {'Content-Type': 'application/json'}
            }
        return {
            'status': 404,
            'body': {'success': False, 'message': 'Organization not found'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('organizations', 'edit')
    def create_organization(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new organization."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        org_id = data_store.organizations.create(data)
        return {
            'status': 201,
            'body': {'success': True, 'id': org_id, 'message': 'Organization created'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('organizations', 'edit')
    def update_organization(self, org_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Update an organization."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        success = data_store.organizations.update(org_id, data)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Organization updated' if success else 'Organization not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('organizations', 'delete')
    def delete_organization(self, org_id, request_context=None) -> Dict[str, Any]:
        """Delete an organization."""
        success = data_store.organizations.delete(org_id)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Organization deleted' if success else 'Organization not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }
