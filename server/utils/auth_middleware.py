import time
from functools import wraps
from server.utils.jwt_handler import jwt_handler
from server.utils.permissions import has_permission


def extract_user_from_request(request_context):
    headers = request_context.get('headers', {})
    if isinstance(headers, dict):
        auth_header = headers.get('Authorization', '') or headers.get('authorization', '')
    else:
        auth_header = headers.get('Authorization', '')

    if not auth_header or not auth_header.startswith('Bearer '):
        return None

    token = auth_header[7:]
    payload = jwt_handler.verify_token(token)
    return payload


def require_auth(handler_method):
    @wraps(handler_method)
    def wrapper(request_context, *args, **kwargs):
        user_payload = extract_user_from_request(request_context)

        if not user_payload:
            return {
                'status': 401,
                'body': {
                    'success': False,
                    'message': '认证失败，Token 无效或缺失',
                    'error': 'UNAUTHORIZED'
                },
                'headers': {'Content-Type': 'application/json'}
            }

        request_context['user'] = user_payload
        return handler_method(request_context, *args, **kwargs)

    return wrapper


def require_permission(permission):
    def decorator(handler_method):
        @wraps(handler_method)
        def wrapper(request_context, *args, **kwargs):
            user_payload = extract_user_from_request(request_context)

            if not user_payload:
                return {
                    'status': 401,
                    'body': {
                        'success': False,
                        'message': '认证失败，Token 无效或缺失',
                        'error': 'UNAUTHORIZED'
                    },
                    'headers': {'Content-Type': 'application/json'}
                }

            request_context['user'] = user_payload

            user_role = user_payload.get('role', 'viewer')
            if not has_permission(user_role, permission):
                return {
                    'status': 403,
                    'body': {
                        'success': False,
                        'message': f'权限不足，需要 {permission} 权限',
                        'error': 'FORBIDDEN',
                        'required_permission': permission,
                        'user_role': user_role
                    },
                    'headers': {'Content-Type': 'application/json'}
                }

            return handler_method(request_context, *args, **kwargs)

        return wrapper
    return decorator


class RateLimiter:
    def __init__(self, max_attempts=5, window_seconds=300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts = {}

    def _cleanup_expired(self, ip_address):
        if ip_address not in self._attempts:
            return
        current_time = time.time()
        self._attempts[ip_address] = [
            t for t in self._attempts[ip_address]
            if current_time - t < self.window_seconds
        ]
        if not self._attempts[ip_address]:
            del self._attempts[ip_address]

    def is_rate_limited(self, ip_address):
        self._cleanup_expired(ip_address)
        if ip_address not in self._attempts:
            return False
        return len(self._attempts[ip_address]) >= self.max_attempts

    def record_attempt(self, ip_address):
        if ip_address not in self._attempts:
            self._attempts[ip_address] = []
        self._attempts[ip_address].append(time.time())

    def reset(self, ip_address):
        self._attempts.pop(ip_address, None)


from server.config import LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS
login_rate_limiter = RateLimiter(max_attempts=LOGIN_MAX_ATTEMPTS, window_seconds=LOGIN_WINDOW_SECONDS)
