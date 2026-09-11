"""
Projects API routes module.
"""

import json
import logging
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_auth, require_permission

logger = logging.getLogger(__name__)


class ProjectsRouter:
    """Router for project-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle project-related requests.

        Args:
            request_context: Dictionary containing request details

        Returns:
            Dictionary containing response data
        """
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path == '/api/projects/list':
                return self.list_projects(request_context)
            elif method == 'GET' and path.startswith('/api/projects/'):
                project_id = path.split('/')[-1]
                return self.get_project(project_id, request_context)
            elif method == 'POST' and path == '/api/projects':
                return self.create_project(request_context)
            elif method == 'PUT' and path.startswith('/api/projects/'):
                project_id = path.split('/')[-1]
                return self.update_project(project_id, request_context)
            elif method == 'DELETE' and path.startswith('/api/projects/'):
                project_id = path.split('/')[-1]
                return self.delete_project(project_id, request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling project request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_auth
    def list_projects(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get all projects with pagination."""
        query_params = request_context.get('query_params', {})
        page = int(query_params.get('page', [1])[0])
        page_size = int(query_params.get('pageSize', [10])[0])
        search = query_params.get('search', [''])[0]
        status_filter = query_params.get('status', ['all'])[0]

        all_projects = data_store.projects.get_all(order_by='created_at DESC')

        # Apply search filter
        if search:
            search_lower = search[0].lower() if isinstance(search, list) else search.lower()
            all_projects = [p for p in all_projects if search_lower in p.get('name', '').lower()]

        # Apply status filter
        if status_filter and status_filter != 'all':
            all_projects = [p for p in all_projects if p.get('status') == status_filter]

        total = len(all_projects)
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Pagination
        offset = (page - 1) * page_size
        paginated = all_projects[offset:offset + page_size]

        return {
            'status': 200,
            'body': {
                'success': True,
                'data': paginated,
                'total': total,
                'totalPages': total_pages,
                'page': page,
                'pageSize': page_size
            },
            'headers': {'Content-Type': 'application/json'}
        }

    @require_auth
    def get_project(self, project_id, request_context=None):
        """Get a specific project by ID."""
        project = data_store.projects.get_by_id(project_id)
        if project:
            return {
                'status': 200,
                'body': {'success': True, 'data': project},
                'headers': {'Content-Type': 'application/json'}
            }
        return {
            'status': 404,
            'body': {'success': False, 'message': 'Project not found'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('create')
    def create_project(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new project."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        project_id = data_store.projects.create(data)
        return {
            'status': 201,
            'body': {'success': True, 'id': project_id, 'message': 'Project created'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('update')
    def update_project(self, project_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Update a project."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        success = data_store.projects.update(project_id, data)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Project updated' if success else 'Project not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('delete')
    def delete_project(self, project_id, request_context=None):
        """Delete a project."""
        success = data_store.projects.delete(project_id)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Project deleted' if success else 'Project not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }
