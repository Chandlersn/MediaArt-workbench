"""
Server configuration module.
Centralizes all configuration from environment variables with sensible defaults.
"""

import os
import time

# Port configuration (supports environment variable override)
PORT = int(os.environ.get('WORKBENCH_PORT', os.environ.get('PORT', 8080)))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 进程启动时间（模块在进程启动时导入一次，用于 /api/status 的服务运行时间）
SERVER_START_TIME = time.time()

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

# 静态资源根目录。
#
# ⚠️ 此前这段逻辑有缺陷：只看 dist/ **目录**是否存在，且最后一个分支把 STATIC_DIR
#    设成 BASE_DIR（仓库根）——那里是**开发版** index.html，引用 /src/main.js，
#    只有 Vite dev server 能解析。后果是打包后的桌面端（Electron 加载
#    http://localhost:8080）拿不到构建产物，页面直接白屏。
#    现改为：以 `dist/index.html` 是否存在作为「已构建」的判据。
def _pick_static_dir() -> str:
    for cand in (DIST_DIR_IN_BASE, APP_DIST_DIR):
        if os.path.isfile(os.path.join(cand, 'index.html')):
            return cand
    return BASE_DIR


STATIC_DIR = _pick_static_dir()
STATIC_BASE_URL = ''

# 前端是否已构建。False 时后端只能提供开发版页面，需配合 Vite dev server 使用。
FRONTEND_BUILT = STATIC_DIR != BASE_DIR

# 业务目录前缀：素材库 / 归档 / 模板 / 运行时数据。
# 这些**始终**在仓库根下，不能跟着 STATIC_DIR 走进 dist/。
# 注意 /assets/ 两边都可能出现（前端构建产物 vs 业务素材），解析时先查构建产物再回退。
BUSINESS_PATH_PREFIXES = (
    '/resources/', '/assets/', '/MediaArt_Archives/', '/templates/', '/data/',
)

# ========== Environment Detection ==========
def is_development():
    env = os.environ.get('NODE_ENV', os.environ.get('ENV', 'development'))
    return env == 'development'

def is_production():
    return not is_development()

def get_environment():
    return 'development' if is_development() else 'production'
