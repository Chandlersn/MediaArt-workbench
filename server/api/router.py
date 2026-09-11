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
            from server.archive.routes import ArchiveRouter
            self._archive_router = ArchiveRouter()
        except ImportError as e:
            logger.warning(f"Archive module not available: {e}")

    def _is_archive_route(self, path: str) -> bool:
        """Check if path matches an archive API route."""
        archive_paths = [
            '/api/count-files', '/api/list-archives', '/api/open-archive',
            '/api/delete-file', '/api/delete-folder', '/api/create-folder',
            '/api/upload', '/api/rename-folder', '/api/file-icon'
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
