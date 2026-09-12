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


def _split_handler_args(args):
    """兼容两种被装饰函数形态，定位 request_context 并还原调用参数。

    历史背景：这些装饰器最初是按「模块级函数 handler(request_context, ...)」写的，
    首参即 request_context。但各 Router 普遍把它套在**实例方法**上
    （如 get_users(self, request_context) / get_user(self, user_id, request_context)），
    此时 Python 描述符会在最前面插入 self，导致 self 被当成 request_context，
    触发 'XRouter' object has no attribute 'get' 之类的 500。

    这里用「参数里那个 dict 就是 request_context」这一稳定约定来定位它：
      - 纯函数：      (rc)                     -> self=None
      - 简单方法：    (self, rc)               -> self=args[0]
      - 带参方法：    (self, user_id, rc)      -> self=args[0]，前置位置参数=(user_id,)

    返回 (self_obj, request_context, pre_args, post_args)。
    """
    rc_idx = None
    for i, a in enumerate(args):
        if isinstance(a, dict):
            rc_idx = i
            break

    if rc_idx is None:
        # 找不到上下文，保持旧行为（交给调用方按纯函数处理，通常会得到 401）
        return None, (args[0] if args else {}), (), ()

    if rc_idx == 0:
        return None, args[0], (), args[1:]

    # rc_idx > 0：说明前面至少有一个非 dict 位置参数，第一个即 self（实例方法形态）
    return args[0], args[rc_idx], args[1:rc_idx], args[rc_idx + 1:]


def _unauthorized():
    return {
        'status': 401,
        'body': {
            'success': False,
            'message': '认证失败，Token 无效或缺失',
            'error': 'UNAUTHORIZED'
        },
        'headers': {'Content-Type': 'application/json'}
    }


def require_auth(handler_method):
    @wraps(handler_method)
    def wrapper(*args, **kwargs):
        self_obj, request_context, pre, post = _split_handler_args(args)

        user_payload = extract_user_from_request(request_context)
        if not user_payload:
            return _unauthorized()

        request_context['user'] = user_payload

        if self_obj is None:
            return handler_method(request_context, *pre, *post, **kwargs)
        return handler_method(self_obj, *pre, request_context, *post, **kwargs)

    return wrapper


def require_permission(module, action=None):
    """权限校验装饰器。

    两种用法等价：
      @require_permission('projects', 'edit')
      @require_permission('projects:edit')
    admin 恒通过；未认证返回 401；权限不足返回 403。
    """
    def decorator(handler_method):
        @wraps(handler_method)
        def wrapper(*args, **kwargs):
            self_obj, request_context, pre, post = _split_handler_args(args)

            user_payload = extract_user_from_request(request_context)
            if not user_payload:
                return _unauthorized()

            request_context['user'] = user_payload

            user_role = user_payload.get('role', 'viewer')
            if not has_permission(user_role, module, action):
                perm_label = f'{module}:{action}' if action else module
                return {
                    'status': 403,
                    'body': {
                        'success': False,
                        'message': f'权限不足，需要 {perm_label} 权限',
                        'error': 'FORBIDDEN',
                        'required_permission': perm_label,
                        'user_role': user_role
                    },
                    'headers': {'Content-Type': 'application/json'}
                }

            if self_obj is None:
                return handler_method(request_context, *pre, *post, **kwargs)
            return handler_method(self_obj, *pre, request_context, *post, **kwargs)

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
