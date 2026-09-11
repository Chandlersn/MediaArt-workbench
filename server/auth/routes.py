"""
Auth API routes module.
Handles login, register, token refresh, and logout.
"""

import json
import logging
import bcrypt
from typing import Dict, Any
from server.database.store import data_store
from server.utils.jwt_handler import jwt_handler
from server.utils.auth_middleware import login_rate_limiter, extract_user_from_request

logger = logging.getLogger(__name__)


class AuthRouter:
    """Router for authentication-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle authentication requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'POST' and path == '/api/auth/login':
                return self.login(request_context)
            elif method == 'POST' and path == '/api/auth/register':
                return self.register(request_context)
            elif method == 'POST' and path == '/api/auth/refresh':
                return self.refresh_token(request_context)
            elif method == 'POST' and path == '/api/auth/logout':
                return self.logout(request_context)
            elif method == 'GET' and path == '/api/auth/me':
                return self.get_current_user(request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling auth request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    def _generate_tokens(self, user_id: str, username: str, role: str) -> Dict[str, str]:
        """Generate access and refresh tokens using the unified JWT handler."""
        access_token = jwt_handler.generate_token(user_id, username, role)
        refresh_token = jwt_handler.generate_refresh_token(user_id, username)
        return {
            'access_token': access_token,
            'refresh_token': refresh_token
        }

    def _verify_token(self, token: str, token_type: str = 'access') -> Dict:
        """Verify a JWT token using the unified JWT handler."""
        payload = jwt_handler.verify_token(token)
        if not payload:
            raise Exception('Token has expired or is invalid')
        if payload.get('type') != token_type:
            raise Exception('Invalid token type')
        return payload

    def _get_token_from_headers(self, headers: Dict) -> str:
        """Extract token from Authorization header."""
        auth_header = headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:]
        return ''

    def login(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user login."""
        client_address = request_context.get('client_address', ('127.0.0.1',))
        client_ip = client_address[0] if isinstance(client_address, (tuple, list)) else str(client_address)

        if login_rate_limiter.is_rate_limited(client_ip):
            return {
                'status': 429,
                'body': {'success': False, 'message': '登录尝试过于频繁，请5分钟后再试', 'error': 'RATE_LIMITED'},
                'headers': {'Content-Type': 'application/json'}
            }

        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        username = data.get('username', '')
        password = data.get('password', '')

        if not username or not password:
            return {
                'status': 400,
                'body': {'success': False, 'message': 'Username and password are required'},
                'headers': {'Content-Type': 'application/json'}
            }

        # Find user in database
        user = data_store.users.find_one("username = ?", (username,))

        if not user:
            login_rate_limiter.record_attempt(client_ip)
            return {
                'status': 401,
                'body': {'success': False, 'message': 'Invalid username or password'},
                'headers': {'Content-Type': 'application/json'}
            }

        # Verify password
        import base64
        stored_password = user.get('password', '')

        # Try Base64 decode first (legacy encoding)
        try:
            decoded = base64.b64decode(stored_password).decode('utf-8')
            if decoded.startswith('$2'):
                stored_password = decoded
        except Exception:
            pass  # Not Base64 encoded

        if not stored_password.startswith('$2'):
            # Plain text password (legacy)
            if password != stored_password:
                login_rate_limiter.record_attempt(client_ip)
                return {
                    'status': 401,
                    'body': {'success': False, 'message': 'Invalid username or password'},
                    'headers': {'Content-Type': 'application/json'}
                }
        else:
            # Hashed password
            if not bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
                login_rate_limiter.record_attempt(client_ip)
                return {
                    'status': 401,
                    'body': {'success': False, 'message': 'Invalid username or password'},
                    'headers': {'Content-Type': 'application/json'}
                }

        login_rate_limiter.reset(client_ip)

        # Generate tokens
        tokens = self._generate_tokens(
            user.get('id', ''),
            user.get('username', ''),
            user.get('role', 'viewer')
        )

        return {
            'status': 200,
            'body': {
                'success': True,
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'user': {
                    'id': user.get('id'),
                    'username': user.get('username'),
                    'role': user.get('role'),
                    'real_name': user.get('real_name')
                }
            },
            'headers': {'Content-Type': 'application/json'}
        }

    def register(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user registration."""
        user_payload = extract_user_from_request(request_context)
        if not user_payload:
            return {
                'status': 401,
                'body': {'success': False, 'message': '认证失败', 'error': 'UNAUTHORIZED'},
                'headers': {'Content-Type': 'application/json'}
            }

        from server.utils.permissions import has_permission
        if not has_permission(user_payload.get('role', 'viewer'), 'manage_users'):
            return {
                'status': 403,
                'body': {'success': False, 'message': '权限不足，需要管理用户权限', 'error': 'FORBIDDEN'},
                'headers': {'Content-Type': 'application/json'}
            }

        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        username = data.get('username', '')
        password = data.get('password', '')
        real_name = data.get('real_name', '')

        if not username or not password:
            return {
                'status': 400,
                'body': {'success': False, 'message': 'Username and password are required'},
                'headers': {'Content-Type': 'application/json'}
            }

        # Check if user already exists
        existing = data_store.users.find_one("username = ?", (username,))
        if existing:
            return {
                'status': 409,
                'body': {'success': False, 'message': 'Username already exists'},
                'headers': {'Content-Type': 'application/json'}
            }

        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Create user
        import uuid
        user_id = str(uuid.uuid4())
        data_store.users.create({
            'id': user_id,
            'username': username,
            'password': hashed_password,
            'real_name': real_name,
            'role': 'viewer'
        })

        return {
            'status': 201,
            'body': {'success': True, 'message': 'User registered successfully'},
            'headers': {'Content-Type': 'application/json'}
        }

    def refresh_token(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        refresh_token = data.get('refresh_token', '')

        if not refresh_token:
            return {
                'status': 400,
                'body': {'success': False, 'message': 'Refresh token is required'},
                'headers': {'Content-Type': 'application/json'}
            }

        try:
            payload = self._verify_token(refresh_token, 'refresh')
            user_id = payload.get('user_id')
            username = payload.get('username')

            # Get user from database
            user = data_store.users.get_by_id(user_id)
            if not user:
                raise Exception('User not found')

            # Generate new tokens
            tokens = self._generate_tokens(
                user_id,
                username,
                user.get('role', 'viewer')
            )

            jwt_handler.revoke_token(refresh_token)

            return {
                'status': 200,
                'body': {
                    'success': True,
                    'access_token': tokens['access_token'],
                    'refresh_token': tokens['refresh_token']
                },
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 401,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    def logout(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        headers = request_context.get('headers', {})
        auth_header = headers.get('Authorization', '') or headers.get('authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            jwt_handler.revoke_token(token)
        return {
            'status': 200,
            'body': {'success': True, 'message': 'Logged out successfully'},
            'headers': {'Content-Type': 'application/json'}
        }

    def get_current_user(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get current authenticated user."""
        user_payload = extract_user_from_request(request_context)

        if not user_payload:
            return {
                'status': 401,
                'body': {'success': False, 'message': '认证失败', 'error': 'UNAUTHORIZED'},
                'headers': {'Content-Type': 'application/json'}
            }

        user_id = user_payload.get('user_id')
        user = data_store.users.get_by_id(user_id)
        if not user:
            return {
                'status': 401,
                'body': {'success': False, 'message': 'User not found'},
                'headers': {'Content-Type': 'application/json'}
            }

        return {
            'status': 200,
            'body': {
                'success': True,
                'user': {
                    'id': user.get('id'),
                    'username': user.get('username'),
                    'role': user.get('role'),
                    'real_name': user.get('real_name')
                }
            },
            'headers': {'Content-Type': 'application/json'}
        }
