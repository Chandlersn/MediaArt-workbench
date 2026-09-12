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
from server.config import PORT, BASE_DIR
from server.api.router import APIRouter

class WorkbenchHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP request handler for the workbench application."""
    
    def __init__(self, *args, **kwargs):
        self.router = APIRouter()
        super().__init__(*args, directory=BASE_DIR, **kwargs)
    
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

def main():
    """Main entry point."""
    logger.info(f"Starting Workbench Server on port {PORT}")
    logger.info(f"Base directory: {BASE_DIR}")
    
    try:
        # 多线程服务器：单线程 TCPServer 会被慢请求（扫盘/递归计数）整体阻塞，
        # 导致前端并发请求排队超时、代理层直接报 500。改用每请求一线程。
        class ThreadingWorkbenchServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True
            allow_reuse_address = True

        with ThreadingWorkbenchServer(("", PORT), WorkbenchHTTPRequestHandler) as httpd:
            logger.info(f"Server running at http://localhost:{PORT}")
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")

if __name__ == "__main__":
    main()