"""
JWT Token 处理模块
提供 JWT Token 生成、验证、刷新功能
"""
import jwt
import os
import time
import threading
import json
import secrets
from functools import wraps
from datetime import datetime, timedelta


class JWTHandler:
    """JWT Token 处理器"""

    def __init__(self, secret_key=None, algorithm='HS256', expires_in=7200):
        """
        初始化 JWT 处理器

        Args:
            secret_key: JWT 密钥，如果不提供则自动生成
            algorithm: 加密算法，默认 HS256
            expires_in: Token 有效期（秒），默认 2 小时。
                       必须与 refresh token（7 天）拉开差距，否则刷新机制失去意义。
        """
        self.algorithm = algorithm
        self.expires_in = expires_in
        self.secret_key = secret_key or self._get_or_create_secret_key()
        self._blacklist = set()
        self._blacklist_lock = threading.Lock()

    def _get_or_create_secret_key(self):
        """
        获取或创建 JWT 密钥。

        优先级：
        1. 环境变量 WORKBENCH_JWT_SECRET（推荐，密钥不落盘）
        2. 密钥文件 .jwt_secret（隐藏文件，权限 600）

        安全说明：旧的明文 jwt_config.json 会被**忽略**（不再读取），
        从而强制轮换密钥——因为该文件曾随 data 目录暴露，且服务默认监听 0.0.0.0。
        程序不自动删除该文件，仅提示人工清理，避免在启动流程中执行破坏性操作。
        """
        env_secret = os.environ.get('WORKBENCH_JWT_SECRET')
        if env_secret:
            return env_secret

        config_dir = os.environ.get('WORKBENCH_DATA_DIR') or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        config_file = os.path.join(config_dir, '.jwt_secret')

        # 确保目录存在
        os.makedirs(config_dir, exist_ok=True)

        # 旧的明文密钥文件一律不再读取（触发轮换），但不在此处删除
        legacy_file = os.path.join(config_dir, 'jwt_config.json')
        if os.path.exists(legacy_file):
            print("[SECURITY] 检测到旧的明文密钥文件 jwt_config.json，已忽略该文件并轮换密钥；"
                  "建议人工删除该文件以彻底清除历史明文密钥")

        # 尝试读取现有密钥
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if config.get('secret_key'):
                        return config['secret_key']
            except Exception as e:
                print(f"读取 JWT 配置失败: {e}")

        # 生成新密钥
        secret_key = secrets.token_urlsafe(64)

        # 保存密钥到配置文件
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'secret_key': secret_key,
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(config_file, 0o600)
            except OSError:
                pass
            print(f"JWT 密钥已生成并保存到: {config_file}")
        except Exception as e:
            print(f"保存 JWT 配置失败: {e}")

        return secret_key

    def generate_token(self, user_id, username, role='viewer', expires_in=None):
        """
        生成 JWT Token

        Args:
            user_id: 用户ID
            username: 用户名
            role: 用户角色
            expires_in: 过期时间（秒），如果不提供则使用默认值

        Returns:
            str: JWT Token
        """
        if expires_in is None:
            expires_in = self.expires_in

        payload = {
            'user_id': user_id,
            'username': username,
            'role': role,
            'iat': int(time.time()),  # 签发时间
            'exp': int(time.time()) + expires_in,  # 过期时间
            'type': 'access'  # Token 类型
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def generate_refresh_token(self, user_id, username):
        """
        生成刷新 Token（有效期 7 天）

        Args:
            user_id: 用户ID
            username: 用户名

        Returns:
            str: Refresh Token
        """
        payload = {
            'user_id': user_id,
            'username': username,
            'iat': int(time.time()),
            'exp': int(time.time()) + 604800,  # 7 天
            'type': 'refresh'
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token):
        """
        验证 JWT Token

        Args:
            token: JWT Token

        Returns:
            dict: 解码后的 payload，如果验证失败返回 None
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            if self.is_revoked(token):
                print("Token 已被撤销")
                return None
                
            return payload
        except jwt.ExpiredSignatureError:
            print("Token 已过期")
            return None
        except jwt.InvalidTokenError as e:
            print(f"Token 无效: {e}")
            return None

    def refresh_token(self, refresh_token):
        """
        使用刷新 Token 生成新的访问 Token

        Args:
            refresh_token: 刷新 Token

        Returns:
            str: 新的访问 Token，如果失败返回 None
        """
        payload = self.verify_token(refresh_token)

        if not payload:
            return None

        if payload.get('type') != 'refresh':
            print("不是刷新 Token")
            return None

        # 生成新的访问 Token
        new_token = self.generate_token(
            user_id=payload['user_id'],
            username=payload['username'],
            role=payload.get('role', 'viewer')
        )

        return new_token

    def revoke_token(self, token):
        """将 Token 加入黑名单"""
        payload = self.decode_token_without_verification(token)
        if payload:
            token_id = str(payload.get('iat', 0)) + '_' + str(payload.get('user_id', ''))
            with self._blacklist_lock:
                self._blacklist.add(token_id)

    def is_revoked(self, token):
        """检查 Token 是否已被撤销"""
        payload = self.decode_token_without_verification(token)
        if not payload:
            return True
        token_id = str(payload.get('iat', 0)) + '_' + str(payload.get('user_id', ''))
        with self._blacklist_lock:
            return token_id in self._blacklist

    def clear_expired_blacklist(self):
        """清理过期的黑名单条目（超过7天的）"""
        current_time = int(time.time())
        with self._blacklist_lock:
            expired = set()
            for entry in self._blacklist:
                try:
                    iat = int(entry.split('_')[0]) if '_' in entry else 0
                    if current_time - iat > 604800:
                        expired.add(entry)
                except (ValueError, IndexError):
                    expired.add(entry)
            self._blacklist -= expired

    def decode_token_without_verification(self, token):
        """
        不验证签名直接解码 Token（仅用于获取过期 Token 的信息）

        Args:
            token: JWT Token

        Returns:
            dict: 解码后的 payload
        """
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload
        except Exception as e:
            print(f"解码 Token 失败: {e}")
            return None


# 全局 JWT 处理器实例
jwt_handler = JWTHandler()


def require_auth(handler_method):
    """
    认证装饰器，用于保护需要认证的 API 接口

    用法:
        @require_auth
        def protected_api(self):
            user = get_current_user(self)
            # ...
    """
    @wraps(handler_method)
    def wrapper(self, *args, **kwargs):
        # 从请求头获取 Token
        auth_header = self.headers.get('Authorization', '')

        if not auth_header:
            self.send_response(401)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': '缺少认证信息',
                'error': 'MISSING_TOKEN'
            }, ensure_ascii=False).encode())
            return

        # 解析 Bearer Token
        if not auth_header.startswith('Bearer '):
            self.send_response(401)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': '认证格式错误',
                'error': 'INVALID_TOKEN_FORMAT'
            }, ensure_ascii=False).encode())
            return

        token = auth_header[7:]  # 去掉 'Bearer ' 前缀

        # 验证 Token
        payload = jwt_handler.verify_token(token)

        if not payload:
            self.send_response(401)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': 'Token 无效或已过期',
                'error': 'INVALID_OR_EXPIRED_TOKEN'
            }, ensure_ascii=False).encode())
            return

        # 将用户信息存储到请求对象中
        self.user_payload = payload

        # 调用原始处理方法
        return handler_method(self, *args, **kwargs)

    return wrapper


def get_current_user(request_handler):
    """
    从请求处理器中获取当前用户信息

    Args:
        request_handler: HTTP 请求处理器实例

    Returns:
        dict: 用户信息，包含 user_id, username, role 等
    """
    return getattr(request_handler, 'user_payload', None)


def create_token_response(user_id, username, role='viewer'):
    """
    创建包含 Token 的响应数据

    Args:
        user_id: 用户ID
        username: 用户名
        role: 用户角色

    Returns:
        dict: 包含 access_token 和 refresh_token 的响应数据
    """
    access_token = jwt_handler.generate_token(user_id, username, role)
    refresh_token = jwt_handler.generate_refresh_token(user_id, username)

    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'Bearer',
        'expires_in': jwt_handler.expires_in
    }
