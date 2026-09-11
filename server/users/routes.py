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


class UsersRouter:
    """Router for user-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user-related requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path == '/api/users':
                return self.get_users(request_context)
            elif method == 'POST' and path == '/api/users':
                return self.create_user(request_context)
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

    @require_permission('manage_users')
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

    @require_permission('manage_users')
    def create_user(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        username = data.get('username', '')
        password = data.get('password', '')
        real_name = data.get('real_name', '')
        role = data.get('role', 'viewer')

        if not username or not password:
            return {
                'status': 400,
                'body': {'success': False, 'message': 'Username and password are required'},
                'headers': {'Content-Type': 'application/json'}
            }

        existing = data_store.users.find_one("username = ?", (username,))
        if existing:
            return {
                'status': 409,
                'body': {'success': False, 'message': 'Username already exists'},
                'headers': {'Content-Type': 'application/json'}
            }

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        user_id = str(uuid.uuid4())
        data_store.users.create({
            'id': user_id,
            'username': username,
            'password': hashed_password,
            'real_name': real_name,
            'role': role
        })

        return {
            'status': 201,
            'body': {'success': True, 'message': 'User created', 'id': user_id},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_auth
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

    @require_permission('manage_users')
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

        update_data = {}
        if 'real_name' in data:
            update_data['real_name'] = data['real_name']
        if 'role' in data:
            update_data['role'] = data['role']
        if 'password' in data and data['password']:
            hashed = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            update_data['password'] = hashed

        if update_data:
            data_store.users.update(user_id, update_data)

        return {
            'status': 200,
            'body': {'success': True, 'message': 'User updated'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('manage_users')
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
