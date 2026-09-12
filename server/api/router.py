"""
API Router module for request dispatching.
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class APIRouter:
    """Main API router for dispatching requests to appropriate modules."""

    def __init__(self):
        """Initialize the API router with module routes."""
        self.routes = {}
        self._archive_router = None
        self._resources_router = None
        self._setup_routes()

    def _setup_routes(self):
        """Setup route mappings to handler modules."""
        try:
            from server.users.routes import UsersRouter
            self.routes['/api/users'] = UsersRouter()
        except ImportError as e:
            logger.warning(f"Users module not available: {e}")

        try:
            from server.auth.routes import AuthRouter
            self.routes['/api/auth'] = AuthRouter()
        except ImportError as e:
            logger.warning(f"Auth module not available: {e}")

        try:
            from server.permissions.routes import PermissionsRouter
            self.routes['/api/permissions'] = PermissionsRouter()
        except ImportError as e:
            logger.warning(f"Permissions module not available: {e}")

        try:
            from server.projects.routes import ProjectsRouter
            self.routes['/api/projects'] = ProjectsRouter()
        except ImportError as e:
            logger.warning(f"Projects module not available: {e}")

        try:
            from server.resources.routes import ResourcesRouter
            self._resources_router = ResourcesRouter()
            self.routes['/api/resources'] = self._resources_router
            for p in ('/api/list-files', '/api/upload', '/api/get-file',
                      '/api/delete-file', '/api/open-resource', '/api/open-folder'):
                self.routes[p] = self._resources_router
        except ImportError as e:
            logger.warning(f"Resources module not available: {e}")

        try:
            from server.organizations.routes import OrganizationsRouter
            self.routes['/api/organizations'] = OrganizationsRouter()
        except ImportError as e:
            logger.warning(f"Organizations module not available: {e}")

        try:
            from server.players.routes import PlayersRouter
            self.routes['/api/players'] = PlayersRouter()
        except ImportError as e:
            logger.warning(f"Players module not available: {e}")

        try:
            from server.finances.routes import FinancesRouter
            self.routes['/api/finances'] = FinancesRouter()
        except ImportError as e:
            logger.warning(f"Finances module not available: {e}")

        try:
            from server.knowledge.routes import KnowledgeRouter
            self.routes['/api/knowledge'] = KnowledgeRouter()
        except ImportError as e:
            logger.warning(f"Knowledge module not available: {e}")

        try:
            from server.search.routes import SearchRouter
            self.routes['/api/search'] = SearchRouter()
        except ImportError as e:
            logger.warning(f"Search module not available: {e}")

        try:
            from server.notifications.routes import NotificationsRouter
            self.routes['/api/notifications'] = NotificationsRouter()
        except ImportError as e:
            logger.warning(f"Notifications module not available: {e}")

        try:
            from server.system.routes import SystemRouter
            self._system_router = SystemRouter()
            for p in ('/api/status', '/api/browse-dirs', '/api/open-file',
                      '/api/preview-text', '/api/config/archive-path',
                      '/api/config/resources-path', '/api/audit-logs',
                      '/api/cleanup/scan', '/api/cleanup/execute',
                      '/api/save-stage-materials'):
                self.routes[p] = self._system_router
        except ImportError as e:
            logger.warning(f"System module not available: {e}")

        try:
            from server.materials.routes import MaterialsRouter
            self._materials_router = MaterialsRouter()
            for p in ('/api/scan-project-files', '/api/scan-org-files', '/api/scan-player-files',
                      '/api/download-project-material', '/api/download-player-material',
                      '/api/get-org-material', '/api/delete-project-material',
                      '/api/delete-org-material', '/api/delete-player-material',
                      '/api/import-players'):
                self.routes[p] = self._materials_router
        except ImportError as e:
            logger.warning(f"Materials module not available: {e}")

        try:
            from server.archive.routes import ArchiveRouter
            self._archive_router = ArchiveRouter()
        except ImportError as e:
            logger.warning(f"Archive module not available: {e}")

    def _is_archive_route(self, path: str) -> bool:
        """Check if path matches an archive API route.

        注意：/api/upload 与 /api/delete-file 被前端多个页面（资源中心、模板、
        归档、项目/机构/选手资料）复用，需要按字段/路径区分写入的资源目录还是
        归档目录，因此统一交给 ResourcesRouter 处理，不在此处截获。
        """
        archive_paths = [
            '/api/count-files', '/api/list-archives', '/api/open-archive',
            '/api/delete-folder', '/api/create-folder',
            '/api/rename-folder', '/api/file-icon'
        ]
        return path in archive_paths

    def route_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route request to appropriate module based on path.
        """
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        # Archive routes (exact path match)
        if self._is_archive_route(path) and self._archive_router:
            try:
                return self._archive_router.handle_request(request_context)
            except Exception as e:
                logger.error(f"Error in archive router: {e}")
                return {
                    'status': 500,
                    'body': {'error': 'Internal Server Error'},
                    'headers': {'Content-Type': 'application/json'}
                }

        # Data routes
        if path.startswith('/api/data/') and self._resources_router:
            try:
                return self._resources_router.handle_request(request_context)
            except Exception as e:
                logger.error(f"Error in resources router: {e}")
                return {
                    'status': 500,
                    'body': {'error': 'Internal Server Error'},
                    'headers': {'Content-Type': 'application/json'}
                }

        # Find matching route (prefix match)
        for base_path, router in self.routes.items():
            if path.startswith(base_path):
                try:
                    return router.handle_request(request_context)
                except Exception as e:
                    logger.error(f"Error in {base_path} router: {e}")
                    return {
                        'status': 500,
                        'body': {'error': 'Internal Server Error'},
                        'headers': {'Content-Type': 'application/json'}
                    }

        # No matching route found
        return {
            'status': 404,
            'body': {'error': 'Not Found'},
            'headers': {'Content-Type': 'application/json'}
        }
