"""
Permissions API routes module.

提供角色-权限矩阵的读取与保存，以及当前用户的有效权限查询：
  - GET  /api/permissions        模块/动作定义 + 当前矩阵（前端初始化用）
  - GET  /api/permissions/roles  当前角色矩阵
  - PUT  /api/permissions/roles  保存矩阵（需 users:edit，即管理员）
  - GET  /api/permissions/me     当前登录用户的有效权限
"""

import json
import logging
from typing import Dict, Any

from server.utils.permissions import (
    MODULES, ACTIONS, MODULE_LABELS, ACTION_LABELS, ROLE_DISPLAY_NAMES,
    get_role_matrix, save_role_matrix, reload_role_matrix,
    get_user_effective_permissions, has_permission,
)
from server.utils.auth_middleware import extract_user_from_request

logger = logging.getLogger(__name__)


class PermissionsRouter:
    """Router for permission-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path == '/api/permissions':
                return self.get_permissions_meta(request_context)
            elif method == 'GET' and path == '/api/permissions/roles':
                return self.get_roles(request_context)
            elif method == 'PUT' and path == '/api/permissions/roles':
                return self.update_roles(request_context)
            elif method == 'GET' and path == '/api/permissions/me':
                return self.get_my_permissions(request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling permission request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    def _matrix_payload(self) -> Dict[str, Any]:
        return {
            'modules': MODULES,
            'actions': ACTIONS,
            'module_labels': MODULE_LABELS,
            'action_labels': ACTION_LABELS,
            'role_labels': ROLE_DISPLAY_NAMES,
            'roles': get_role_matrix(),
        }

    def get_permissions_meta(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """模块/动作定义 + 当前矩阵。"""
        payload = self._matrix_payload()
        payload['success'] = True
        return {'status': 200, 'body': payload, 'headers': {'Content-Type': 'application/json'}}

    def get_roles(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """返回当前角色矩阵。"""
        return {
            'status': 200,
            'body': {'success': True, **self._matrix_payload()},
            'headers': {'Content-Type': 'application/json'}
        }

    def update_roles(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """保存角色矩阵（需 users:edit）。"""
        user = extract_user_from_request(request_context)
        if not user:
            return {
                'status': 401,
                'body': {'success': False, 'message': '认证失败', 'error': 'UNAUTHORIZED'},
                'headers': {'Content-Type': 'application/json'}
            }
        if not has_permission(user.get('role', 'viewer'), 'users', 'edit'):
            return {
                'status': 403,
                'body': {'success': False, 'message': '权限不足，需要 users:edit 权限', 'error': 'FORBIDDEN'},
                'headers': {'Content-Type': 'application/json'}
            }

        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        matrix = data.get('roles') or data.get('matrix')
        if not matrix:
            return {
                'status': 400,
                'body': {'success': False, 'message': '缺少 roles 字段'},
                'headers': {'Content-Type': 'application/json'}
            }

        # 始终保证 admin 拥有全部权限，避免误锁死管理员
        from server.utils.permissions import ACTIONS, MODULES
        matrix['admin'] = {m: list(ACTIONS) for m in MODULES}

        if not save_role_matrix(matrix):
            return {
                'status': 400,
                'body': {'success': False, 'message': '矩阵格式非法，保存失败'},
                'headers': {'Content-Type': 'application/json'}
            }
        reload_role_matrix()
        return {
            'status': 200,
            'body': {'success': True, 'message': '权限矩阵已保存', **self._matrix_payload()},
            'headers': {'Content-Type': 'application/json'}
        }

    def get_my_permissions(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """返回当前登录用户的有效权限。"""
        user = extract_user_from_request(request_context)
        if not user:
            return {
                'status': 401,
                'body': {'success': False, 'message': '认证失败', 'error': 'UNAUTHORIZED'},
                'headers': {'Content-Type': 'application/json'}
            }
        role = user.get('role', 'viewer')
        return {
            'status': 200,
            'body': {
                'success': True,
                'role': role,
                'role_label': ROLE_DISPLAY_NAMES.get(role, role),
                'permissions': get_user_effective_permissions(role),
            },
            'headers': {'Content-Type': 'application/json'}
        }
