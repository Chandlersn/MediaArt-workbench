# -*- coding: utf-8 -*-
"""
Base Handler - 公共方法和辅助函数
"""
import os
import json
import hashlib
import gzip
import mimetypes
from io import BytesIO
from http.server import SimpleHTTPRequestHandler
from urllib.parse import unquote

from server.utils import jwt_handler, has_permission

# 全局配置（从 server.py 导入）
GZIP_MIN_SIZE = 1024
GZIP_TYPES = {
    'text/html', 'text/css', 'text/javascript',
    'application/javascript', 'application/json',
    'text/json', 'text/plain', 'application/xml',
    'text/xml', 'image/svg+xml'
}
CACHE_STATIC_MAX_AGE = 31536000


class BaseHandler(SimpleHTTPRequestHandler):
    """基础 Handler 类，包含公共方法"""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def generate_etag(self, content):
        """生成 ETag"""
        return hashlib.md5(content).hexdigest()

    def should_compress(self, content_type, content_length):
        """判断是否应该压缩"""
        if not content_type:
            return False
        main_type = content_type.split(';')[0].strip().lower()
        if main_type not in GZIP_TYPES:
            return False
        if content_length < GZIP_MIN_SIZE:
            return False
        return True

    def compress_content(self, content):
        """使用 gzip 压缩内容"""
        if isinstance(content, str):
            content = content.encode('utf-8')
        compressed = BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode='wb') as f:
            f.write(content)
        return compressed.getvalue()

    def add_cache_headers(self, content_type, content=None):
        """添加缓存相关头部"""
        main_type = content_type.split(';')[0].strip().lower() if content_type else ''

        if main_type == 'text/html':
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        elif main_type in ['text/css', 'text/javascript', 'application/javascript']:
            self.send_header('Cache-Control', f'public, max-age={CACHE_STATIC_MAX_AGE}')
            if content:
                etag = self.generate_etag(content if isinstance(content, bytes) else content.encode('utf-8'))
                self.send_header('ETag', f'"{etag}"')
        elif main_type.startswith('image/') or main_type in ['font/woff', 'font/woff2']:
            self.send_header('Cache-Control', f'public, max-age={CACHE_STATIC_MAX_AGE}')
            if content:
                etag = self.generate_etag(content if isinstance(content, bytes) else content.encode('utf-8'))
                self.send_header('ETag', f'"{etag}"')
        elif main_type == 'application/json':
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        else:
            self.send_header('Cache-Control', 'public, max-age=3600')

    def send_error(self, code, message=None):
        """重写 send_error 方法以支持中文错误信息"""
        try:
            self.send_response(code)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            if message:
                error_msg = json.dumps({
                    'success': False,
                    'error': str(code),
                    'message': str(message)
                }, ensure_ascii=False)
                self.wfile.write(error_msg.encode('utf-8'))
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def send_json_response(self, data, status=200):
        """发送 JSON 响应"""
        try:
            self.send_response(status)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def log_message(self, format, *args):
        """重写日志方法以支持中文"""
        try:
            print("%s - - [%s] %s" %
                  (self.address_string(),
                   self.log_date_time_string(),
                   format % args))
        except UnicodeEncodeError:
            print("%s - - [%s] %s" %
                  (self.address_string(),
                   self.log_date_time_string(),
                   (format % args).encode('utf-8', errors='replace').decode('utf-8')))

    def end_headers(self):
        """添加 CORS 头"""
        try:
            self.send_header('Access-Control-Allow-Origin', '*')
            super().end_headers()
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def serve_static_file(self, file_path):
        """提供静态文件服务（支持压缩和缓存）"""
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            with open(file_path, 'rb') as f:
                content = f.read()

            accept_encoding = self.headers.get('Accept-Encoding', '')
            supports_gzip = 'gzip' in accept_encoding
            should_compress = supports_gzip and self.should_compress(mime_type, len(content))

            if should_compress:
                response_content = self.compress_content(content)
            else:
                response_content = content

            self.send_response(200)
            self.send_header('Content-type', mime_type)

            if should_compress:
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Vary', 'Accept-Encoding')

            self.send_header('Content-Length', len(response_content))
            self.add_cache_headers(mime_type, content)
            self.end_headers()
            self.wfile.write(response_content)
        except Exception as e:
            self.send_error(500, str(e))

    def _check_auth_and_permission(self, required_permission):
        """
        检查认证和权限的辅助方法

        Returns:
            tuple: (is_valid, user_payload, error_response)
        """
        auth_header = self.headers.get('Authorization', '')

        if not auth_header:
            return False, None, {
                'status': 401,
                'response': {
                    'success': False,
                    'message': '缺少认证信息',
                    'error': 'MISSING_TOKEN'
                }
            }

        if not auth_header.startswith('Bearer '):
            return False, None, {
                'status': 401,
                'response': {
                    'success': False,
                    'message': '认证格式错误',
                    'error': 'INVALID_TOKEN_FORMAT'
                }
            }

        token = auth_header[7:]
        payload = jwt_handler.verify_token(token)

        if not payload:
            return False, None, {
                'status': 401,
                'response': {
                    'success': False,
                    'message': 'Token 无效或已过期',
                    'error': 'INVALID_OR_EXPIRED_TOKEN'
                }
            }

        user_role = payload.get('role', 'viewer')
        if not has_permission(user_role, required_permission):
            return False, None, {
                'status': 403,
                'response': {
                    'success': False,
                    'message': f'权限不足，需要 {required_permission} 权限',
                    'error': 'FORBIDDEN',
                    'required_permission': required_permission,
                    'user_role': user_role
                }
            }

        return True, payload, None

    def _send_permission_error(self, error_info):
        """发送权限错误响应"""
        self.send_response(error_info['status'])
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(error_info['response'], ensure_ascii=False).encode())

    def get_current_user(self):
        """获取当前用户信息"""
        auth_header = self.headers.get('Authorization', '')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None
        token = auth_header[7:]
        return jwt_handler.verify_token(token)