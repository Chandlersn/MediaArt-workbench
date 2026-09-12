"""
Users API routes module.
Handles user CRUD operations.
"""

import json
import logging
import bcrypt
import uuid
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_auth, require_permission

logger = logging.getLogger(__name__)


def _generate_temp_password(length: int = 10) -> str:
    """生成一段可读的临时密码（用于「留空则自动生成」场景）。"""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class UsersRouter:
    """Router for user-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user-related requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path == '/api/users':
                return self.get_users(request_context)
            elif method == 'POST' and path == '/api/users/change-password':
                return self.change_password(request_context)
            elif method == 'POST' and path == '/api/users':
                return self.create_user(request_context)
            elif method == 'POST' and path.startswith('/api/users/') and path.endswith('/toggle-status'):
                user_id = path.split('/')[-2]
                return self.toggle_user_status(user_id, request_context)
            elif method == 'GET' and path.startswith('/api/users/'):
                user_id = path.split('/')[-1]
                return self.get_user(user_id, request_context)
            elif method == 'PUT' and path.startswith('/api/users/'):
                user_id = path.split('/')[-1]
                return self.update_user(user_id, request_context)
            elif method == 'DELETE' and path.startswith('/api/users/'):
                user_id = path.split('/')[-1]
                return self.delete_user(user_id, request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling user request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('users', 'view')
    def get_users(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get all users."""
        try:
            users = data_store.users.get_all(order_by='created_at DESC')
            for u in users:
                u.pop('password', None)
            return {
                'status': 200,
                'body': {'success': True, 'users': users},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('users', 'edit')
    def create_user(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        username = data.get('username', '')
        password = data.get('password', '')
        real_name = data.get('real_name', '') or data.get('realName', '')
        role = data.get('role', 'viewer')

        if not username:
            return {
                'status': 400,
                'body': {'success': False, 'message': 'Username is required'},
                'headers': {'Content-Type': 'application/json'}
            }

        existing = data_store.users.find_one("username = ?", (username,))
        if existing:
            return {
                'status': 409,
                'body': {'success': False, 'message': 'Username already exists'},
                'headers': {'Content-Type': 'application/json'}
            }

        # 密码留空则自动生成一段临时密码，仅此一次回传（initialPassword）
        generated_password = None
        if not password:
            password = _generate_temp_password()
            generated_password = password

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        user_id = str(uuid.uuid4())
        data_store.users.create({
            'id': user_id,
            'username': username,
            'password': hashed_password,
            'real_name': real_name,
            'role': role,
            'is_active': 1
        })

        created = data_store.users.get_by_id(user_id)
        created.pop('password', None)
        body = {'success': True, 'message': 'User created', 'id': user_id, 'user': created}
        if generated_password:
            body['initialPassword'] = generated_password
        return {
            'status': 201,
            'body': body,
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('users', 'view')
    def get_user(self, user_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get a specific user by ID."""
        user = data_store.users.get_by_id(user_id)
        if not user:
            return {
                'status': 404,
                'body': {'success': False, 'message': 'User not found'},
                'headers': {'Content-Type': 'application/json'}
            }
        user.pop('password', None)
        return {
            'status': 200,
            'body': {'success': True, 'user': user},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('users', 'edit')
    def update_user(self, user_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Update a user."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        user = data_store.users.get_by_id(user_id)
        if not user:
            return {
                'status': 404,
                'body': {'success': False, 'message': 'User not found'},
                'headers': {'Content-Type': 'application/json'}
            }

        def _first(d, *keys, default=None):
            for k in keys:
                if k in d and d[k] is not None:
                    return d[k]
            return default

        real_name = _first(data, 'real_name', 'realName')
        email = _first(data, 'email')
        role = _first(data, 'role')
        is_active = _first(data, 'is_active', 'isActive')
        password = data.get('password')

        update_data = {}
        if real_name is not None:
            update_data['real_name'] = real_name
        if email is not None:
            update_data['email'] = email
        if role is not None:
            update_data['role'] = role
        if is_active is not None:
            update_data['is_active'] = int(is_active)
        if password:
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            update_data['password'] = hashed

        if update_data:
            data_store.users.update(user_id, update_data)

        updated = data_store.users.get_by_id(user_id)
        updated.pop('password', None)
        return {
            'status': 200,
            'body': {'success': True, 'message': 'User updated', 'user': updated},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_auth
    def change_password(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """修改密码（自助）。前端 LoginModal 在「需修改密码」流程中调用。"""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        new_password = data.get('newPassword') or data.get('password') or ''
        if len(new_password) < 6:
            return {
                'status': 400,
                'body': {'success': False, 'message': '密码长度至少6位'},
                'headers': {'Content-Type': 'application/json'}
            }
        user = request_context.get('user', {}) or {}
        user_id = data.get('userId') or user.get('user_id')
        target = data_store.users.get_by_id(user_id) if user_id else None
        if not target:
            return {
                'status': 404,
                'body': {'success': False, 'message': '用户不存在'},
                'headers': {'Content-Type': 'application/json'}
            }
        hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        data_store.users.update(user_id, {'password': hashed})
        return {
            'status': 200,
            'body': {'success': True, 'message': '密码已修改'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('users', 'edit')
    def toggle_user_status(self, user_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """启用/停用用户（is_active 列持久化）。"""
        target = data_store.users.get_by_id(user_id)
        if not target:
            return {
                'status': 404,
                'body': {'success': False, 'message': 'User not found'},
                'headers': {'Content-Type': 'application/json'}
            }
        # Model 读出的字典键为驼峰（isActive 等），注意字段名
        _ia = target.get('isActive')
        if _ia is None:
            _ia = target.get('is_active', 1)
        if _ia is None:
            _ia = 1
        current = int(_ia)
        new_status = 0 if current else 1
        data_store.users.update(user_id, {'is_active': new_status})
        return {
            'status': 200,
            'body': {'success': True, 'status': new_status,
                     'message': '已启用' if new_status else '已停用'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('users', 'delete')
    def delete_user(self, user_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a user."""
        user = data_store.users.get_by_id(user_id)
        if not user:
            return {
                'status': 404,
                'body': {'success': False, 'message': 'User not found'},
                'headers': {'Content-Type': 'application/json'}
            }

        data_store.users.delete(user_id)
        return {
            'status': 200,
            'body': {'success': True, 'message': 'User deleted'},
            'headers': {'Content-Type': 'application/json'}
        }
