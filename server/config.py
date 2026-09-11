"""
Server configuration module.
Centralizes all configuration from environment variables with sensible defaults.
"""

import os

# Port configuration (supports environment variable override)
PORT = int(os.environ.get('WORKBENCH_PORT', os.environ.get('PORT', 8080)))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Frontend dev server port
VITE_DEV_SERVER_PORT = int(os.environ.get('VITE_DEV_SERVER_PORT', 3004))

# ========== Resource Optimization Configuration ==========
GZIP_MIN_SIZE = 1024
GZIP_TYPES = {
    'text/html',
    'text/css',
    'text/javascript',
    'application/javascript',
    'application/json',
    'text/json',
    'text/plain',
    'application/xml',
    'text/xml',
    'image/svg+xml'
}

# Cache configuration
CACHE_STATIC_MAX_AGE = 31536000
CACHE_API_MAX_AGE = 0
CACHE_HTML_MAX_AGE = 0

# ========== Rate Limiting Configuration ==========
LOGIN_MAX_ATTEMPTS = int(os.environ.get('LOGIN_MAX_ATTEMPTS', 5))
LOGIN_WINDOW_SECONDS = int(os.environ.get('LOGIN_WINDOW_SECONDS', 300))

# Setup logger
import logging
logger = logging.getLogger(__name__)

# Detect if running in packaged environment
APP_DIR = os.path.join(BASE_DIR, 'app')
PARENT_DIR = os.path.dirname(BASE_DIR)
DIST_DIR_IN_BASE = os.path.join(BASE_DIR, 'dist')
APP_DIST_DIR = os.path.join(APP_DIR, 'dist')
EXTRA_RESOURCES_DIST = os.path.join(BASE_DIR, 'dist')

# Determine static directory
if os.path.exists(EXTRA_RESOURCES_DIST):
    STATIC_DIR = EXTRA_RESOURCES_DIST
    STATIC_BASE_URL = ''
elif os.path.exists(APP_DIST_DIR):
    STATIC_DIR = APP_DIST_DIR
    STATIC_BASE_URL = ''
elif os.path.exists(DIST_DIR_IN_BASE):
    STATIC_DIR = BASE_DIR
    STATIC_BASE_URL = ''
else:
    STATIC_DIR = BASE_DIR
    STATIC_BASE_URL = ''

# ========== Environment Detection ==========
def is_development():
    env = os.environ.get('NODE_ENV', os.environ.get('ENV', 'development'))
    return env == 'development'

def is_production():
    return not is_development()

def get_environment():
    return 'development' if is_development() else 'production'
