#!/usr/bin/env python3
"""
Main entry point for the modularized server.
Replaces the original monolithic server.py
"""

import os
import sys
import json
import time
import base64
import bcrypt
import http.server
import socketserver
import mimetypes
import gzip
import hashlib
import logging
from io import BytesIO
from urllib.parse import urlparse, parse_qs, unquote
import tempfile
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import custom modules
from server.config import (
    HOST, PORT, BASE_DIR, STATIC_DIR, FRONTEND_BUILT, BUSINESS_PATH_PREFIXES,
)
from server.api.router import APIRouter

class WorkbenchHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP request handler for the workbench application."""
    
    def __init__(self, *args, **kwargs):
        self.router = APIRouter()
        # 静态页面仅来自构建目录，开发态由 Vite 提供页面。
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def translate_path(self, path):
        """只解析公开目录，并同时防止 Windows 分隔符、盘符及链接越界。"""
        clean = unquote(path.split('?', 1)[0].split('#', 1)[0], errors='strict')
        segments = [s for s in clean.replace('\\', '/').split('/') if s]
        if any(s.startswith('.') or ':' in s or s != s.rstrip(' .')
               or any(ord(c) < 32 for c in s) for s in segments):
            raise ValueError('Invalid static path')

        def under(root, parts):
            root = os.path.realpath(root)
            target = os.path.realpath(os.path.join(root, *parts))
            candidates = [target]
            if os.path.isdir(target):
                # SimpleHTTPRequestHandler 会在 translate_path 之后自动追加首页文件名。
                candidates.extend(os.path.realpath(os.path.join(target, name))
                                  for name in ('index.html', 'index.htm'))
            for candidate in candidates:
                if os.path.normcase(os.path.commonpath((root, candidate))) != os.path.normcase(root):
                    raise ValueError('Static path escapes its root')
            return target

        for prefix in BUSINESS_PATH_PREFIXES:
            prefix_parts = prefix.strip('/').split('/')
            if [s.casefold() for s in segments[:len(prefix_parts)]] != [s.casefold() for s in prefix_parts]:
                continue
            # /assets 同时用于构建资源与业务素材，先查构建目录。
            if prefix == '/assets/' and FRONTEND_BUILT:
                candidate = under(os.path.join(STATIC_DIR, 'assets'), segments[1:])
                if os.path.exists(candidate):
                    return candidate
            return under(os.path.join(BASE_DIR, *prefix_parts), segments[len(prefix_parts):])

        # data 默认拒绝，即使构建目录中误放了同名文件也不能公开。
        if (segments and segments[0].casefold() == 'data') or not FRONTEND_BUILT:
            raise ValueError('Static path is not public')
        return under(STATIC_DIR, segments)

    def send_head(self):
        # GET 和继承的 HEAD 都经过同一检查。
        try:
            return super().send_head()
        except ValueError:
            self.send_error(404, 'File not found')
            return None

    def list_directory(self, path):
        self.send_error(404, 'File not found')
        return None
    
    def do_GET(self):
        """Handle GET requests."""
        try:
            # Check if this is an API request
            if self.path.startswith('/api/'):
                self.handle_api_request('GET')
            else:
                # Handle static file requests
                super().do_GET()
        except Exception as e:
            logger.error(f"Error handling GET request: {e}")
            self.send_error(500, "Internal Server Error")
    
    def do_POST(self):
        """Handle POST requests."""
        try:
            if self.path.startswith('/api/'):
                self.handle_api_request('POST')
            else:
                self.send_error(405, "Method Not Allowed")
        except Exception as e:
            logger.error(f"Error handling POST request: {e}")
            self.send_error(500, "Internal Server Error")
    
    def do_PUT(self):
        """Handle PUT requests."""
        try:
            if self.path.startswith('/api/'):
                self.handle_api_request('PUT')
            else:
                self.send_error(405, "Method Not Allowed")
        except Exception as e:
            logger.error(f"Error handling PUT request: {e}")
            self.send_error(500, "Internal Server Error")
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        try:
            if self.path.startswith('/api/'):
                self.handle_api_request('DELETE')
            else:
                self.send_error(405, "Method Not Allowed")
        except Exception as e:
            logger.error(f"Error handling DELETE request: {e}")
            self.send_error(500, "Internal Server Error")
    
    def handle_api_request(self, method):
        """Handle API requests using the router."""
        try:
            # Read request body if present
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b''
            
            # Parse query parameters
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            # Prepare request context
            request_context = {
                'path': parsed_url.path,
                'method': method,
                'headers': dict(self.headers),
                'body': body,
                'query_params': query_params,
                'client_address': self.client_address
            }
            
            # Route the request
            response = self.router.route_request(request_context)
            
            # Send response
            status_code = response.get('status', 200)
            headers = response.get('headers', {'Content-Type': 'application/json'})
            body = response.get('body', {})

            # Convert body to JSON if it's a dict or list
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            elif isinstance(body, str):
                body = body.encode('utf-8')
            elif not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')

            # Set Content-Length header
            headers['Content-Length'] = str(len(body))

            # Send response
            self.send_response(status_code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            
        except Exception as e:
            logger.error(f"Error in API request handling: {e}")
            error_response = json.dumps({'error': 'Internal Server Error'}).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(error_response)))
            self.end_headers()
            self.wfile.write(error_response)

def run_startup_checks():
    """启动期维护：数据库完整性自检 + 每日自动备份 + 备份轮转（任一步失败都不阻断启动）。"""
    try:
        from server.database.maintenance import (
            check_db_integrity, rotate_backups, ensure_daily_backup)
        db_file = os.path.join(BASE_DIR, 'data', 'workbench.db')
        backup_dir = os.path.join(BASE_DIR, 'data', 'backup')
        ok, detail = check_db_integrity(db_file)
        if ok:
            logger.info(f"数据库完整性自检通过: {db_file}")
        else:
            logger.error(f"数据库完整性异常（{detail}）—— 请从 data/backup 选取一份备份恢复")

        # 每日自动备份。rotate_backups 只删旧的、从不创建，缺了这一步
        # data/backup 会长期为空 —— 本地单机一旦库损坏就无从恢复。
        try:
            from server.database.store import data_store
            name = ensure_daily_backup(backup_dir, lambda: data_store.load_all_data())
            if name:
                logger.info(f"已创建每日自动备份: {name}")
        except Exception as e:
            logger.warning(f"每日自动备份跳过: {e}")

        removed = rotate_backups(backup_dir, keep=20)
        if removed:
            logger.info(f"备份轮转：删除 {removed} 份旧备份，保留最新 20 份")
    except Exception as e:
        logger.warning(f"启动期维护跳过: {e}")

def main():
    """Main entry point."""
    logger.info(f"Starting Workbench Server on port {PORT}")
    logger.info(f"Base directory: {BASE_DIR}")
    if FRONTEND_BUILT:
        logger.info(f"静态资源目录（已构建）: {STATIC_DIR}")
    else:
        logger.warning(
            "未检测到前端构建产物 dist/index.html —— 后端仅提供 API 和公开业务文件，"
            "请另开终端运行 `npm run dev`，或先执行 `npm run build`。"
        )

    run_startup_checks()

    try:
        # 多线程服务器：单线程 TCPServer 会被慢请求（扫盘/递归计数）整体阻塞，
        # 导致前端并发请求排队超时、代理层直接报 500。改用每请求一线程。
        class ThreadingWorkbenchServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True
            allow_reuse_address = True

        with ThreadingWorkbenchServer((HOST, PORT), WorkbenchHTTPRequestHandler) as httpd:
            logger.info(f"Server running at http://{HOST}:{PORT}")
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")

if __name__ == "__main__":
    main()
