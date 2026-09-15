"""
Projects API routes module.
"""

import logging
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_permission

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
            if method == 'GET' and path in ('/api/projects', '/api/projects/list'):
                return self.list_projects(request_context)
            elif method == 'GET' and path.startswith('/api/projects/'):
                project_id = path.split('/')[-1]
                return self.get_project(project_id, request_context)
            # ⚠️ 写入已统一走 POST /api/data/save（全量快照，见前端 dataService.save）。
            #    此前的 POST/PUT/DELETE /api/projects 前端从未调用，属第二套并行写
            #    路径，已退役——避免"同一份数据两处可写、改一处不影响另一处"。
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed',
                             'message': '写入请使用 POST /api/data/save'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling project request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('projects', 'view')
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

    @require_permission('projects', 'view')
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

    # 写入方法（create/update/delete_project）已随第二套写路径退役，
    # 统一走 POST /api/data/save → data_store.save_all_data。
