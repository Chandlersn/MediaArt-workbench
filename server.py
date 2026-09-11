import os
import sys
import json
import time
import re
import base64
import bcrypt
import http.server
import socketserver
import mimetypes
import gzip
import hashlib
import logging
from io import BytesIO
from urllib.parse import urlparse, parse_qs, unquote, quote
import tempfile
import shutil
import subprocess

from server.utils.auth_middleware import login_rate_limiter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 记录服务器启动时间
SERVER_START_TIME = time.time()

# 导入校验和 XSS 防护模块
from server.utils.validator import Validator, FormSchemas
from server.utils.xss_protection import XSSProtection, sanitize_input, sanitize_form

# 导入 JWT 工具模块
from server.utils import JWTHandler, require_auth, get_current_user, create_token_response, jwt_handler

# 导入权限管理模块
from server.utils.permissions import (
    require_permission,
    require_role,
    has_permission,
    get_role_permissions,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    ROLE_DISPLAY_NAMES
)

# 导入数据库模块
from server.database import get_data_store, get_db

# 端口配置（支持环境变量覆盖）
PORT = int(os.environ.get('WORKBENCH_PORT', 8080))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ========== 资源优化配置 ==========
# Gzip 压缩配置
GZIP_MIN_SIZE = 1024  # 最小压缩阈值（1KB）
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

# 缓存配置
CACHE_STATIC_MAX_AGE = 31536000  # 静态资源缓存 1 年
CACHE_API_MAX_AGE = 0  # API 响应不缓存
CACHE_HTML_MAX_AGE = 0  # HTML 不缓存（开发环境）

# 检测是否在打包环境中运行
APP_DIR = os.path.join(BASE_DIR, 'app')
# dist 可能在 BASE_DIR (开发环境) 或在 app/ 内部 (打包环境)
PARENT_DIR = os.path.dirname(BASE_DIR)
DIST_DIR_IN_BASE = os.path.join(BASE_DIR, 'dist')
APP_DIST_DIR = os.path.join(APP_DIR, 'dist')
# electron-builder extraResources 会把 dist 复制到 resources/dist 而不是 resources/app/dist
EXTRA_RESOURCES_DIST = os.path.join(BASE_DIR, 'dist')

logger.debug("路径检测开始")
logger.debug(f"BASE_DIR: {BASE_DIR}")
logger.debug(f"PARENT_DIR: {PARENT_DIR}")
logger.debug(f"DIST_DIR_IN_BASE exists: {os.path.exists(DIST_DIR_IN_BASE)}")
logger.debug(f"APP_DIST_DIR exists: {os.path.exists(APP_DIST_DIR)}")
logger.debug(f"EXTRA_RESOURCES_DIST exists: {os.path.exists(EXTRA_RESOURCES_DIST)}")

# 优先检查 extraResources dist（electron-builder 打包环境）
if os.path.exists(EXTRA_RESOURCES_DIST):
    # dist 在 resources/dist (electron-builder extraResources 复制位置)
    STATIC_DIR = EXTRA_RESOURCES_DIST
    STATIC_BASE_URL = ''
    logger.debug("使用 EXTRA_RESOURCES_DIST (electron-builder 打包环境)")
elif os.path.exists(APP_DIST_DIR):
    # dist 在 app 内部 (例如 resources/app/dist)
    STATIC_DIR = APP_DIST_DIR
    STATIC_BASE_URL = ''
    logger.debug(f"使用 APP_DIST_DIR")
elif os.path.exists(DIST_DIR_IN_BASE):
    # dist 在 BASE_DIR (例如 resources/dist)
    STATIC_DIR = DIST_DIR_IN_BASE
    STATIC_BASE_URL = ''
    logger.debug("使用 DIST_DIR_IN_BASE (开发环境)")
else:
    # 安全修复：严禁回退到 BASE_DIR，否则会把 data/、源码、数据库发布到 HTTP
    STATIC_DIR = None
    STATIC_BASE_URL = ''
    logger.error("未找到 dist 目录，前端资源不可用。请先执行 npm run build。")
    print(f"[Server][ERROR] 未找到 dist 目录，已禁用静态资源服务（不会回退到项目根目录）。请执行 npm run build")

# STATIC_DIR 恒为 dist 目录本身（找不到时为 None）
STATIC_IS_DIST = STATIC_DIR is not None
# 供 SimpleHTTPRequestHandler 初始化使用；STATIC_DIR 为 None 时静态请求会被显式拒绝
STATIC_FALLBACK_DIR = STATIC_DIR or BASE_DIR

print(f"[Server] 最终 STATIC_DIR: {STATIC_DIR}")
print(f"[Server] STATIC_DIR exists: {STATIC_DIR is not None}")

# 检测是否在临时目录运行（便携版）
def is_temp_directory(path):
    """检测是否在临时目录运行"""
    temp_dirs = [
        os.environ.get('TEMP', ''),
        os.environ.get('TMP', ''),
        os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Temp'),
    ]
    for temp_dir in temp_dirs:
        if temp_dir and path.lower().startswith(temp_dir.lower()):
            return True
    return False

# 获取持久化数据目录
def get_persistent_dir():
    """获取持久化数据存储目录"""
    # 优先检查项目根目录是否有 data 目录（开发环境）
    project_data_dir = os.path.join(BASE_DIR, 'data')
    if os.path.exists(project_data_dir) and os.path.exists(os.path.join(project_data_dir, 'workbench_data.json')):
        # 开发环境：项目已有数据文件，使用 BASE_DIR
        return BASE_DIR

    # 检查是否在 electron 打包环境（通过环境变量判断）
    if os.environ.get('ELECTRON_RUN_AS_NODE') or os.environ.get('electron_main_path'):
        # 打包环境：使用用户文档目录存储数据
        user_docs = os.path.join(os.environ.get('USERPROFILE', ''), 'Documents')
        persistent_dir = os.path.join(user_docs, 'MediaArt_Workbench')
        os.makedirs(persistent_dir, exist_ok=True)
        return persistent_dir

    # 默认开发环境：使用 BASE_DIR
    # 同时检查 app 目录是否只是构建产物（没有实际运行）
    app_dir = os.path.join(BASE_DIR, 'app')
    if os.path.exists(app_dir):
        # app 目录存在但可能是构建产物，检查是否有真实数据
        if not os.path.exists(project_data_dir):
            # 创建 data 目录
            os.makedirs(project_data_dir, exist_ok=True)
        return BASE_DIR

    return BASE_DIR

PERSISTENT_DIR = get_persistent_dir()

ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
DEFAULT_RESOURCES_DIR = os.path.join(PERSISTENT_DIR, 'resources')
DEFAULT_ARCHIVES_DIR = os.path.join(PERSISTENT_DIR, 'MediaArt_Archives')
DATA_DIR = os.path.join(PERSISTENT_DIR, 'data')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

# 加载配置
def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_config(config):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f'保存配置失败: {e}')
        return False

def get_archives_dir():
    config = load_config()
    custom_path = config.get('archivesPath', '')
    if custom_path and os.path.isabs(custom_path):
        return custom_path
    return DEFAULT_ARCHIVES_DIR

def get_resources_dir():
    config = load_config()
    custom_path = config.get('resourcesPath', '')
    if custom_path and os.path.isabs(custom_path):
        return custom_path
    return DEFAULT_RESOURCES_DIR

ARCHIVES_DIR = get_archives_dir()
RESOURCES_DIR = get_resources_dir()

# 默认资源分类文件夹
DEFAULT_RESOURCE_FOLDERS = [
    'images',
    'videos',
    'documents',
    'audios',
    'projects',
    'players',
    'organizations'
]

# ========== 密码加密辅助函数 ==========

def hash_password(password):
    """使用 bcrypt 加密密码"""
    try:
        # 将密码转换为字节
        password_bytes = password.encode('utf-8')
        # 生成盐值并加密
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        # 返回 base64 编码的哈希值，便于存储
        return base64.b64encode(hashed).decode('utf-8')
    except Exception as e:
        print(f"密码加密失败: {e}")
        return None

def verify_password(password, hashed_password):
    """验证密码"""
    try:
        # 将密码和哈希值转换为字节
        password_bytes = password.encode('utf-8')
        hashed_bytes = base64.b64decode(hashed_password.encode('utf-8'))
        # 验证密码
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception as e:
        print(f"密码验证失败: {e}")
        return False

def decode_client_password(encoded_password):
    """解码客户端传输的密码（Base64 编码）"""
    try:
        return base64.b64decode(encoded_password).decode('utf-8')
    except Exception as e:
        # 如果解码失败，可能客户端没有编码，直接返回原密码
        return encoded_password

def is_password_hashed(password):
    """检查密码是否已经被 bcrypt 加密"""
    try:
        # bcrypt 哈希值通常以 $2b$ 开头
        decoded = base64.b64decode(password.encode('utf-8'))
        return decoded.startswith(b'$2b$')
    except:
        return False

# 确保资源目录和默认分类文件夹存在
os.makedirs(RESOURCES_DIR, exist_ok=True)
for folder in DEFAULT_RESOURCE_FOLDERS:
    os.makedirs(os.path.join(RESOURCES_DIR, folder), exist_ok=True)

class WorkbenchHandler(http.server.SimpleHTTPRequestHandler):
    # ========== 安全：API 统一认证白名单 ==========
    # 这些接口必须匿名可访问（登录/刷新/健康检查/API 文档）
    PUBLIC_API_EXACT = frozenset({
        '/api/auth/login',
        '/api/auth/register',
        '/api/auth/refresh',
        '/api/auth/verify',
        '/api/status',
        # 文件类型图标：由 <img src="/api/file-icon?..."> 加载，元素级请求不带
        # Authorization 头，不放进白名单就会一律 401（图标全裂）。该接口只返回
        # 系统文件类型图标 PNG，不涉及任何用户数据。
        '/api/file-icon',
    })
    PUBLIC_API_PREFIX = ('/api/docs', '/api/swagger')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_FALLBACK_DIR, **kwargs)
        self.current_user = None

    # ---------- 安全工具 ----------
    @staticmethod
    def _sanitize_filename(name):
        """净化上传文件名：剥离目录成分、控制字符，拒绝 . 与 .."""
        if not name:
            return None
        try:
            name = unquote(str(name))
        except Exception:
            return None
        name = os.path.basename(name.replace('\\', '/'))
        name = re.sub(r'[\x00-\x1f]', '', name).strip()
        if not name or name in ('.', '..'):
            return None
        return name

    def _resolve_material_dir(self, base_dir, parts):
        """按多级目录名逐层安全解析，任一段非法或越界即返回 None"""
        current = os.path.realpath(base_dir)
        for part in parts:
            safe_part = self._sanitize_filename(part)
            if not safe_part:
                return None
            current = self._resolve_safe_path(current, safe_part)
            if current is None:
                return None
        return current

    def _resolve_material_candidate(self, subdirs, name, file_name, material_type=None,
                                    allow_subdir_search=False):
        """
        在归档目录的若干候选子目录中定位资料文件。

        目录名、资料类型、文件名都会先净化，再校验最终路径不越出归档目录。
        返回存在的绝对路径，找不到或非法时返回 None。
        """
        safe_name = self._sanitize_filename(name)
        safe_file = self._sanitize_filename(file_name)
        if not safe_name or not safe_file:
            return None
        safe_type = self._sanitize_filename(material_type) if material_type else None

        for sub in subdirs:
            base = self._resolve_safe_path(ARCHIVES_DIR, os.path.join(sub, safe_name))
            if base is None:
                continue
            dirs_to_try = []
            if safe_type:
                type_dir = self._resolve_safe_path(base, safe_type)
                if type_dir:
                    dirs_to_try.append(type_dir)
            dirs_to_try.append(base)
            for candidate_dir in dirs_to_try:
                full = self._resolve_safe_path(candidate_dir, safe_file)
                if full and os.path.exists(full):
                    return full
            # 兜底：在 base 的一级子目录中查找。
            # 归档目录名可能带序号（01_策划文档）或与资料类型文案不完全一致，
            # 所以即使传了 material_type 也保留这条兜底——否则"类型对不上"就直接 404。
            if allow_subdir_search and os.path.isdir(base):
                try:
                    for sub_name in sorted(os.listdir(base)):
                        sub_dir = self._resolve_safe_path(base, sub_name)
                        if sub_dir and os.path.isdir(sub_dir):
                            full = self._resolve_safe_path(sub_dir, safe_file)
                            if full and os.path.exists(full):
                                return full
                except OSError:
                    pass
        return None

    @staticmethod
    def _content_disposition(disposition, file_name):
        """
        构造 Content-Disposition 头，兼容中文文件名。

        send_header 用 latin-1 编码发送头部，遇到中文文件名会抛 UnicodeEncodeError，
        导致响应在只发出 Content-type 之后就被打成 500 —— 后续的 Content-Disposition
        与 Content-Length 全部丢失（实测表现为：响应头残缺 + 尾部多一个 500 响应块）。
        这里按 RFC 5987 输出 ASCII 回退名 + UTF-8 编码的真实名。
        """
        base = os.path.basename(file_name or '')
        stem, ext = os.path.splitext(base)
        ascii_stem = stem.encode('ascii', 'ignore').decode('ascii').strip(' ._-')
        ascii_ext = ext.encode('ascii', 'ignore').decode('ascii')
        # 引号/反斜杠会破坏头部结构，统一替换掉
        fallback = ((ascii_stem or 'file') + ascii_ext).replace('\\', '_').replace('"', '_')
        return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(base)}"

    @staticmethod
    def _resolve_safe_path(base_dir, user_path):
        """
        把用户传入的相对路径安全地解析到 base_dir 内部。

        拒绝：绝对路径、盘符路径、UNC 路径、以及任何通过 .. 逃逸出 base_dir 的路径。
        返回：安全的绝对路径；不合法或越界时返回 None。
        """
        if not user_path or not base_dir:
            return None
        try:
            user_path = unquote(str(user_path))
        except Exception:
            return None

        # 统一分隔符后拒绝绝对/盘符/UNC
        normalized = user_path.replace('/', os.sep)
        if os.path.isabs(normalized):
            return None
        if re.match(r'^[A-Za-z]:', normalized):
            return None
        if normalized.startswith(os.sep * 2) or normalized.startswith('\\\\'):
            return None

        base_real = os.path.realpath(base_dir)
        target_real = os.path.realpath(os.path.join(base_real, normalized))
        if target_real != base_real and not target_real.startswith(base_real + os.sep):
            print(f"[SECURITY] 已拦截越界路径访问: {user_path} -> {target_real} (基准: {base_real})")
            return None
        return target_real

    @staticmethod
    def _is_public_api(path):
        return path in WorkbenchHandler.PUBLIC_API_EXACT or \
            path.startswith(WorkbenchHandler.PUBLIC_API_PREFIX)

    def _send_json(self, status, payload):
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    def _guard_api_auth(self, path):
        """
        统一 API 认证门禁：除白名单外，所有 /api/* 请求必须携带有效 JWT。

        返回 True 表示放行；False 表示已写入 401 响应，调用方应立即 return。
        """
        if not path.startswith('/api/'):
            return True
        if self._is_public_api(path):
            return True

        auth_header = self.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            self._send_json(401, {
                'success': False,
                'message': '缺少认证信息，请先登录',
                'error': 'MISSING_TOKEN'
            })
            return False

        payload = jwt_handler.verify_token(auth_header[7:])
        if not payload:
            self._send_json(401, {
                'success': False,
                'message': 'Token 无效或已过期',
                'error': 'INVALID_OR_EXPIRED_TOKEN'
            })
            return False

        self.current_user = payload
        return True

    def generate_etag(self, content):
        """生成 ETag"""
        return hashlib.md5(content).hexdigest()

    def should_compress(self, content_type, content_length):
        """判断是否应该压缩"""
        # 检查内容类型
        if not content_type:
            return False

        # 提取主类型（去掉 charset 等参数）
        main_type = content_type.split(';')[0].strip().lower()

        # 检查是否在压缩类型列表中
        if main_type not in GZIP_TYPES:
            return False

        # 检查大小是否达到阈值
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
        # 根据内容类型设置缓存策略
        main_type = content_type.split(';')[0].strip().lower() if content_type else ''

        # HTML 文件不缓存（开发环境）
        if main_type == 'text/html':
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        # 静态资源长期缓存
        elif main_type in ['text/css', 'text/javascript', 'application/javascript']:
            self.send_header('Cache-Control', f'public, max-age={CACHE_STATIC_MAX_AGE}')
            # 添加 ETag
            if content:
                etag = self.generate_etag(content if isinstance(content, bytes) else content.encode('utf-8'))
                self.send_header('ETag', f'"{etag}"')
        # 图片、字体等资源
        elif main_type.startswith('image/') or main_type in ['font/woff', 'font/woff2', 'application/font-woff', 'application/font-woff2']:
            self.send_header('Cache-Control', f'public, max-age={CACHE_STATIC_MAX_AGE}')
            if content:
                etag = self.generate_etag(content if isinstance(content, bytes) else content.encode('utf-8'))
                self.send_header('ETag', f'"{etag}"')
        # JSON 响应
        elif main_type == 'application/json':
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        # 其他资源
        else:
            self.send_header('Cache-Control', 'public, max-age=3600')  # 默认缓存 1 小时

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
        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
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
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'

        parsed = urlparse(self.path)

        # ========== 安全：API 统一认证门禁 ==========
        if not self._guard_api_auth(parsed.path):
            return

        # ========== 安全：前端未构建时拒绝提供静态资源 ==========
        if STATIC_DIR is None and not parsed.path.startswith('/api/'):
            self._send_json(503, {
                'success': False,
                'message': '前端资源未构建，请先执行 npm run build 生成 dist 目录后重启服务',
                'error': 'FRONTEND_NOT_BUILT'
            })
            return

        # ========== API 文档接口 ==========
        if parsed.path == '/api/docs':
            self.serve_swagger_ui()
            return

        if parsed.path == '/api/swagger.yaml':
            self.serve_openapi_yaml()
            return

        if parsed.path == '/api/open-file':
            query = parse_qs(parsed.query)
            filepath = query.get('path', [''])[0]
            if filepath:
                self.open_file(filepath)
            return

        if parsed.path == '/api/get-file':
            query = parse_qs(parsed.query)
            filepath = query.get('path', [''])[0]
            if filepath:
                self.serve_file(filepath)
            return

        if parsed.path == '/api/list-files':
            query = parse_qs(parsed.query)
            folder = query.get('folder', [''])[0]
            self.list_files(folder)
            return

        if parsed.path == '/api/list-archives':
            query = parse_qs(parsed.query)
            folder = query.get('folder', [''])[0]
            self.list_archives(folder)
            return

        if parsed.path == '/api/count-files':
            query = parse_qs(parsed.query)
            folder = query.get('folder', [''])[0]
            self.count_files_recursive(folder)
            return

        if self.path == '/api/open-archive':
            query = parse_qs(parsed.query)
            filepath = query.get('path', [''])[0]
            if filepath:
                self.open_archive_file(filepath)
            return

        if self.path.startswith('/api/delete-folder'):
            # 删除文件夹 - 必须认证
            query = parse_qs(parsed.query)
            folder_path = query.get('path', [''])[0]
            if folder_path:
                auth_header = self.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    self.delete_folder_with_auth(folder_path)
                else:
                    # 拒绝未认证请求
                    self.send_error(401, '请先登录')
            return

        # 注：rename-folder 的 PUT 分支已移至 do_PUT（原先写在这里永不执行）

        if self.path.startswith('/api/delete-file'):
            # 删除文件 - 必须认证
            query = parse_qs(parsed.query)
            file_path = query.get('path', [''])[0]
            if file_path:
                auth_header = self.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    self.delete_file_with_auth(file_path)
                else:
                    # 拒绝未认证请求
                    self.send_error(401, '请先登录')
            return

        # 扫描选手归档文件夹
        if parsed.path == '/api/scan-player-files':
            query = parse_qs(parsed.query)
            player_name = query.get('name', [''])[0]
            if player_name:
                self.scan_player_files(player_name)
            return

        # 下载选手/机构/项目资料
        if parsed.path == '/api/download-player-material':
            query = parse_qs(parsed.query)
            player_name = query.get('playerName', [''])[0]
            file_name = query.get('fileName', [''])[0]
            material_type = query.get('materialType', [''])[0]
            preview = query.get('preview', [''])[0] == 'true'
            if player_name and file_name:
                self.download_player_material(player_name, file_name, preview, material_type)
            return

        # 扫描项目文件夹
        if parsed.path == '/api/scan-project-files':
            query = parse_qs(parsed.query)
            project_name = query.get('name', [''])[0]
            if project_name:
                self.scan_project_files(project_name)
            return

        # 扫描机构文件夹
        if parsed.path == '/api/scan-org-files':
            query = parse_qs(parsed.query)
            org_name = query.get('name', [''])[0]
            if org_name:
                self.scan_org_files(org_name)
            return

        # 下载项目资料
        if parsed.path == '/api/download-project-material':
            query = parse_qs(parsed.query)
            project_name = query.get('projectName', [''])[0]
            file_name = query.get('fileName', [''])[0]
            material_type = query.get('materialType', [''])[0]
            preview = query.get('preview', [''])[0] == 'true'
            if project_name and file_name:
                self.download_project_material(project_name, file_name, preview, material_type)
            return

        # 注：delete-project-material 的 DELETE 分支已移至 do_DELETE（原先写在这里永不执行）

        # 下载机构资料
        if parsed.path == '/api/download-org-material':
            query = parse_qs(parsed.query)
            org_name = query.get('orgName', [''])[0]
            file_name = query.get('fileName', [''])[0]
            material_type = query.get('materialType', [''])[0]
            preview = query.get('preview', [''])[0] == 'true'
            if org_name and file_name:
                # 修复：此前漏传 material_type，直接 TypeError 并把连接打断（该接口从不可用）
                self.download_org_material(org_name, file_name, material_type, preview)
            return

        # 预览机构资料（内联显示）
        if parsed.path == '/api/get-org-material':
            query = parse_qs(parsed.query)
            org_name = query.get('orgName', [''])[0]
            file_name = query.get('fileName', [''])[0]
            material_type = query.get('materialType', [''])[0]  # 资料类型（子文件夹）
            if org_name and file_name and material_type:
                self.download_org_material(org_name, file_name, material_type, preview=True)
            elif org_name and file_name:
                # 兼容旧调用（尝试在所有子文件夹中查找）
                self.download_org_material_legacy(org_name, file_name, preview=True)
            return

        # 提取文件纯文本内容（用于 Office 等格式在线预览）
        if parsed.path == '/api/preview-text':
            query = parse_qs(parsed.query)
            source = query.get('source', [''])[0]
            name = query.get('name', [''])[0]
            file_name = query.get('fileName', [''])[0]
            material_type = query.get('materialType', [''])[0]
            path = query.get('path', [''])[0]
            if (source and file_name) or path:
                self.preview_file_text(source, name, file_name, material_type, path)
            return

        # 注：delete-org-material 的 DELETE 分支已移至 do_DELETE（原先写在这里永不执行）

        # 获取缺失资料列表
        if parsed.path == '/api/data/missing-materials':
            self.get_missing_materials()
            return

        # 审计日志 API
        if parsed.path == '/api/audit-logs' and self.command == 'GET':
            self.get_audit_logs()
            return

        # 用户管理 API
        if parsed.path == '/api/users' and self.command == 'GET':
            self.get_users()
            return

        # 注：/api/users 的 POST/PUT/DELETE、/api/users/{id}/toggle-status、
        #     /api/import-players 的 POST 分支已分别移至 do_POST / do_PUT / do_DELETE
        #     （原先全部写在这里，因 do_GET 中 self.command 恒为 GET 而永不执行）

        # 分页查询选手列表
        if parsed.path == '/api/players/list':
            query = parse_qs(parsed.query)
            page = int(query.get('page', ['1'])[0])
            pageSize = int(query.get('pageSize', ['20'])[0])
            search = query.get('search', [''])[0]
            self.list_players_paginated(page, pageSize, search)
            return

        # 分页查询项目列表
        if parsed.path == '/api/projects/list':
            query = parse_qs(parsed.query)
            page = int(query.get('page', ['1'])[0])
            pageSize = int(query.get('pageSize', ['20'])[0])
            search = query.get('search', [''])[0]
            self.list_projects_paginated(page, pageSize, search)
            return

        # 分页查询机构列表
        if parsed.path == '/api/organizations/list':
            query = parse_qs(parsed.query)
            page = int(query.get('page', ['1'])[0])
            pageSize = int(query.get('pageSize', ['20'])[0])
            search = query.get('search', [''])[0]
            self.list_organizations_paginated(page, pageSize, search)
            return

        # 数据存储 API
        if parsed.path == '/api/data/load':
            self.load_data()
            return

        if parsed.path == '/api/data/list-backups':
            self.list_backups()
            return

        # 获取数据版本信息
        if parsed.path == '/api/data/version':
            self.get_data_version()
            return

        if parsed.path == '/api/config/archive-path':
            self.get_archive_path()
            return

        if parsed.path == '/api/config/resources-path':
            self.get_resources_path()
            return

        if parsed.path == '/api/status':
            self.get_system_status()
            return

        if parsed.path == '/api/cleanup/scan':
            self.scan_temp_files()
            return

        if parsed.path == '/api/cleanup/execute':
            self.cleanup_temp_files()
            return

        if parsed.path.startswith('/api/notifications'):
            self.handle_notifications()
            return

        if parsed.path == '/api/browse-dirs':
            self.browse_directories()
            return

        if parsed.path == '/api/file-icon':
            self.get_file_icon()
            return

        # Token 验证接口
        if parsed.path == '/api/auth/verify':
            self.auth_verify_token()
            return

        # 获取权限信息接口
        if parsed.path == '/api/auth/permissions':
            self.get_permissions_info()
            return

        # ========== 数据同步 API ==========
        if parsed.path == '/api/data/sync/status':
            self.get_sync_status()
            return

        if parsed.path == '/api/data/sync/import':
            self.import_from_json_api()
            return

        if parsed.path == '/api/data/sync/export':
            self.export_to_json_api()
            return

        # 处理 resources 目录的静态文件请求
        if parsed.path.startswith('/resources/'):
            file_path = unquote(parsed.path[len('/resources/'):])
            # 安全修复：禁止通过 .. 或绝对路径读取素材目录之外的文件
            full_path = self._resolve_safe_path(RESOURCES_DIR, file_path)
            if full_path is None:
                self._reject_unsafe_path(file_path)
                return
            if os.path.exists(full_path) and os.path.isfile(full_path):
                self.serve_static_file(full_path)
                return
            else:
                self.send_error(404, 'File not found')
                return

        # 处理 dist 目录的静态文件请求（Vite 构建的前端）
        # dist 目录在 resources/app/dist/ 下（打包环境）或 dist/ 下（开发环境）
        # 同时处理旧路径 /js/ 和 /css/，映射到 resources/js/ 和 resources/css/

        # 判断 STATIC_DIR 是否已经是 dist 目录（即不需要再添加 dist 前缀）
        STATIC_IS_DIST = STATIC_DIR.endswith('dist') or os.path.basename(STATIC_DIR) == 'dist'

        if parsed.path.startswith('/dist/'):
            file_path = os.path.join(STATIC_DIR, unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
            else:
                print(f"静态文件未找到: {file_path}")
                self.send_error(404, 'File not found')
            return
        elif parsed.path.startswith('/css/'):
            if STATIC_IS_DIST:
                file_path = os.path.join(STATIC_DIR, unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))
            else:
                file_path = os.path.join(STATIC_DIR, 'dist', unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
            else:
                print(f"CSS文件未找到: {file_path}")
                self.send_error(404, 'File not found')
            return
        elif parsed.path.startswith('/js/') and not parsed.path.startswith('/js/lib/'):
            if STATIC_IS_DIST:
                file_path = os.path.join(STATIC_DIR, unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))
            else:
                file_path = os.path.join(STATIC_DIR, 'dist', unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))
            print(f"JS请求: {parsed.path} -> 实际路径: {file_path}, 存在: {os.path.exists(file_path)}")
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
            else:
                print(f"JS文件未找到: {file_path}")
                self.send_error(404, 'File not found')
            return
        elif parsed.path.startswith('/js/lib/') or parsed.path == '/js/':
            # 优先在 STATIC_DIR 中查找（打包环境 dist/js/lib/）
            if STATIC_IS_DIST:
                file_path = os.path.join(STATIC_DIR, unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))
            else:
                file_path = os.path.join(STATIC_DIR, 'dist', unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))

            # 如果在 STATIC_DIR 中找不到，回退到 BASE_DIR（开发环境）
            if not os.path.exists(file_path):
                file_path = os.path.join(BASE_DIR, unquote(parsed.path[1:] if parsed.path.startswith('/') else parsed.path))


            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
            else:
                print(f"静态文件未找到: {file_path}")
                self.send_error(404, 'File not found')
            return
        elif parsed.path == '/index.html':
            if STATIC_IS_DIST:
                file_path = os.path.join(STATIC_DIR, 'index.html')
            else:
                file_path = os.path.join(STATIC_DIR, 'dist', 'index.html')
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
            else:
                print(f"静态文件未找到: {file_path}")
                self.send_error(404, 'File not found')
            return
        elif parsed.path == '/style.css':
            if STATIC_IS_DIST:
                file_path = os.path.join(STATIC_DIR, 'style.css')
            else:
                file_path = os.path.join(STATIC_DIR, 'dist', 'style.css')
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
            else:
                print(f"静态文件未找到: {file_path}")
                self.send_error(404, 'File not found')
            return

        # 处理其他静态文件（相对路径请求）
        # 这些请求来自 HTML 中的相对引用，如 "js/lib/chart.min.js"
        if not parsed.path.startswith('/') and '.' in parsed.path:
            if STATIC_IS_DIST:
                file_path = os.path.join(STATIC_DIR, parsed.path)
            else:
                file_path = os.path.join(STATIC_DIR, 'dist', parsed.path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
                return
            else:
                print(f"相对路径文件未找到: {file_path}")
                self.send_error(404, 'File not found')
                return

        # ========== SPA 路回退 ==========
        # 所有非 API、非静态文件的请求 → 返回 index.html（前端路由处理）
        if not parsed.path.startswith('/api') and '.' not in parsed.path:
            if STATIC_IS_DIST:
                file_path = os.path.join(STATIC_DIR, 'index.html')
            else:
                file_path = os.path.join(STATIC_DIR, 'dist', 'index.html')
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_static_file(file_path)
                return
            else:
                print(f"SPA index.html 未找到: {file_path}")
                self.send_error(404, 'File not found')
                return

        # ========== 安全：兜底静态服务 ==========
        # 仅在静态目录明确指向 dist 时放行；严禁回退到项目根目录
        if STATIC_IS_DIST:
            super().do_GET()
        else:
            self.send_error(404, 'Not Found')

    def do_POST(self):
        parsed = urlparse(self.path)

        # ========== 安全：API 统一认证门禁 ==========
        if not self._guard_api_auth(parsed.path):
            return

        # 数据同步（SQLite <-> JSON）
        # 修复：这两个接口此前只在 do_GET 里分发，而前端 SettingsView 用 POST 调用，
        #      导致"数据迁移/导出"点击后恒返回 404（handle 本身与请求方法无关）。
        if parsed.path in ('/api/data/sync/import', '/api/data/sync/export'):
            # 排空请求体，避免 keep-alive 连接上残留数据污染下一个请求
            try:
                length = int(self.headers.get('Content-Length') or 0)
                if length > 0:
                    self.rfile.read(length)
            except (TypeError, ValueError):
                pass
            if parsed.path == '/api/data/sync/import':
                self.import_from_json_api()
            else:
                self.export_to_json_api()
            return

        if self.path == '/api/open-file':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.open_file(data.get('path', ''))
            return

        # 保存 stageMaterials 配置
        if self.path == '/api/save-stage-materials':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.save_stage_materials(data)
            return

        if self.path == '/api/create-folder':
            # 安全修复：移除"允许未认证访问"分支，统一走认证版本
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.create_folder_with_auth(data.get('path', ''))
            return

        if self.path == '/api/config/archive-path':
            # 保存归档路径配置
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.set_archive_path_with_auth(data.get('path', ''))
            return

        if self.path == '/api/config/resources-path':
            # 保存资源路径配置
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.set_resources_path_with_auth(data.get('path', ''))
            return

        if self.path == '/api/open-archive':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.open_archive_file(data.get('path', ''))
            return

        if self.path == '/api/save-file':
            # 安全修复：移除"允许未认证访问"分支
            self.save_file_with_auth()
            return

        if self.path == '/api/copy-to-archive':
            # 安全修复：移除"允许未认证访问"分支
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.copy_to_archive_with_auth(data.get('source', ''), data.get('destination', ''))
            return

        # 数据存储 API
        if self.path == '/api/data/save':
            is_valid, _, error = self._check_auth_and_permission('manage_config')
            if not is_valid:
                self._send_permission_error(error)
                return
            self.save_data()
            return

        if self.path == '/api/data/save-incremental':
            is_valid, _, error = self._check_auth_and_permission('update')
            if not is_valid:
                self._send_permission_error(error)
                return
            self.save_incremental_data()
            return

        if self.path == '/api/data/backup':
            # 安全修复：移除"允许未认证访问"分支
            self.create_backup_with_auth()
            return

        if self.path == '/api/data/restore':
            # 恢复备份需要 admin 权限
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.restore_backup_with_auth(data.get('backup_name', ''))
            return

        if self.path == '/api/config/archive-path':
            # 配置归档路径需要 admin 权限
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.set_archive_path_with_auth(data.get('path', ''))
            return

        if self.path == '/api/cleanup/execute':
            self.cleanup_temp_files()
            return

        if self.path.startswith('/api/upload'):
            # 上传资源需要 editor 或更高权限
            self.upload_resource_with_auth()
            return

        if self.path == '/api/rename-folder':
            # 重命名文件夹需要 editor 或更高权限
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.rename_folder_with_auth(data.get('old_path', ''), data.get('new_name', ''))
            return

        # ========== 认证 API ==========
        if self.path == '/api/auth/register':
            self.auth_register()
            return

        if self.path == '/api/auth/login':
            self.auth_login()
            return

        if self.path == '/api/auth/migrate-password':
            self.auth_migrate_password()
            return

        if self.path == '/api/auth/check-password':
            self.auth_check_password()
            return

        if self.path == '/api/auth/refresh':
            self.auth_refresh_token()
            return

        if self.path == '/api/audit-logs':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.add_audit_log(data)
            return

        if self.path == '/api/export':
            self.handle_export_data()
            return

        if self.path.startswith('/api/notifications'):
            self.handle_notifications()
            return

        # ========== 用户管理 API（POST）==========
        # 原先这些分支写在 do_GET 中，因 self.command 恒为 GET 而永不执行
        if parsed.path == '/api/users':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.add_user(data)
            return

        if parsed.path.startswith('/api/users/') and parsed.path.endswith('/toggle-status'):
            user_id = parsed.path[len('/api/users/'):].replace('/toggle-status', '')
            self.toggle_user_status(user_id)
            return

        # ========== 选手批量导入 API（POST）==========
        if parsed.path == '/api/import-players':
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in content_type:
                self.import_players()
            else:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                self.import_players_json(data)
            return

        # ========== 修改密码 API（POST）==========
        if parsed.path == '/api/users/change-password':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.change_password(data)
            return

        # ========== 打开资源文件 API（POST）==========
        if parsed.path == '/api/open-resource':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.open_resource_file(data.get('path', ''))
            return

        # ========== 打开资源文件夹 API（POST）==========
        if parsed.path == '/api/open-folder':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.open_resource_folder(data.get('path', ''))
            return

        self.send_error(404, 'Not Found')

    def do_PUT(self):
        """处理 PUT 请求（统一走认证门禁）"""
        parsed = urlparse(self.path)

        if not self._guard_api_auth(parsed.path):
            return

        # ========== 重命名文件夹 ==========
        # 前端 ArchiveView 使用 PUT，原先分支写在 do_GET 中永不执行
        if parsed.path.startswith('/api/rename-folder'):
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            old_path = data.get('oldPath', '')
            new_path = data.get('newPath', '')
            if old_path and new_path:
                self.rename_folder_with_auth(old_path, os.path.basename(new_path))
            else:
                self._send_json(400, {
                    'success': False,
                    'message': '缺少 oldPath 或 newPath 参数',
                    'error': 'MISSING_PARAMS'
                })
            return

        # ========== 更新用户 ==========
        if parsed.path.startswith('/api/users/'):
            user_id = parsed.path[len('/api/users/'):]
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.update_user(user_id, data)
            return

        self._send_json(501, {
            'success': False,
            'message': '该接口暂不支持 PUT 方法',
            'error': 'METHOD_NOT_IMPLEMENTED'
        })

    def do_DELETE(self):
        """处理 DELETE 请求"""
        parsed = urlparse(self.path)

        # ========== 安全：API 统一认证门禁 ==========
        if not self._guard_api_auth(parsed.path):
            return

        # 删除选手/机构/项目资料
        if parsed.path == '/api/delete-player-material':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                player_name = data.get('playerName', '')
                file_name = data.get('fileName', '')
                if player_name and file_name:
                    self.delete_player_material(player_name, file_name)
                else:
                    self.send_error(400, 'Missing playerName or fileName')
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
            return

        # 删除项目资料（前端 ProjectDetailView 使用 DELETE，原先分支写在 do_GET 中永不执行）
        if parsed.path == '/api/delete-project-material':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                project_name = data.get('projectName', '')
                file_name = data.get('fileName', '')
                if project_name and file_name:
                    self.delete_project_material(project_name, file_name)
                else:
                    self.send_error(400, 'Missing projectName or fileName')
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
            return

        # 删除机构资料（前端 OrganizationDetailView 使用 DELETE）
        if parsed.path == '/api/delete-org-material':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                org_name = data.get('orgName', '')
                file_name = data.get('fileName', '')
                material_type = data.get('materialType', '')
                if org_name and file_name:
                    self.delete_org_material(org_name, file_name, material_type)
                else:
                    self.send_error(400, 'Missing orgName or fileName')
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
            return

        # 删除用户（原先分支写在 do_GET 中永不执行）
        if parsed.path.startswith('/api/users/'):
            user_id = parsed.path[len('/api/users/'):].replace('/toggle-status', '')
            if user_id:
                self.delete_user(user_id)
            else:
                self.send_error(400, 'Missing user id')
            return

        # 通知相关：DELETE /api/notifications/{id}
        # 修复：do_GET / do_POST 都有该分发，do_DELETE 原先漏掉，
        #      导致前端删除通知恒返回 404（handle_notifications 本身支持 DELETE）
        if parsed.path.startswith('/api/notifications'):
            self.handle_notifications()
            return

        if self.path.startswith('/api/delete-file'):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            filepath = params.get('path', [''])[0]

            if not filepath:
                self.send_error(400, 'No file path provided')
                return

            # 必须认证
            auth_header = self.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                self.delete_file_with_auth(filepath)
            else:
                self.send_error(401, '请先登录')
            return

        if self.path.startswith('/api/delete-folder'):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            folder_path = params.get('path', [''])[0]

            if not folder_path:
                self.send_error(400, 'No folder path provided')
                return

            auth_header = self.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                self.delete_folder_with_auth(folder_path)
            else:
                self.send_error(401, '请先登录')
            return

        self.send_error(404, 'Not Found')

    def save_file(self):
        """保存上传的文件到 assets 目录"""
        try:
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_error(400, 'Expected multipart/form-data')
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            print(f"上传文件: Content-Length={content_length}, boundary exist={('boundary=' in content_type)}")

            boundary = content_type.split('boundary=')[1].encode()
            parts = post_data.split(b'--' + boundary)

            print(f"上传文件: 解析到 {len(parts)} 个 parts")

            file_data = None
            original_filename = None
            new_filename = None
            category = 'documents'

            for i, part in enumerate(parts):
                if not part or part == b'--\r\n' or part == b'--':
                    continue

                print(f"上传文件: 处理 part {i}, 长度={len(part)}, Content-Disposition exist={b'Content-Disposition' in part}")

                if b'Content-Disposition' in part:
                    disposition_start = part.find(b'Content-Disposition:')
                    disposition_end = part.find(b'\r\n', disposition_start)
                    disposition = part[disposition_start:disposition_end].decode()

                    print(f"上传文件: part {i} disposition={disposition}")

                    if b'filename="' in part:
                        filename_start = part.find(b'filename="') + 10
                        filename_end = part.find(b'"', filename_start)
                        if filename_start > 9 and filename_end > filename_start:
                            original_filename = part[filename_start:filename_end].decode()
                            print(f"上传文件: part {i} original_filename={original_filename}")

                        content_start = part.rfind(b'\r\n\r\n')
                        print(f"上传文件: part {i} content_start={content_start}")
                        if content_start != -1:
                            content_start += 4
                            file_data = part[content_start:]
                            if file_data.endswith(b'\r\n'):
                                file_data = file_data[:-2]
                            print(f"上传文件: part {i} file_data长度={len(file_data) if file_data else 0}")
                    elif 'name="filename"' in disposition:
                        content_start = part.find(b'\r\n\r\n')
                        if content_start != -1:
                            content_start += 4
                            content_end = len(part)
                            if part.endswith(b'\r\n'):
                                content_end -= 2
                            new_filename = part[content_start:content_end].decode().strip()
                    elif 'name="category"' in disposition:
                        content_start = part.find(b'\r\n\r\n')
                        if content_start != -1:
                            content_start += 4
                            content_end = len(part)
                            if part.endswith(b'\r\n'):
                                content_end -= 2
                            category = part[content_start:content_end].decode().strip()

            file_name = new_filename or original_filename

            print(f"解析结果: file_data长度={len(file_data) if file_data else 0}, file_name={file_name}, category={category}")

            if file_data and len(file_data) > 0 and file_name:
                # 安全修复：净化文件名并校验最终路径不能越出素材目录
                file_name = self._sanitize_filename(file_name)
                if not file_name:
                    self._send_json(400, {
                        'success': False,
                        'message': '非法的文件名',
                        'error': 'INVALID_FILENAME'
                    })
                    return

                category_dir = self._resolve_safe_path(ASSETS_DIR, category or '')
                if category_dir is None:
                    self._reject_unsafe_path(category)
                    return
                os.makedirs(category_dir, exist_ok=True)

                file_path = self._resolve_safe_path(category_dir, file_name)
                if file_path is None:
                    self._reject_unsafe_path(file_name)
                    return
                print(f"保存文件: {file_path} (大小: {len(file_data)} bytes)")
                with open(file_path, 'wb') as f:
                    f.write(file_data)

                print(f"文件保存成功: {file_path}")

                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': True,
                    'message': 'File saved successfully',
                    'path': f'{category}/{file_name}'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
            else:
                print(f"保存文件失败: file_data={file_data is not None}, file_name={file_name}")
                self.send_error(400, 'No file data received')

        except Exception as e:
            print(f"保存文件异常: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    # ========== 权限验证辅助方法 ==========

    def _check_auth_and_permission(self, required_permission):
        """
        检查认证和权限的辅助方法

        Args:
            required_permission: 所需权限

        Returns:
            tuple: (is_valid, user_payload, error_response)
        """
        # 从请求头获取 Token
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

        # 解析 Bearer Token
        if not auth_header.startswith('Bearer '):
            return False, None, {
                'status': 401,
                'response': {
                    'success': False,
                    'message': '认证格式错误',
                    'error': 'INVALID_TOKEN_FORMAT'
                }
            }

        token = auth_header[7:]  # 去掉 'Bearer ' 前缀

        # 验证 Token
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

        # 检查权限
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

    def get_permissions_info(self):
        """获取权限信息"""
        try:
            # 检查认证
            auth_header = self.headers.get('Authorization', '')

            if not auth_header or not auth_header.startswith('Bearer '):
                self.send_response(401)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '缺少认证信息',
                    'error': 'MISSING_TOKEN'
                }, ensure_ascii=False).encode())
                return

            token = auth_header[7:]
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

            # 获取用户权限
            user_role = payload.get('role', 'viewer')
            permissions = get_role_permissions(user_role)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'role': user_role,
                'role_display_name': ROLE_DISPLAY_NAMES.get(user_role, user_role),
                'permissions': permissions,
                'role_level': ROLE_HIERARCHY.get(user_role, 0)
            }, ensure_ascii=False).encode())

        except Exception as e:
            print(f"获取权限信息失败: {e}")
            self.send_error(500, str(e))

    # ========== 带权限验证的 API 方法 ==========

    def delete_folder_with_auth(self, folder_path):
        """删除文件夹（需要 admin 权限）"""
        is_valid, _, error = self._check_auth_and_permission('delete')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始删除方法
        self.delete_folder(folder_path)

    def delete_file_with_auth(self, file_path):
        """删除文件（需要 admin 权限）"""
        is_valid, _, error = self._check_auth_and_permission('delete')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始删除方法
        self.delete_file(file_path)

    def create_folder_with_auth(self, folder_path):
        """创建文件夹（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('create')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始创建方法
        self.create_folder(folder_path)

    def save_file_with_auth(self):
        """保存文件（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('create')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始保存方法
        self.save_file()

    def copy_to_archive_with_auth(self, source, destination):
        """复制到归档（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('create')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始复制方法
        self.copy_to_archive(source, destination)

    def save_data_with_auth(self):
        """保存数据（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('update')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始保存方法
        self.save_data()

    def save_incremental_data_with_auth(self):
        """增量保存数据（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('update')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用增量保存方法
        self.save_incremental_data()

    def create_backup_with_auth(self):
        """创建备份（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('create')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始备份方法
        self.create_backup()

    def restore_backup_with_auth(self, backup_name):
        """恢复备份（需要 admin 权限）"""
        is_valid, _, error = self._check_auth_and_permission('delete')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始恢复方法
        self.restore_backup(backup_name)

    def set_archive_path_with_auth(self, new_path):
        """设置归档路径（需要 admin 权限）"""
        is_valid, _, error = self._check_auth_and_permission('manage_config')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始设置方法
        self.set_archive_path(new_path)

    def upload_resource_with_auth(self):
        """上传资源（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('create')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始上传方法
        self.upload_resource()

    def rename_folder_with_auth(self, old_path, new_name):
        """重命名文件夹（需要 editor 或更高权限）"""
        is_valid, _, error = self._check_auth_and_permission('update')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始重命名方法
        self.rename_folder(old_path, new_name)

    def upload_resource(self):
        """上传资源文件到 resources 目录"""
        try:
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_error(400, 'Expected multipart/form-data')
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            boundary = content_type.split('boundary=')[1].encode()
            parts = post_data.split(b'--' + boundary)

            file_data = None
            original_filename = None
            folder = ''
            org_name = ''
            material_type = ''
            target_path = ''

            for part in parts:
                if not part or part == b'--\r\n' or part == b'--':
                    continue

                if b'Content-Disposition' in part:
                    disposition_start = part.find(b'Content-Disposition:')
                    disposition_end = part.find(b'\r\n', disposition_start)

                    if b'filename="' in part:
                        filename_start = part.find(b'filename="') + 10
                        filename_end = part.find(b'"', filename_start)
                        if filename_start > 9 and filename_end > filename_start:
                            original_filename = part[filename_start:filename_end].decode()

                        content_start = part.rfind(b'\r\n\r\n')
                        if content_start != -1:
                            content_start += 4
                            file_data = part[content_start:]
                            if file_data.endswith(b'\r\n'):
                                file_data = file_data[:-2]
                    elif b'name="folder"' in part:
                        content_start = part.find(b'\r\n\r\n')
                        if content_start != -1:
                            content_start += 4
                            content_end = len(part)
                            if part.endswith(b'\r\n'):
                                content_end -= 2
                            folder = part[content_start:content_end].decode().strip()
                    elif b'name="orgName"' in part:
                        content_start = part.find(b'\r\n\r\n')
                        if content_start != -1:
                            content_start += 4
                            content_end = len(part)
                            if part.endswith(b'\r\n'):
                                content_end -= 2
                            org_name = part[content_start:content_end].decode().strip()
                    elif b'name="materialType"' in part:
                        content_start = part.find(b'\r\n\r\n')
                        if content_start != -1:
                            content_start += 4
                            content_end = len(part)
                            if part.endswith(b'\r\n'):
                                content_end -= 2
                            material_type = part[content_start:content_end].decode().strip()
                    elif b'name="targetPath"' in part:
                        # 前端（素材库分类 / 归档目录 / 模板）统一用 targetPath 指定目标目录，
                        # 此前后端从未解析该字段，导致三个页面上传的文件全部落到素材根目录
                        content_start = part.find(b'\r\n\r\n')
                        if content_start != -1:
                            content_start += 4
                            content_end = len(part)
                            if part.endswith(b'\r\n'):
                                content_end -= 2
                            target_path = part[content_start:content_end].decode().strip().strip('/\\')

            if file_data and len(file_data) > 0 and original_filename:
                # 安全修复：净化文件名，并校验保存目录不越出各自的基准目录
                safe_filename = self._sanitize_filename(original_filename)
                if not safe_filename:
                    self._send_json(400, {
                        'success': False,
                        'message': '非法的文件名',
                        'error': 'INVALID_FILENAME'
                    })
                    return

                if org_name and material_type:
                    # 机构资料上传 - 保存到归档目录
                    save_dir = self._resolve_material_dir(
                        ARCHIVES_DIR, ('03_合作机构', self._sanitize_filename(org_name),
                                       self._sanitize_filename(material_type)))
                    print(f"上传机构资料: {org_name}/{material_type}/{safe_filename}")
                elif target_path:
                    # targetPath 归一化到归一目录：归档前缀走归档目录，其余走素材库目录
                    normalized_target = target_path.replace('/', os.sep)
                    if normalized_target.startswith(self.ARCHIVE_TOP_DIRS):
                        save_dir = self._resolve_safe_path(ARCHIVES_DIR, normalized_target)
                        print(f"上传到归档目录: {target_path}/{safe_filename}")
                    else:
                        save_dir = self._resolve_safe_path(RESOURCES_DIR, normalized_target)
                        print(f"上传到素材库目录: {target_path}/{safe_filename}")
                elif folder:
                    save_dir = self._resolve_safe_path(RESOURCES_DIR, folder)
                else:
                    save_dir = RESOURCES_DIR

                if save_dir is None:
                    self._reject_unsafe_path(target_path or (folder if folder else org_name))
                    return

                os.makedirs(save_dir, exist_ok=True)

                file_path = self._resolve_safe_path(save_dir, safe_filename)
                if file_path is None:
                    self._reject_unsafe_path(safe_filename)
                    return
                print(f"上传资源文件: {file_path} (大小: {len(file_data)} bytes)")

                with open(file_path, 'wb') as f:
                    f.write(file_data)

                if target_path:
                    relative_path = f'{target_path}/{original_filename}'
                elif folder:
                    relative_path = f'{folder}/{original_filename}'
                else:
                    relative_path = original_filename

                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': True,
                    'message': 'File uploaded successfully',
                    'path': relative_path
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
            else:
                self.send_error(400, 'No file data received')

        except Exception as e:
            print(f"上传资源文件异常: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def copy_to_archive(self, source, destination):
        """将文件从 assets 复制到归档目录"""
        try:
            # 安全修复：源与目标都必须落在各自基准目录内
            source_path = self._resolve_safe_path(ASSETS_DIR, source)
            dest_path = self._resolve_safe_path(ARCHIVES_DIR, destination)
            if source_path is None or dest_path is None:
                self._reject_unsafe_path(destination if dest_path is None else source)
                return

            print(f"复制文件: {source_path} -> {dest_path}")

            # 检查源文件是否存在
            if not os.path.exists(source_path):
                print(f"源文件不存在: {source_path}")
                print(f"尝试列出目录: {os.path.dirname(source_path)}")
                if os.path.exists(os.path.dirname(source_path)):
                    files = os.listdir(os.path.dirname(source_path))
                    print(f"目录中的文件: {files}")
                self.send_error(404, f'Source file not found: {source}')
                return

            # 确保目标目录存在
            dest_dir = os.path.dirname(dest_path)
            os.makedirs(dest_dir, exist_ok=True)

            # 复制文件
            import shutil
            shutil.copy2(source_path, dest_path)

            print(f"文件复制成功: {dest_path}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'message': 'File copied to archive',
                'source': source,
                'destination': destination
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except Exception as e:
            print(f"复制文件失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    # 归档目录的一级子目录（与归档页的分类保持一致）
    ARCHIVE_TOP_DIRS = (
        '01_项目资料', '02_选手档案', '03_合作机构',
        '04_财务管理', '05_知识资源', '06_系统备份',
    )

    def _resolve_material_path(self, filepath):
        """
        解析素材/归档文件路径；越界或非法时返回 None。

        - 归档文件（01_项目资料/… 等）→ ARCHIVES_DIR
        - 其余 → 依次尝试 RESOURCES_DIR、ASSETS_DIR

        修复两点：① 此前只认前三个归档目录，归档页里 04/05/06 分类下的文件会被
        错误地解析到 ASSETS_DIR 而找不到；② 素材库的文件实际存放在 RESOURCES_DIR，
        此前完全没被考虑，导致素材库的下载/预览一律取不到文件。
        """
        if not filepath:
            return None
        normalized = str(filepath).replace('/', os.sep)
        if normalized.startswith(self.ARCHIVE_TOP_DIRS):
            return self._resolve_safe_path(ARCHIVES_DIR, normalized)

        candidates = []
        for base_dir in (RESOURCES_DIR, ASSETS_DIR):
            resolved = self._resolve_safe_path(base_dir, normalized)
            if resolved:
                candidates.append(resolved)
                if os.path.exists(resolved):
                    return resolved
        # 都不存在时返回首个候选，由调用方按"文件不存在"处理（保持原有 404 语义）
        return candidates[0] if candidates else None

    def _reject_unsafe_path(self, filepath):
        self._send_json(403, {
            'success': False,
            'message': '非法的文件路径：仅允许访问素材库与归档目录内的文件',
            'error': 'PATH_OUT_OF_BOUNDS'
        })

    def open_file(self, filepath):
        if not filepath:
            self.send_error(400, 'No file path provided')
            return

        # 安全修复：统一走安全路径解析，禁止绝对路径与 .. 越界
        full_path = self._resolve_material_path(filepath)
        if full_path is None:
            self._reject_unsafe_path(filepath)
            return

        print(f"尝试打开文件: {full_path}")

        if not os.path.exists(full_path):
            self.send_error(404, f'File not found: {filepath}')
            return

        try:
            os.startfile(full_path)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'message': f'Opened: {filepath}'}).encode())
        except Exception as e:
            print(f"打开文件失败: {e}")
            self.send_error(500, str(e))

    def serve_file(self, filepath):
        if not filepath:
            self.send_error(400, 'No file path provided')
            return

        print(f"serve_file 请求: {filepath}")

        # 安全修复：统一走安全路径解析，禁止绝对路径与 .. 越界
        full_path = self._resolve_material_path(filepath)
        if full_path is None:
            self._reject_unsafe_path(filepath)
            return

        print(f"serve_file 完整路径: {full_path}")
        print(f"serve_file 文件存在: {os.path.exists(full_path)}")

        if not os.path.exists(full_path):
            # 尝试列出目录内容帮助调试
            dir_path = os.path.dirname(full_path)
            print(f"serve_file 目录存在: {os.path.exists(dir_path)}")
            if os.path.exists(dir_path):
                try:
                    files = os.listdir(dir_path)
                    print(f"serve_file 目录内容 ({len(files)} 个): {files[:10]}")
                except Exception as e:
                    print(f"serve_file 列出目录失败: {e}")
            self.send_error(404, f'File not found: {filepath}')
            return

        try:
            # 根据文件扩展名确定 Content-Type
            import mimetypes
            content_type, _ = mimetypes.guess_type(full_path)
            if not content_type:
                content_type = 'application/octet-stream'

            with open(full_path, 'rb') as f:
                file_data = f.read()

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(file_data))
            # 支持跨域
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(file_data)

        except Exception as e:
            print(f"获取文件失败: {e}")
            self.send_error(500, str(e))

    def list_files(self, folder):
        # 优先从 resources 目录读取，如果不存在则从 assets 读取
        # 排除系统目录
        EXCLUDED_DIRS = {'app', 'data', 'templates', '__pycache__', '.git', 'node_modules'}

        if folder == '' or folder == '/':
            target_dir = RESOURCES_DIR
        else:
            # 安全修复：校验路径必须落在素材资源目录内
            target_dir = self._resolve_safe_path(RESOURCES_DIR, folder)
            if target_dir is None:
                self._reject_unsafe_path(folder)
                return

        if not os.path.exists(target_dir):
            # 回退到 assets 目录（同样校验不越界）
            if folder:
                target_dir = self._resolve_safe_path(ASSETS_DIR, folder)
                if target_dir is None:
                    self._reject_unsafe_path(folder)
                    return
            else:
                target_dir = ASSETS_DIR

        if not os.path.exists(target_dir):
            self.send_error(404, f'Folder not found: {folder}')
            return

        try:
            files = []
            # 递归获取所有文件，排除系统目录
            for root, dirs, filenames in os.walk(target_dir):
                # 过滤掉排除的目录
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith('.')]

                for filename in filenames:
                    # 排除系统文件
                    if filename.startswith('.') or filename.endswith(('.py', '.yml', '.exe', '.sh')):
                        continue

                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, target_dir)
                    stat = os.stat(file_path)
                    files.append({
                        'name': filename,
                        'path': rel_path.replace('\\', '/'),
                        'size': stat.st_size,
                        'modifiedTime': stat.st_mtime,
                        'type': 'file'
                    })

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'files': files}, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def serve_static_file(self, file_path):
        """提供静态文件服务（支持压缩和缓存）"""
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            with open(file_path, 'rb') as f:
                content = f.read()

            # 检查客户端是否支持 gzip
            accept_encoding = self.headers.get('Accept-Encoding', '')
            supports_gzip = 'gzip' in accept_encoding

            # 判断是否应该压缩
            should_compress = supports_gzip and self.should_compress(mime_type, len(content))

            # 准备响应内容
            if should_compress:
                compressed_content = self.compress_content(content)
                response_content = compressed_content
            else:
                response_content = content

            # 发送响应
            self.send_response(200)
            self.send_header('Content-type', mime_type)

            # 添加压缩头
            if should_compress:
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Vary', 'Accept-Encoding')

            self.send_header('Content-Length', len(response_content))

            # 添加缓存头
            self.add_cache_headers(mime_type, content)

            self.end_headers()
            self.wfile.write(response_content)
        except Exception as e:
            self.send_error(500, str(e))

    def serve_swagger_ui(self):
        """提供 Swagger UI 页面"""
        try:
            swagger_html_path = os.path.join(BASE_DIR, 'server', 'swagger', 'index.html')

            if not os.path.exists(swagger_html_path):
                self.send_error(404, 'Swagger UI not found')
                return

            with open(swagger_html_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(content.encode('utf-8')))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except Exception as e:
            print(f"提供 Swagger UI 失败: {e}")
            self.send_error(500, str(e))

    def serve_openapi_yaml(self):
        """提供 OpenAPI YAML 文件"""
        try:
            yaml_path = os.path.join(BASE_DIR, 'server', 'swagger', 'openapi.yaml')

            if not os.path.exists(yaml_path):
                self.send_error(404, 'OpenAPI specification not found')
                return

            with open(yaml_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-type', 'text/yaml; charset=utf-8')
            self.send_header('Content-Length', len(content.encode('utf-8')))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except Exception as e:
            print(f"提供 OpenAPI YAML 失败: {e}")
            self.send_error(500, str(e))

    def count_files_recursive(self, folder):
        """统计目录中的文件和文件夹数量（文件夹只统计直接子目录，文件递归统计）"""
        if folder:
            target_dir = self._resolve_safe_path(ARCHIVES_DIR, folder)
            if target_dir is None:
                self._reject_unsafe_path(folder)
                return
        else:
            target_dir = ARCHIVES_DIR

        folder_count = 0
        file_count = 0

        if not os.path.exists(target_dir):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'folders': 0, 'files': 0}).encode())
            return

        for item in os.listdir(target_dir):
            item_path = os.path.join(target_dir, item)
            if os.path.isdir(item_path):
                folder_count += 1

        for root, dirs, files in os.walk(target_dir):
            file_count += len(files)

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'folders': folder_count, 'files': file_count}).encode())

    def create_folder(self, folder_path):
        if not folder_path:
            self.send_error(400, 'No folder path provided')
            return

        # 安全修复：校验路径必须落在归档目录内
        full_path = self._resolve_safe_path(ARCHIVES_DIR, folder_path)
        if full_path is None:
            self._reject_unsafe_path(folder_path)
            return

        try:
            os.makedirs(full_path, exist_ok=True)
            print(f"创建文件夹: {full_path}")
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({'success': True, 'message': f'Created: {folder_path}', 'path': full_path}, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))
        except Exception as e:
            print(f"创建文件夹失败: {e}")
            self.send_error(500, str(e))

    def delete_file(self, file_path):
        """删除文件（支持 assets 和 archives 目录）"""
        if not file_path:
            self.send_error(400, 'No file path provided')
            return

        # URL 解码路径
        file_path = unquote(file_path)
        print(f"删除文件请求: {file_path}")

        try:
            # 安全修复：按前缀选择基准目录，并强制校验路径不越界
            normalized = file_path.replace('/', os.sep)
            if normalized.startswith('assets' + os.sep) or normalized.startswith('assets/'):
                base_dir = ASSETS_DIR
                relative = normalized[len('assets'):].lstrip('/\\')
            elif normalized.startswith('archives' + os.sep) or normalized.startswith('archives/'):
                base_dir = ARCHIVES_DIR
                relative = normalized[len('archives'):].lstrip('/\\')
            elif normalized.startswith(self.ARCHIVE_TOP_DIRS):
                base_dir = ARCHIVES_DIR
                relative = normalized
            else:
                base_dir = ASSETS_DIR
                relative = normalized

            full_path = self._resolve_safe_path(base_dir, relative)
            if full_path is None:
                self._reject_unsafe_path(file_path)
                return

            print(f"尝试删除文件: {full_path}")

            if os.path.exists(full_path):
                os.remove(full_path)
                print(f"删除文件成功: {full_path}")

                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({'success': True, 'message': 'File deleted', 'path': file_path}, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
            else:
                print(f"文件不存在: {full_path}")
                # 尝试列出目录内容
                dir_path = os.path.dirname(full_path)
                print(f"检查目录是否存在: {os.path.exists(dir_path)}")
                if os.path.exists(dir_path):
                    try:
                        files = os.listdir(dir_path)
                        print(f"目录内容 ({len(files)} 个文件): {files[:10]}")
                    except Exception as e:
                        print(f"列出目录内容失败: {e}")
                self.send_error(404, f'File not found: {file_path}')
        except Exception as e:
            print(f"删除文件失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def scan_player_files(self, player_name):
        """扫描选手归档文件夹，返回已有的资料类型"""
        try:
            # 安全修复：净化选手名并校验路径不越出归档目录
            player_folder = self._resolve_material_dir(ARCHIVES_DIR, ('02_选手档案', player_name))
            if player_folder is None:
                self._reject_unsafe_path(player_name)
                return

            print(f"扫描选手文件夹: {player_folder}")

            if not os.path.exists(player_folder):
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': True,
                    'player_name': player_name,
                    'materials': [],
                    'message': '选手文件夹不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 扫描所有子文件夹中的文件
            materials = []
            try:
                subfolders = os.listdir(player_folder)
            except Exception as e:
                print(f"无法读取选手文件夹: {player_folder}, 错误: {e}")
                subfolders = []

            for subfolder in subfolders:
                subfolder_path = os.path.join(player_folder, subfolder)
                if os.path.isdir(subfolder_path):
                    try:
                        files = os.listdir(subfolder_path)
                    except Exception as e:
                        print(f"无法读取子文件夹: {subfolder_path}, 错误: {e}")
                        files = []

                    for file_name in files:
                        file_path = os.path.join(subfolder_path, file_name)
                        if os.path.isfile(file_path):
                            # 从文件名解析资料类型
                            # 文件名格式: 选手名_阶段_资料类型_时间戳.扩展名
                            try:
                                parts = file_name.rsplit('.', 1)[0].split('_')
                                if len(parts) >= 3:
                                    material_type = parts[2]
                                else:
                                    material_type = '未知'
                            except Exception:
                                material_type = '未知'

                            try:
                                file_size = os.path.getsize(file_path)
                            except Exception:
                                file_size = 0

                            materials.append({
                                'type': material_type,
                                'name': file_name,
                                'folder': subfolder,
                                'path': f'02_选手档案/{player_name}/{subfolder}/{file_name}',
                                'size': file_size
                            })

            print(f"找到 {len(materials)} 个文件: {[m['type'] for m in materials]}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'player_name': player_name,
                'materials': materials,
                'material_types': list(set(m['type'] for m in materials))  # 去重后的资料类型列表
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"扫描选手文件夹失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            print(f"ARCHIVES_DIR: {ARCHIVES_DIR}")
            print(f"player_name: {player_name}")
            self.send_error(500, str(e))

    def download_player_material(self, player_name, file_name, preview=False, material_type=None):
        """下载选手/机构/项目资料"""
        try:
            # 安全修复：净化名称并校验路径不越出归档目录
            # 修复：补传 material_type 并开启子目录兜底搜索，否则资料存在类型子目录里时必然 404
            file_path = self._resolve_material_candidate(
                ('02_选手档案', '03_合作机构', '01_项目资料'), player_name, file_name,
                material_type, allow_subdir_search=True)

            if file_path is None:
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': False,
                    'message': '文件不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 获取文件 MIME 类型
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            # 读取文件并发送
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # 预览模式用 inline，下载模式用 attachment
            disposition = 'inline' if preview else 'attachment'

            self.send_response(200)
            self.send_header('Content-type', mime_type)
            self.send_header('Content-Disposition', self._content_disposition(disposition, file_name))
            self.send_header('Content-Length', len(file_content))
            self.end_headers()
            self.wfile.write(file_content)

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"下载资料失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def delete_player_material(self, player_name, file_name):
        """删除选手/机构/项目资料"""
        try:
            # 安全修复：净化名称并校验路径不越出归档目录
            file_path = self._resolve_material_candidate(
                ('02_选手档案', '03_合作机构', '01_项目资料'), player_name, file_name)

            if file_path is None:
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': False,
                    'message': '文件不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 删除文件
            os.remove(file_path)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'message': '删除成功'
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"删除资料失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def scan_project_files(self, project_name):
        """扫描项目归档文件夹，返回已有的资料类型"""
        try:
            # 安全修复：净化项目名并校验路径不越出归档目录
            project_folder = self._resolve_material_dir(ARCHIVES_DIR, ('01_项目资料', project_name))
            if project_folder is None:
                self._reject_unsafe_path(project_name)
                return

            print(f"扫描项目文件夹: {project_folder}")

            if not os.path.exists(project_folder):
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': True,
                    'project_name': project_name,
                    'materials': [],
                    'message': '项目文件夹不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 扫描所有子文件夹中的文件
            materials = []
            try:
                subfolders = os.listdir(project_folder)
            except Exception as e:
                print(f"无法读取项目文件夹: {project_folder}, 错误: {e}")
                subfolders = []

            for subfolder in subfolders:
                subfolder_path = os.path.join(project_folder, subfolder)
                if os.path.isdir(subfolder_path):
                    try:
                        files = os.listdir(subfolder_path)
                    except Exception as e:
                        print(f"无法读取子文件夹: {subfolder_path}, 错误: {e}")
                        files = []

                    for file_name in files:
                        file_path = os.path.join(subfolder_path, file_name)
                        if os.path.isfile(file_path):
                            # 从文件名解析资料类型
                            try:
                                parts = file_name.rsplit('.', 1)[0].split('_')
                                if len(parts) >= 2:
                                    material_type = parts[1]
                                else:
                                    material_type = '未知'
                            except Exception:
                                material_type = '未知'

                            try:
                                file_size = os.path.getsize(file_path)
                            except Exception:
                                file_size = 0

                            materials.append({
                                'type': material_type,
                                'name': file_name,
                                'folder': subfolder,
                                'path': f'01_项目资料/{project_name}/{subfolder}/{file_name}',
                                'size': file_size
                            })

            print(f"找到 {len(materials)} 个文件: {[m['type'] for m in materials]}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'project_name': project_name,
                'materials': materials,
                'material_types': list(set(m['type'] for m in materials))
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"扫描项目文件夹失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def download_project_material(self, project_name, file_name, preview=False, material_type=None):
        """下载项目资料"""
        try:
            # 构建文件路径
            # 安全修复：净化名称并校验路径不越出归档目录
            # 修复：补传 material_type 并开启子目录兜底搜索，否则资料存在类型子目录里时必然 404
            file_path = self._resolve_material_candidate(
                ('01_项目资料',), project_name, file_name,
                material_type, allow_subdir_search=True)

            if file_path is None:
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': False,
                    'message': '文件不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 获取文件类型和大小
            file_size = os.path.getsize(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            # 读取文件内容
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # 预览模式用 inline，下载模式用 attachment（与选手/机构保持一致）
            disposition = 'inline' if preview else 'attachment'

            self.send_response(200)
            self.send_header('Content-type', mime_type)
            self.send_header('Content-Disposition', self._content_disposition(disposition, file_name))
            self.send_header('Content-Length', len(file_content))
            self.end_headers()
            self.wfile.write(file_content)

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"下载项目资料失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def delete_project_material(self, project_name, file_name):
        """删除项目资料"""
        try:
            # 构建文件路径
            # 安全修复：净化名称并校验路径不越出归档目录
            file_path = self._resolve_material_candidate(('01_项目资料',), project_name, file_name)

            if file_path is None:
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': False,
                    'message': '文件不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 删除文件
            os.remove(file_path)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'message': '删除成功'
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"删除项目资料失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def scan_org_files(self, org_name):
        """扫描机构归档文件夹，返回已有的资料类型"""
        try:
            # 安全修复：净化机构名并校验路径不越出归档目录
            org_folder = self._resolve_material_dir(ARCHIVES_DIR, ('03_合作机构', org_name))
            if org_folder is None:
                self._reject_unsafe_path(org_name)
                return

            print(f"扫描机构文件夹: {org_folder}")

            if not os.path.exists(org_folder):
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': True,
                    'org_name': org_name,
                    'materials': [],
                    'message': '机构文件夹不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 扫描所有子文件夹中的文件
            materials = []
            try:
                subfolders = os.listdir(org_folder)
            except Exception as e:
                print(f"无法读取机构文件夹: {org_folder}, 错误: {e}")
                subfolders = []

            for subfolder in subfolders:
                subfolder_path = os.path.join(org_folder, subfolder)
                if os.path.isdir(subfolder_path):
                    try:
                        files = os.listdir(subfolder_path)
                    except Exception as e:
                        print(f"无法读取子文件夹: {subfolder_path}, 错误: {e}")
                        files = []

                    for file_name in files:
                        file_path = os.path.join(subfolder_path, file_name)
                        if os.path.isfile(file_path):
                            # 资料类型从文件夹名获取（上传时资料类型作为文件夹名保存）
                            material_type = subfolder

                            try:
                                file_size = os.path.getsize(file_path)
                            except Exception:
                                file_size = 0

                            materials.append({
                                'type': material_type,
                                'name': file_name,
                                'folder': subfolder,
                                'path': f'03_合作机构/{org_name}/{subfolder}/{file_name}',
                                'size': file_size
                            })

            print(f"找到 {len(materials)} 个文件: {[m['type'] for m in materials]}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'org_name': org_name,
                'materials': materials,
                'material_types': list(set(m['type'] for m in materials))
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"扫描机构文件夹失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    # 可做无依赖文本提取的 OOXML 格式（本质是 zip + XML）
    OOXML_EXTS = ('.docx', '.docm', '.xlsx', '.xlsm', '.pptx', '.pptm')
    # 旧版二进制 Office 格式：无法无依赖提取，需提示用户下载
    LEGACY_OFFICE_EXTS = ('.doc', '.xls', '.ppt')
    # 纯文本类格式
    PLAIN_TEXT_EXTS = (
        '.txt', '.md', '.markdown', '.json', '.xml', '.csv', '.tsv', '.log',
        '.html', '.htm', '.css', '.js', '.ts', '.yml', '.yaml', '.ini', '.cfg',
        '.conf', '.py', '.java', '.sql', '.sh', '.bat', '.ps1', '.srt', '.vtt',
    )

    def extract_office_text(self, file_path):
        """
        从 OOXML 文件（docx/xlsx/pptx）中提取纯文本，使用标准库无额外依赖。

        返回：提取到的文本；无法提取时返回 None。

        修复：此前用 `zipfile.ZipFile()` 打开 PDF，必然抛 BadZipFile，
        然后落进兜底分支把文件**前 8192 字节当文本返回** —— 于是 .doc / .pdf
        在预览面板里显示一堆二进制乱码。现在：
          - 只对真正的 OOXML 格式做提取；
          - 非 zip（.doc/.pdf）或损坏文件明确返回 None，由上层给出可读提示；
          - 绝不返回文件原始字节。
        """
        import zipfile
        import xml.etree.ElementTree as ET

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.OOXML_EXTS:
            return None

        W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        S_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        A_NS = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
        text_parts = []

        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                if ext in ('.docx', '.docm'):
                    doc_xml = z.read('word/document.xml')
                    root = ET.fromstring(doc_xml)
                    # 按段落聚合，避免一个段落的多个 run 被拆成多行
                    for p in root.iter(f'{W_NS}p'):
                        runs = [t.text for t in p.iter(f'{W_NS}t') if t.text]
                        if runs:
                            text_parts.append(''.join(runs))

                elif ext in ('.xlsx', '.xlsm'):
                    if 'xl/sharedStrings.xml' in z.namelist():
                        ss_xml = z.read('xl/sharedStrings.xml')
                        root = ET.fromstring(ss_xml)
                        for t in root.iter(f'{S_NS}t'):
                            if t.text:
                                text_parts.append(t.text)
                    else:
                        for sheet_name in z.namelist():
                            if sheet_name.startswith('xl/worksheets/sheet') and sheet_name.endswith('.xml'):
                                try:
                                    sheet_xml = z.read(sheet_name)
                                    root = ET.fromstring(sheet_xml)
                                    for v in root.iter(f'{S_NS}v'):
                                        if v.text:
                                            text_parts.append(v.text)
                                except Exception:
                                    continue

                elif ext in ('.pptx', '.pptm'):
                    slide_files = sorted(
                        n for n in z.namelist()
                        if n.startswith('ppt/slides/slide') and n.endswith('.xml')
                    )
                    for idx, slide_file in enumerate(slide_files, 1):
                        try:
                            slide_xml = z.read(slide_file)
                            root = ET.fromstring(slide_xml)
                            slide_text = [t.text for t in root.iter(f'{A_NS}t') if t.text]
                            if slide_text:
                                text_parts.append(f'―― 第 {idx} 页 ――\n' + ''.join(slide_text))
                        except Exception:
                            continue

        except (zipfile.BadZipFile, KeyError) as e:
            print(f"文档不是有效的 OOXML 压缩包，无法提取文本: {file_path} ({e})")
            return None
        except Exception as e:
            print(f"提取文件文本失败: {e}")
            return None

        result = '\n'.join(text_parts).strip()
        return result or None

    @staticmethod
    def read_plain_text(file_path, max_bytes=2000000):
        """读取纯文本文件，按常见中文编码依次尝试（utf-8 → gb18030 → big5 → latin-1）"""
        with open(file_path, 'rb') as f:
            raw = f.read(max_bytes)
        for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'big5'):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace')

    def preview_file_text(self, source, name, file_name, material_type='', path=''):
        """返回文件的纯文本内容用于预览"""
        is_valid, _, error = self._check_auth_and_permission('read')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 安全修复：统一走净化 + 越界校验的路径解析
        # 修复：三个来源统一开启 allow_subdir_search——归档资料按类型存于子目录，
        #      不开启则选手/项目的资料永远找不到（此前 org 开了、player/project 没开）
        path_map = {
            'org': lambda: self._resolve_material_candidate(
                ('03_合作机构',), name, file_name, material_type, allow_subdir_search=True),
            'player': lambda: self._resolve_material_candidate(
                ('02_选手档案',), name, file_name, material_type, allow_subdir_search=True),
            'project': lambda: self._resolve_material_candidate(
                ('01_项目资料',), name, file_name, material_type, allow_subdir_search=True),
            # 归档页/素材库按相对路径预览（path 形如 01_项目资料/xxx/yyy.docx）
            'file': lambda: self._resolve_material_path(path),
        }

        resolver = path_map.get(source)
        if not resolver:
            self.send_response(400)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'message': f'无效的来源类型: {source}'}, ensure_ascii=False).encode())
            return

        file_path = resolver()

        if not file_path or not os.path.exists(file_path):
            self.send_response(404)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'message': '文件不存在'}, ensure_ascii=False).encode())
            return

        ext = os.path.splitext(file_name)[1].lower()

        text_content = None
        # 提取失败时给用户一句能看懂的原因，而不是笼统的"不支持"
        fail_message = None

        if ext in self.OOXML_EXTS:
            text_content = self.extract_office_text(file_path)
            if not text_content:
                fail_message = '已打开该文档，但里面没有可提取的文字（可能是纯图片或空文档）'
        elif ext in self.LEGACY_OFFICE_EXTS:
            fail_message = f'旧版 Office 格式（{ext}）无法在线提取文字，请下载后用本机 Office 打开'
        elif ext == '.pdf':
            # PDF 的文本提取需要专门的解析库，这里不做；前端会走内置 PDF 阅读器（iframe）渲染
            fail_message = 'PDF 请使用内置阅读器查看（本接口不提取 PDF 文字）'
        elif ext in self.PLAIN_TEXT_EXTS:
            try:
                text_content = self.read_plain_text(file_path)
            except Exception as e:
                print(f"读取纯文本失败 {file_path}: {e}")
                fail_message = '读取文件内容失败'
        else:
            fail_message = f'暂不支持在线预览该格式（{ext or "无扩展名"}），请下载后查看'

        if text_content:
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'text': text_content[:100000],
                'fileName': file_name,
                'truncated': len(text_content) > 100000
            }, ensure_ascii=False)
            self.wfile.write(response.encode())
            return

        # 用 200 + success:false 返回，前端才能把具体原因显示在预览面板里
        # （返回 4xx 会被 http.js 当成请求失败，只显示"加载文件内容失败"）
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({
            'success': False,
            'message': fail_message or '无法提取文件内容'
        }, ensure_ascii=False).encode())

    def download_org_material(self, org_name, file_name, material_type='', preview=False):
        """下载/预览机构资料"""
        try:
            # 安全修复：净化名称并校验路径不越出归档目录
            file_path = self._resolve_material_candidate(
                ('03_合作机构',), org_name, file_name, material_type,
                allow_subdir_search=True)

            if file_path is None:
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': False,
                    'message': '文件不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 获取文件类型和大小
            file_size = os.path.getsize(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            # 读取文件内容
            with open(file_path, 'rb') as f:
                file_content = f.read()

            self.send_response(200)
            if preview:
                # 预览模式：内联显示
                self.send_header('Content-type', mime_type)
                self.send_header('Content-Disposition', self._content_disposition('inline', file_name))
            else:
                # 下载模式
                self.send_header('Content-type', mime_type)
                self.send_header('Content-Disposition', self._content_disposition('attachment', file_name))
            self.send_header('Content-Length', len(file_content))
            self.end_headers()
            self.wfile.write(file_content)

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"下载/预览机构资料失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def download_org_material_legacy(self, org_name, file_name, preview=False):
        """兼容旧调用：在所有子文件夹中查找文件"""
        try:
            # 安全修复：净化名称并校验路径不越出归档目录
            org_folder = self._resolve_material_dir(ARCHIVES_DIR, ('03_合作机构', org_name))
            if org_folder is None or not os.path.exists(org_folder):
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({'success': False, 'message': '机构文件夹不存在'}, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            file_path = self._resolve_material_candidate(
                ('03_合作机构',), org_name, file_name, allow_subdir_search=True)

            if not file_path:
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({'success': False, 'message': '文件不存在'}, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 获取文件类型和大小
            file_size = os.path.getsize(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            with open(file_path, 'rb') as f:
                file_content = f.read()

            self.send_response(200)
            if preview:
                self.send_header('Content-type', mime_type)
                self.send_header('Content-Disposition', self._content_disposition('inline', file_name))
            else:
                self.send_header('Content-type', 'application/octet-stream')
                self.send_header('Content-Disposition', self._content_disposition('attachment', file_name))
            self.send_header('Content-Length', file_size)
            self.end_headers()
            self.wfile.write(file_content)

        except Exception as e:
            self.send_error(500, str(e))

    def delete_org_material(self, org_name, file_name, material_type=None):
        """删除机构资料"""
        try:
            # 安全修复：净化名称并校验路径不越出归档目录
            file_path = self._resolve_material_candidate(
                ('03_合作机构',), org_name, file_name, material_type,
                allow_subdir_search=True)

            if not file_path:
                self.send_response(404)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                response = json.dumps({
                    'success': False,
                    'message': '文件不存在'
                }, ensure_ascii=False)
                self.wfile.write(response.encode('utf-8'))
                return

            # 删除文件
            os.remove(file_path)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'message': '删除成功'
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            import traceback
            print(f"删除机构资料失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def save_stage_materials(self, data):
        """保存 stageMaterials 配置"""
        try:
            import sqlite3
            db_file = os.path.join(DATA_DIR, 'workbench.db')
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            stage_materials = data.get('stageMaterials', {})
            material_types = data.get('materialTypes', [])
            archive_config = data.get('archiveConfig', {})

            # 保存到 SQLite
            if os.path.exists(db_file):
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
                ''', ('stageMaterials', json.dumps(stage_materials, ensure_ascii=False)))

                conn.commit()
                conn.close()
                print(f"已保存 stageMaterials 配置到 SQLite")

            # 保存到 JSON
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)

                if not json_data.get('config'):
                    json_data['config'] = {}
                json_data['config']['stageMaterials'] = stage_materials

                # 保存 materialTypes
                if material_types:
                    json_data['materialTypes'] = material_types
                    print(f"已保存 materialTypes 配置到 JSON")

                # 保存 archiveConfig
                if archive_config:
                    json_data['archiveConfig'] = archive_config
                    print(f"已保存 archiveConfig 配置到 JSON")

                # 统一走 _write_json_data，保证 materialTypes / config 同步到 SQLite
                self._write_json_data(json_data)
                print(f"已保存 stageMaterials 配置到 JSON")

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'message': '配置已保存'
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except Exception as e:
            import traceback
            print(f"保存 stageMaterials 配置失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def get_missing_materials(self):
        """获取缺失资料列表"""
        try:
            import sqlite3
            db_file = os.path.join(DATA_DIR, 'workbench.db')

            players = []

            # 从 SQLite 读取选手数据
            if os.path.exists(db_file):
                conn = sqlite3.connect(db_file)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('SELECT * FROM players')
                rows = cursor.fetchall()

                for row in rows:
                    player = dict(row)
                    if player.get('missingMaterials') and player.get('missingCount', 0) > 0:
                        players.append({
                            'id': player['id'],
                            'name': player['name'],
                            'stage': player.get('stage', ''),
                            'missingCount': player.get('missingCount', 0),
                            'missingTypes': player.get('missingTypes', [])
                        })

                conn.close()

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'players': players
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except Exception as e:
            import traceback
            print(f"获取缺失资料失败：{e}")
            print(f"详细错误：{traceback.format_exc()}")
            self.send_error(500, str(e))

    def open_archive_file(self, filepath):
        if not filepath:
            self.send_error(400, 'No file path provided')
            return

        # 安全修复：校验路径必须落在归档目录内
        full_path = self._resolve_safe_path(ARCHIVES_DIR, filepath)
        if full_path is None:
            self._reject_unsafe_path(filepath)
            return

        if not os.path.exists(full_path):
            self.send_error(404, f'File not found: {filepath}')
            return

        try:
            os.startfile(full_path)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'message': f'Opened: {filepath}'}).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def delete_folder(self, folder_path):
        if not folder_path:
            self.send_error(400, 'No folder path provided')
            return

        # 安全修复：校验路径必须落在归档目录内，禁止 rmtree 越界
        full_path = self._resolve_safe_path(ARCHIVES_DIR, folder_path)
        if full_path is None:
            self._reject_unsafe_path(folder_path)
            return

        # 禁止删除归档根目录本身
        if os.path.realpath(full_path) == os.path.realpath(ARCHIVES_DIR):
            self._send_json(400, {
                'success': False,
                'message': '不允许删除归档根目录',
                'error': 'INVALID_TARGET'
            })
            return

        if not os.path.exists(full_path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'message': 'Folder does not exist', 'path': full_path}).encode())
            return

        try:
            import shutil
            shutil.rmtree(full_path)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'message': f'Deleted: {folder_path}', 'path': full_path}).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def rename_folder(self, old_path, new_name):
        """重命名文件夹"""
        if not old_path or not new_name:
            self.send_error(400, 'Missing parameters')
            return

        # URL 解码路径
        old_path = unquote(old_path)
        new_name = unquote(new_name)

        try:
            # 安全修复：旧路径必须落在归档目录内；新名称不允许含路径分隔符
            old_full_path = self._resolve_safe_path(ARCHIVES_DIR, old_path)
            if old_full_path is None:
                self._reject_unsafe_path(old_path)
                return
            if os.sep in new_name or '/' in new_name or new_name in ('.', '..'):
                self._send_json(400, {
                    'success': False,
                    'message': '新名称不能包含路径分隔符',
                    'error': 'INVALID_NAME'
                })
                return

            if not os.path.exists(old_full_path):
                self.send_error(404, f'Folder not found: {old_path}')
                return

            if not os.path.isdir(old_full_path):
                self.send_error(400, 'Not a folder')
                return

            # 构建新路径
            parent_dir = os.path.dirname(old_full_path)
            new_full_path = os.path.join(parent_dir, new_name)

            if os.path.exists(new_full_path):
                self.send_error(400, f'Folder already exists: {new_name}')
                return

            os.rename(old_full_path, new_full_path)
            print(f"重命名文件夹: {old_full_path} -> {new_full_path}")

            # 构建新的相对路径
            new_path = os.path.join(os.path.dirname(old_path), new_name) if os.path.dirname(old_path) else new_name

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            response = json.dumps({
                'success': True,
                'message': f'Renamed to: {new_name}',
                'old_path': old_path,
                'new_path': new_path,
                'new_name': new_name
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))
        except Exception as e:
            print(f"重命名文件夹失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def list_archives(self, folder):
        # 安全修复：校验路径必须落在归档目录内
        if folder:
            target_dir = self._resolve_safe_path(ARCHIVES_DIR, folder)
            if target_dir is None:
                self._reject_unsafe_path(folder)
                return
        else:
            target_dir = ARCHIVES_DIR

        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                self.send_error(500, str(e))
                return

        try:
            files = []
            for item in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item)
                is_dir = os.path.isdir(item_path)
                relative_path = f"{folder}/{item}" if folder else item
                file_info = {
                    'name': item,
                    'type': 'folder' if is_dir else 'file',
                    'path': relative_path
                }
                if not is_dir:
                    try:
                        file_info['size'] = os.path.getsize(item_path)
                        file_info['modified'] = os.path.getmtime(item_path)
                    except:
                        pass
                files.append(file_info)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(files).encode())
        except Exception as e:
            self.send_error(500, str(e))

    # ========== 数据存储 API ==========

    def get_archive_path(self):
        """获取归档目录配置"""
        try:
            config = load_config()
            archives_path = config.get('archivesPath', '')
            default_path = DEFAULT_ARCHIVES_DIR

            # 检查路径是否有效
            is_valid = True
            if archives_path:
                is_valid = os.path.isabs(archives_path)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'path': archives_path if archives_path else default_path,
                'defaultPath': default_path,
                'isCustom': bool(archives_path),
                'isValid': is_valid
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def set_archive_path(self, new_path):
        """设置归档目录"""
        try:
            config = load_config()

            if new_path:
                # 验证路径
                if not os.path.isabs(new_path):
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'message': '路径必须是绝对路径'
                    }, ensure_ascii=False).encode())
                    return

                # 创建目录（如果不存在）
                try:
                    os.makedirs(new_path, exist_ok=True)
                except Exception as e:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'message': f'无法创建目录: {str(e)}'
                    }, ensure_ascii=False).encode())
                    return

                config['archivesPath'] = new_path
            else:
                # 清除自定义路径，使用默认
                config.pop('archivesPath', None)

            if save_config(config):
                # 更新全局变量
                global ARCHIVES_DIR
                ARCHIVES_DIR = get_archives_dir()

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'path': ARCHIVES_DIR,
                    'message': '归档目录已更新'
                }, ensure_ascii=False).encode())
            else:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '保存配置失败'
                }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def get_resources_path(self):
        """获取资源目录配置"""
        try:
            config = load_config()
            resources_path = config.get('resourcesPath', '')

            # 检查路径是否有效
            is_valid = True
            if resources_path:
                is_valid = os.path.isabs(resources_path)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'path': resources_path if resources_path else DEFAULT_RESOURCES_DIR,
                'defaultPath': DEFAULT_RESOURCES_DIR,
                'isCustom': bool(resources_path),
                'isValid': is_valid
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def set_resources_path(self, new_path):
        """设置资源目录"""
        try:
            config = load_config()

            if new_path:
                # 验证路径
                if not os.path.isabs(new_path):
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'message': '路径必须是绝对路径'
                    }, ensure_ascii=False).encode())
                    return

                # 创建目录（如果不存在）
                try:
                    os.makedirs(new_path, exist_ok=True)
                except Exception as e:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'message': f'无法创建目录: {str(e)}'
                    }, ensure_ascii=False).encode())
                    return

                config['resourcesPath'] = new_path
            else:
                # 清除自定义路径，使用默认
                config.pop('resourcesPath', None)

            if save_config(config):
                # 更新全局变量
                global RESOURCES_DIR
                RESOURCES_DIR = get_resources_dir()

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'path': RESOURCES_DIR,
                    'message': '资源目录已更新'
                }, ensure_ascii=False).encode())
            else:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '保存配置失败'
                }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def set_resources_path_with_auth(self, new_path):
        """设置资源目录（需要 admin 权限）"""
        is_valid, _, error = self._check_auth_and_permission('manage_config')
        if not is_valid:
            self._send_permission_error(error)
            return

        # 调用原始设置方法
        self.set_resources_path(new_path)

    def get_audit_logs(self):
        """获取审计日志"""
        try:
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')
            logs = []
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logs = data.get('auditLogs', [])

            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            action_type = params.get('actionType', [None])[0]
            if action_type:
                logs = [l for l in logs if l.get('actionType') == action_type]

            logs.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'logs': logs
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'获取审计日志失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def add_audit_log(self, data):
        """添加审计日志"""
        try:
            import random
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')
            file_data = {}
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)

            if 'auditLogs' not in file_data:
                file_data['auditLogs'] = []

            log_entry = {
                'id': f'al_{int(time.time())}_{random.randint(1000, 9999)}',
                'action': data.get('action', ''),
                'actionType': data.get('actionType', 'update'),
                'target': data.get('target', ''),
                'description': data.get('description', ''),
                'userName': data.get('userName', '系统'),
                'ip': data.get('ip', ''),
                'createdAt': time.strftime('%Y-%m-%d %H:%M:%S')
            }

            file_data['auditLogs'].append(log_entry)

            # 统一走 _write_json_data，保证审计日志同时落 SQLite
            # （此前直写 JSON，导致库里少日志、重启后读 SQLite 就看不到）
            self._write_json_data(file_data)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'log': log_entry
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'添加审计日志失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def _read_json_data(self):
        json_file = os.path.join(DATA_DIR, 'workbench_data.json')
        if os.path.exists(json_file):
            with open(json_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _write_json_data(self, data):
        """
        写入 JSON 数据文件，并同步到 SQLite。

        修复：load_data 读取时以 SQLite 为优先数据源，而用户管理等写操作
        过去只写 JSON，导致重启后数据回退。此处统一双写以保证一致性。
        """
        json_file = os.path.join(DATA_DIR, 'workbench_data.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        try:
            from server.database import get_data_store
            store = get_data_store()
            if store and hasattr(store, 'save_all_data'):
                store.save_all_data(data)
        except Exception as e:
            print(f"同步数据到 SQLite 失败: {e}")

    def change_password(self, data):
        """
        修改用户密码（POST /api/users/change-password）

        安全约束：
        - 已通过统一认证门禁（必须已登录）
        - 仅允许修改本人密码；admin 可修改他人密码
        - 新密码不得少于 6 位
        """
        try:
            user_id = (data.get('userId') or '').strip()
            new_password = data.get('newPassword') or ''

            if not user_id or not new_password:
                self._send_json(400, {
                    'success': False,
                    'message': '缺少 userId 或 newPassword',
                    'error': 'MISSING_PARAMS'
                })
                return

            if len(new_password) < 6:
                self._send_json(400, {
                    'success': False,
                    'message': '密码长度至少6位',
                    'error': 'PASSWORD_TOO_SHORT'
                })
                return

            current = self.current_user or {}
            requester_id = current.get('user_id') or current.get('userId')
            requester_role = current.get('role', 'viewer')
            if requester_id != user_id and requester_role != 'admin':
                self._send_json(403, {
                    'success': False,
                    'message': '只能修改自己的密码',
                    'error': 'FORBIDDEN'
                })
                return

            file_data = self._read_json_data()
            users = file_data.get('users', [])
            target = next((u for u in users if u.get('id') == user_id), None)
            if target is None:
                self._send_json(404, {
                    'success': False,
                    'message': '用户不存在',
                    'error': 'USER_NOT_FOUND'
                })
                return

            hashed = hash_password(new_password)
            if not hashed:
                self._send_json(500, {
                    'success': False,
                    'message': '密码加密失败',
                    'error': 'HASH_FAILED'
                })
                return

            now = time.strftime('%Y-%m-%d %H:%M:%S')
            target['password'] = hashed
            target['passwordHashed'] = 1
            target['passwordMigratedAt'] = now
            target['updatedAt'] = now
            target['mustChangePassword'] = False
            self._write_json_data(file_data)

            self._send_json(200, {
                'success': True,
                'message': '密码修改成功'
            })
        except Exception as e:
            print(f"修改密码失败: {e}")
            self._send_json(500, {
                'success': False,
                'message': f'修改密码失败: {str(e)}'
            })

    def open_resource_file(self, file_path):
        """
        用本地默认程序打开素材资源文件（POST /api/open-resource）

        安全约束：路径必须落在 RESOURCES_DIR 内，禁止越界。
        """
        if not file_path:
            self._send_json(400, {
                'success': False,
                'message': '缺少 path 参数',
                'error': 'MISSING_PARAMS'
            })
            return

        full_path = self._resolve_safe_path(RESOURCES_DIR, file_path)
        if full_path is None:
            self._reject_unsafe_path(file_path)
            return

        if not os.path.exists(full_path):
            self._send_json(404, {
                'success': False,
                'message': '文件不存在',
                'error': 'FILE_NOT_FOUND'
            })
            return

        try:
            self._open_in_explorer(full_path)
            self._send_json(200, {
                'success': True,
                'message': f'已打开: {os.path.basename(full_path)}'
            })
        except Exception as e:
            print(f"打开资源文件失败: {e}")
            self._send_json(500, {
                'success': False,
                'message': f'打开失败: {str(e)}'
            })

    def _open_in_explorer(self, path):
        """
        跨平台在系统文件管理器中打开 path（文件或目录）。

        - Windows: os.startfile（文件用默认程序打开，目录则打开资源管理器）
        - macOS:   open
        - Linux:   xdg-open
        """
        if sys.platform.startswith('win'):
            os.startfile(path)
        elif sys.platform.startswith('darwin'):
            subprocess.run(['open', path], check=False)
        else:
            subprocess.run(['xdg-open', path], check=False)

    def open_resource_folder(self, folder_path):
        """
        在系统文件管理器中打开素材资源目录（POST /api/open-folder）。

        - 不传 path 或传空  -> 打开 RESOURCES_DIR 根目录；
        - 传入相对子目录     -> 打开该子目录（仍受 RESOURCES_DIR 越界约束）。

        安全约束：路径必须落在 RESOURCES_DIR 内，禁止越界。
        """
        if not folder_path:
            target_dir = os.path.realpath(RESOURCES_DIR)
        else:
            target_dir = self._resolve_safe_path(RESOURCES_DIR, folder_path)
            if target_dir is None:
                self._reject_unsafe_path(folder_path)
                return

        # 子目录尚不存在时回退到根目录，避免点击无反应
        if not os.path.isdir(target_dir):
            print(f"[open-folder] 目标目录不存在，回退到根目录: {target_dir}")
            target_dir = os.path.realpath(RESOURCES_DIR)

        try:
            self._open_in_explorer(target_dir)
            self._send_json(200, {
                'success': True,
                'message': f'已打开文件夹: {target_dir}'
            })
        except Exception as e:
            print(f"打开文件夹失败: {e}")
            self._send_json(500, {
                'success': False,
                'message': f'打开文件夹失败: {str(e)}'
            })

    def get_users(self):
        try:
            data = self._read_json_data()
            users = data.get('users', [])
            # 安全修复：绝不在响应中返回密码/哈希等敏感字段
            SENSITIVE_FIELDS = {'password', 'passwordHash', 'passwordHashed', 'salt', 'token', 'secret'}
            safe_users = [
                {k: v for k, v in user.items() if k not in SENSITIVE_FIELDS}
                if isinstance(user, dict) else user
                for user in users
            ]
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'users': safe_users
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'获取用户列表失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def add_user(self, data):
        """
        新增用户（POST /api/users）

        数据一致性修复：users 表有 `username` / `password` 两个 NOT NULL 约束，
        而此前的实现只写入 `name`，既没有登录名也没有密码，导致：
          1) 新增的用户无法登录，根本不是账号；
          2) SQLite 同步时抛 IntegrityError: NOT NULL constraint failed: users.username，
             整表同步被拖垮（JSON 有、库没有），重启后从 SQLite 读出来用户就消失了。
        现在改为落一条完整的账号记录：
          - username：表单传值，缺省则由邮箱前缀/显示名派生并保证唯一；
          - password：表单传值，缺省则生成随机初始密码（仅在响应里回传一次）；
          - name / realName：两者都写，兼顾前端展示与账号字段命名。
        """
        try:
            import random
            import re

            file_data = self._read_json_data()
            if not isinstance(file_data.get('users'), list):
                file_data['users'] = []
            users = file_data['users']

            # 安全修复：role 只允许系统内已定义的角色，禁止自行提权为 admin
            requested_role = data.get('role', 'viewer')
            if requested_role not in ROLE_PERMISSIONS:
                requested_role = 'viewer'

            display_name = (data.get('realName') or data.get('name') or '').strip()

            # 登录名：优先取表单值，否则由邮箱前缀或显示名派生，冲突时追加序号
            username = (data.get('username') or '').strip()
            if not username:
                seed = (data.get('email') or '').split('@')[0] or display_name or 'user'
                username = re.sub(r'[^0-9A-Za-z_.-]', '', seed) or 'user'
            existing_usernames = {
                u.get('username') for u in users if isinstance(u, dict)
            }
            base_username = username
            suffix = 1
            while username in existing_usernames:
                suffix += 1
                username = f'{base_username}{suffix}'

            # 初始密码：表单可指定；未指定则随机生成，并在响应中回传一次供管理员转交
            raw_password = data.get('password') or ''
            generated_password = None
            if not raw_password:
                alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
                generated_password = ''.join(random.choice(alphabet) for _ in range(10))
                raw_password = generated_password

            hashed = hash_password(decode_client_password(raw_password))
            if not hashed:
                self._send_json(500, {
                    'success': False,
                    'message': '密码加密失败'
                })
                return

            now = time.strftime('%Y-%m-%d %H:%M:%S')
            new_user = {
                'id': f'u_{int(time.time())}_{random.randint(1000, 9999)}',
                'username': username,
                'password': hashed,
                'passwordHashed': True,
                'mustChangePassword': bool(generated_password),
                'name': display_name,
                'realName': (data.get('realName') or display_name),
                'email': data.get('email', ''),
                'role': requested_role,
                'department': data.get('department', ''),
                'status': 'active',
                'createdAt': now,
                'updatedAt': now
            }

            users.append(new_user)
            self._write_json_data(file_data)

            # 响应中不返回密码，仅自动生成时回传一次性初始密码
            response_user = {k: v for k, v in new_user.items() if k != 'password'}
            payload = {'success': True, 'user': response_user}
            if generated_password:
                payload['initialPassword'] = generated_password
            self._send_json(200, payload)
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'添加用户失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def update_user(self, user_id, data):
        try:
            # 安全修复：只允许更新白名单字段，防止通过全量合并覆盖 password/username 等敏感字段。
            # 注意：role 之前不在白名单里，而前端编辑弹窗会提交 role，
            #      于是"改角色"永远是静默失效的——这里补上，同时用 ROLE_PERMISSIONS 校验取值。
            ALLOWED_UPDATE_FIELDS = {'name', 'realName', 'email', 'department', 'status', 'phone', 'role'}
            file_data = self._read_json_data()
            users = file_data.get('users', [])
            updated = False
            for i, u in enumerate(users):
                if u.get('id') == user_id:
                    for key, value in data.items():
                        if key not in ALLOWED_UPDATE_FIELDS:
                            continue
                        if key == 'role' and value not in ROLE_PERMISSIONS:
                            # 非法角色直接忽略，避免提权
                            continue
                        users[i][key] = value
                    users[i]['updatedAt'] = time.strftime('%Y-%m-%d %H:%M:%S')
                    updated = True
                    break

            if not updated:
                self._send_json(404, {
                    'success': False,
                    'message': f'用户不存在: {user_id}'
                })
                return

            file_data['users'] = users
            self._write_json_data(file_data)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'更新用户失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def delete_user(self, user_id):
        try:
            file_data = self._read_json_data()
            users = file_data.get('users', [])
            file_data['users'] = [u for u in users if u.get('id') != user_id]
            self._write_json_data(file_data)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'删除用户失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def toggle_user_status(self, user_id):
        try:
            file_data = self._read_json_data()
            users = file_data.get('users', [])
            new_status = 'active'
            for i, u in enumerate(users):
                if u.get('id') == user_id:
                    new_status = 'inactive' if u.get('status') == 'active' else 'active'
                    users[i]['status'] = new_status
                    break
            file_data['users'] = users
            self._write_json_data(file_data)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'status': new_status
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'切换用户状态失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def import_players_json(self, data):
        try:
            players_data = data.get('players', [])
            file_data = self._read_json_data()
            if 'players' not in file_data:
                file_data['players'] = []

            projects = file_data.get('projects', [])
            organizations = file_data.get('organizations', [])

            imported = 0
            failed = 0
            errors = []

            for i, p in enumerate(players_data):
                if not p.get('name') or not p.get('gender') or not p.get('category'):
                    failed += 1
                    errors.append(f'第{i+1}行：姓名、性别、艺术类别为必填')
                    continue

                if p.get('projectName'):
                    proj = next((pr for pr in projects if pr.get('name') == p['projectName']), None)
                    if proj:
                        p['projectId'] = proj.get('id')
                        p['project_id'] = proj.get('id')

                if p.get('orgName'):
                    org = next((o for o in organizations if o.get('name') == p['orgName']), None)
                    if org:
                        p['orgId'] = org.get('id')
                        p['org_id'] = org.get('id')

                p.pop('projectName', None)
                p.pop('orgName', None)

                if not p.get('id'):
                    p['id'] = f'pl_{int(time.time())}_{random.randint(1000, 9999)}'
                p['createdAt'] = time.strftime('%Y-%m-%d')
                p['updatedAt'] = time.strftime('%Y-%m-%d')

                file_data['players'].append(p)
                imported += 1

            self._write_json_data(file_data)

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'imported': imported,
                'failed': failed,
                'errors': errors
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'导入选手失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def import_players(self):
        try:
            import cgi
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers['Content-Type']
                }
            )

            file_item = form['file']
            if not file_item.filename:
                self.send_response(400)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '未选择文件'}).encode())
                return

            content = file_item.file.read().decode('utf-8-sig')
            lines = content.strip().split('\n')
            if len(lines) < 2:
                self.send_response(400)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': 'CSV文件为空或只有表头'}).encode())
                return

            headers = [h.strip() for h in lines[0].split(',')]
            players_data = []
            for line in lines[1:]:
                values = [v.strip() for v in line.split(',')]
                if len(values) < len(headers):
                    values.extend([''] * (len(headers) - len(values)))
                player = {}
                for j, header in enumerate(headers):
                    player[header] = values[j] if j < len(values) else ''
                players_data.append(player)

            self.import_players_json({'players': players_data})
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'导入选手失败: {str(e)}'
            }, ensure_ascii=False).encode())

    def load_data(self):
        """加载数据（需要认证）"""
        is_valid, _, error = self._check_auth_and_permission('read')
        if not is_valid:
            self._send_permission_error(error)
            return

        import time
        start_time = time.time()
        try:
            # 优先从 SQLite 数据库加载
            db_file = os.path.join(DATA_DIR, 'workbench.db')
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            data = None
            use_db = False

            # 检查数据库是否存在
            if os.path.exists(db_file):
                try:
                    data_store_load_start = time.time()
                    data_store = get_data_store()
                    data = data_store.load_all_data()
                    data_store_load_time = time.time() - data_store_load_start
                    use_db = True
                    print(f"从 SQLite 数据库加载数据，耗时: {data_store_load_time:.3f}秒")
                except Exception as e:
                    print(f"从数据库加载失败: {e}，尝试从 JSON 加载")
                    data = None

            load_time = time.time() - start_time

            # 如果数据库不存在或加载失败，从 JSON 加载
            if data is None and os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print("从 JSON 文件加载数据")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'data': data,
                'exists': data is not None,
                'source': 'sqlite' if use_db else 'json'
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def list_players_paginated(self, page, pageSize, search=''):
        """分页查询选手列表"""
        try:
            # 加载全部数据
            db_file = os.path.join(DATA_DIR, 'workbench.db')
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            players = []
            config_data = {}
            if os.path.exists(db_file):
                try:
                    data_store = get_data_store()
                    data = data_store.load_all_data()
                    players = data.get('players', [])
                    config_data = data.get('archiveConfig', {})
                except Exception:
                    pass

            if not players and os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                players = data.get('players', [])
                config_data = data.get('archiveConfig', {})

            # 选手资料类型配置（必填项）
            required_material_types = ['报名表', '个人照片', '参赛视频']
            all_material_types = config_data.get('players', {}).get('materialTypes', [])
            if not all_material_types:
                all_material_types = ['报名表', '个人照片', '参赛视频', '音频文件', '海报', '作品介绍', '媒体报道', '获奖证书']

            # 为每个选手计算缺失资料
            for player in players:
                player_name = player.get('name', '')
                player_folder = os.path.join(ARCHIVES_DIR, '02_选手档案', player_name)

                # 扫描选手文件夹，获取已有的资料类型
                existing_types = set()
                if os.path.exists(player_folder):
                    for subfolder in os.listdir(player_folder):
                        subfolder_path = os.path.join(player_folder, subfolder)
                        if os.path.isdir(subfolder_path):
                            for file_name in os.listdir(subfolder_path):
                                if os.path.isfile(os.path.join(subfolder_path, file_name)):
                                    # 从文件名解析资料类型
                                    parts = file_name.rsplit('.', 1)[0].split('_')
                                    if len(parts) >= 3:
                                        material_type = parts[2]
                                        existing_types.add(material_type)

                # 计算缺失的必填资料
                missing_required = [t for t in required_material_types if t not in existing_types]
                missing_all = [t for t in all_material_types if t not in existing_types]

                player['existingMaterials'] = list(existing_types)
                player['missingMaterials'] = len(missing_required) > 0
                player['missingCount'] = len(missing_required)
                player['missingTypes'] = missing_required

            # 搜索过滤
            if search:
                search_lower = search.lower()
                players = [p for p in players if
                    search_lower in p.get('name', '').lower() or
                    search_lower in p.get('stage', '').lower() or
                    search_lower in p.get('category', '').lower()]

            # 排序：缺失资料的选手排在最前面，按缺失数量降序
            players.sort(key=lambda p: (
                -p.get('missingCount', 0) if p.get('missingMaterials') else 0,
                p.get('name', '')
            ))

            # 分页
            total = len(players)
            start = (page - 1) * pageSize
            end = start + pageSize
            paginated_players = players[start:end]

            # 计算总缺失资料人数（所有选手，不是当前页）
            total_missing_count = sum(1 for p in players if p.get('missingMaterials'))

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'data': paginated_players,
                'total': total,
                'page': page,
                'pageSize': pageSize,
                'totalPages': (total + pageSize - 1) // pageSize,
                'totalMissingCount': total_missing_count
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def list_projects_paginated(self, page, pageSize, search=''):
        """分页查询项目列表"""
        try:
            db_file = os.path.join(DATA_DIR, 'workbench.db')
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            projects = []
            if os.path.exists(db_file):
                try:
                    data_store = get_data_store()
                    data = data_store.load_all_data()
                    projects = data.get('projects', [])
                except Exception:
                    pass

            if not projects and os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                projects = data.get('projects', [])

            # 搜索过滤
            if search:
                search_lower = search.lower()
                projects = [p for p in projects if
                    search_lower in p.get('name', '').lower() or
                    search_lower in p.get('status', '').lower() or
                    search_lower in p.get('category', '').lower()]

            # 分页
            total = len(projects)
            start = (page - 1) * pageSize
            end = start + pageSize
            paginated_projects = projects[start:end]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'data': paginated_projects,
                'total': total,
                'page': page,
                'pageSize': pageSize,
                'totalPages': (total + pageSize - 1) // pageSize
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def list_organizations_paginated(self, page, pageSize, search=''):
        """分页查询机构列表"""
        try:
            db_file = os.path.join(DATA_DIR, 'workbench.db')
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            organizations = []
            if os.path.exists(db_file):
                try:
                    data_store = get_data_store()
                    data = data_store.load_all_data()
                    organizations = data.get('organizations', [])
                except Exception:
                    pass

            if not organizations and os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                organizations = data.get('organizations', [])

            # 搜索过滤
            if search:
                search_lower = search.lower()
                organizations = [o for o in organizations if
                    search_lower in o.get('name', '').lower() or
                    search_lower in o.get('type', '').lower() or
                    search_lower in o.get('contact', '').lower()]

            # 分页
            total = len(organizations)
            start = (page - 1) * pageSize
            end = start + pageSize
            paginated_orgs = organizations[start:end]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'data': paginated_orgs,
                'total': total,
                'page': page,
                'pageSize': pageSize,
                'totalPages': (total + pageSize - 1) // pageSize
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def save_data(self):
        """保存数据"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            # ========== 数据校验（暂时跳过）==========
            # validation_errors = {}
            #
            # # 校验项目数据
            # if 'projects' in data:
            #     for idx, project in enumerate(data['projects']):
            #         valid, errors = Validator.validate_all(project, FormSchemas.PROJECT)
            #         if not valid:
            #             validation_errors[f'projects[{idx}]'] = errors
            #
            # # 校验机构数据
            # if 'organizations' in data:
            #     for idx, org in enumerate(data['organizations']):
            #         valid, errors = Validator.validate_all(org, FormSchemas.ORGANIZATION)
            #         if not valid:
            #             validation_errors[f'organizations[{idx}]'] = errors
            #
            # # 校验选手数据
            # if 'players' in data:
            #     for idx, player in enumerate(data['players']):
            #         valid, errors = Validator.validate_all(player, FormSchemas.PLAYER)
            #         if not valid:
            #             validation_errors[f'players[{idx}]'] = errors
            #
            # # 校验财务数据
            # if 'finances' in data:
            #     for idx, finance in enumerate(data['finances']):
            #         valid, errors = Validator.validate_all(finance, FormSchemas.FINANCE)
            #         if not valid:
            #             validation_errors[f'finances[{idx}]'] = errors
            #
            # # 校验用户数据
            # if 'users' in data:
            #     for idx, user in enumerate(data['users']):
            #         valid, errors = Validator.validate_all(user, FormSchemas.USER)
            #         if not valid:
            #             validation_errors[f'users[{idx}]'] = errors
            #
            # # 如果有校验错误，返回错误信息
            # if validation_errors:
            #     print(f"数据校验失败: {validation_errors}")
            #     self.send_response(400)
            #     self.send_header('Content-type', 'application/json')
            #     self.end_headers()
            #     self.wfile.write(json.dumps({
            #         'success': False,
            #         'message': '数据校验失败',
            #         'errors': validation_errors
            #     }, ensure_ascii=False).encode())
            #     return

            # ========== XSS 防护 ==========
            # 本地桌面应用无需 XSS 防护，直接保存原始数据
            # sanitize_input 会导致数据累积编码（每次保存都编码）
            sanitized_data = data

            # 确保目录存在
            os.makedirs(DATA_DIR, exist_ok=True)

            # 优先保存到 SQLite 数据库
            db_file = os.path.join(DATA_DIR, 'workbench.db')
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            saved_to_db = False
            saved_to_json = False

            # 尝试保存到数据库
            try:
                data_store = get_data_store()
                if data_store.save_all_data(sanitized_data):
                    saved_to_db = True
                    print("数据已保存到 SQLite 数据库")
            except Exception as e:
                print(f"保存到数据库失败: {e}")

            # 同时保存到 JSON 文件（作为备份）
            try:
                # 先备份现有数据
                if os.path.exists(json_file):
                    import shutil
                    from datetime import datetime
                    # 分钟粒度去重：同一分钟只保留一份快照，避免频繁保存产生海量备份
                    backup_name = datetime.now().strftime('%Y-%m-%d_%H-%M')
                    backup_path = os.path.join(BACKUP_DIR, backup_name)
                    backup_file = os.path.join(backup_path, 'workbench_data.json')
                    if not os.path.exists(backup_file):
                        os.makedirs(backup_path, exist_ok=True)
                        shutil.copy2(json_file, backup_file)

                # 保存清洗后的数据
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(sanitized_data, f, ensure_ascii=False, indent=2)
                saved_to_json = True
                print("数据已保存到 JSON 文件")
            except Exception as e:
                print(f"保存到 JSON 文件失败: {e}")

            if saved_to_db or saved_to_json:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': '数据保存成功',
                    'saved_to_db': saved_to_db,
                    'saved_to_json': saved_to_json
                }, ensure_ascii=False).encode())
            else:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据保存失败'
                }, ensure_ascii=False).encode())
        except Exception as e:
            print(f"save_data 异常: {e}")
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': str(e)
            }, ensure_ascii=False).encode())

    def get_data_version(self):
        """获取数据版本信息"""
        try:
            data_file = os.path.join(DATA_DIR, 'workbench_data.json')

            version = 0
            last_modified = 0

            if os.path.exists(data_file):
                stat = os.stat(data_file)
                last_modified = int(stat.st_mtime * 1000)

                # 从文件读取版本号（如果存在）
                try:
                    with open(data_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        version = data.get('_version_timestamp', last_modified)
                except:
                    version = last_modified

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'version': version,
                'lastModified': last_modified
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def save_incremental_data(self):
        """增量保存数据"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data.decode('utf-8'))

            client_version = request_data.get('version', 0)
            changes = request_data.get('changes', [])
            full_data = request_data.get('fullData')  # 用于降级

            # 确保目录存在
            os.makedirs(DATA_DIR, exist_ok=True)
            data_file = os.path.join(DATA_DIR, 'workbench_data.json')

            # 读取现有数据
            current_data = {}
            server_version = 0

            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
                    server_version = current_data.get('_version_timestamp', 0)

            # 确保所有数组字段存在且类型正确
            for key in ['projects', 'organizations', 'players', 'finances', 'users', 'auditLogs']:
                if key not in current_data:
                    current_data[key] = []
                elif not isinstance(current_data[key], list):
                    print(f"修复数据类型: {key} 从 {type(current_data[key]).__name__} 转为 list")
                    current_data[key] = []

            # 版本冲突检测
            if server_version > 0 and client_version > 0 and client_version < server_version:
                # 客户端版本过旧，返回冲突
                self.send_response(409)  # Conflict
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'conflict': True,
                    'message': '数据版本冲突，请刷新后重试',
                    'serverVersion': server_version
                }, ensure_ascii=False).encode())
                return

            # 应用增量变更
            if changes and len(changes) > 0:
                for change in changes:
                    path = change.get('path', '')
                    value = change.get('value')
                    change_type = change.get('type', 'set')

                    if change_type == 'delete':
                        self._delete_by_path(current_data, path)
                    else:
                        self._set_by_path(current_data, path, value)

                print(f"增量保存: 应用了 {len(changes)} 个变更")
            else:
                # 没有变更，使用完整数据降级
                if full_data:
                    current_data = full_data
                    print("增量保存: 使用完整数据降级")

            # ========== 数据校验（增量保存暂时跳过）==========
            # 注意：增量数据来自前端代理，校验可能导致误报
            # 如需启用校验，请取消下面的注释
            """
            validation_errors = {}
            if 'projects' in current_data:
                for idx, project in enumerate(current_data['projects']):
                    if not isinstance(project, dict):
                        continue
                    valid, errors = Validator.validate_all(project, FormSchemas.PROJECT)
                    if not valid:
                        validation_errors[f'projects[{idx}]'] = errors
            if 'organizations' in current_data:
                for idx, org in enumerate(current_data['organizations']):
                    if not isinstance(org, dict):
                        continue
                    valid, errors = Validator.validate_all(org, FormSchemas.ORGANIZATION)
                    if not valid:
                        validation_errors[f'organizations[{idx}]'] = errors
            if 'players' in current_data:
                for idx, player in enumerate(current_data['players']):
                    if not isinstance(player, dict):
                        continue
                    valid, errors = Validator.validate_all(player, FormSchemas.PLAYER)
                    if not valid:
                        validation_errors[f'players[{idx}]'] = errors
            if 'finances' in current_data:
                for idx, finance in enumerate(current_data['finances']):
                    if not isinstance(finance, dict):
                        continue
                    valid, errors = Validator.validate_all(finance, FormSchemas.FINANCE)
                    if not valid:
                        validation_errors[f'finances[{idx}]'] = errors
            if validation_errors:
                print(f"增量保存校验失败: {validation_errors}")
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据校验失败',
                    'errors': validation_errors
                }, ensure_ascii=False).encode())
                return
            """

            # ========== XSS 防护 ==========
            # 本地桌面应用无需 XSS 防护，直接保存原始数据
            sanitized_data = current_data

            # 更新版本号
            new_version = int(time.time() * 1000)
            sanitized_data['_version_timestamp'] = new_version

            # 原子写入：先写入临时文件，再重命名
            dir_name = os.path.dirname(data_file)
            fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(sanitized_data, f, ensure_ascii=False, indent=2)
                # 原子替换
                os.replace(temp_path, data_file)
            except Exception:
                # 清理临时文件
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                raise

            # 同步到 SQLite
            try:
                from server.database.db import get_data_store
                data_store = get_data_store()
                data_store.save_all_data(sanitized_data)
                print(f"增量保存成功并同步到 SQLite: 版本 {new_version}")
            except Exception as sync_err:
                print(f"增量保存 JSON 成功，但同步到 SQLite 失败: {sync_err}")
                import traceback
                traceback.print_exc()

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '增量保存成功',
                'version': new_version,
                'changesApplied': len(changes)
            }, ensure_ascii=False).encode())
        except Exception as e:
            print(f"增量保存失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def _set_by_path(self, obj, path, value):
        """根据路径设置值"""
        if not path or not obj:
            return

        keys = path.split('.')
        current = obj

        for i in range(len(keys) - 1):
            key = keys[i]

            # 处理数组索引
            if isinstance(current, list):
                if key.isdigit():
                    idx = int(key)
                    # 安全上限防止死循环
                    if idx > 10000:
                        print(f"_set_by_path 警告: 索引 {idx} 超过安全上限")
                        return
                    while len(current) <= idx:
                        current.append(None)
                    if current[idx] is None:
                        current[idx] = {}
                    elif not isinstance(current[idx], dict):
                        current[idx] = {}
                    current = current[idx]
                else:
                    # 字符串键在数组上，转换为对象
                    current = self._convert_to_object(current)
                    if key not in current:
                        current[key] = {}
                    elif not isinstance(current[key], dict):
                        current[key] = {}
                    current = current[key]
            elif isinstance(current, dict):
                if key not in current:
                    current[key] = {}
                elif not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
            else:
                # 无法继续导航，终止
                return

        # 处理最后的键
        final_key = keys[-1]
        if isinstance(current, list):
            if final_key.isdigit():
                idx = int(final_key)
                if idx > 10000:
                    print(f"_set_by_path 警告: 最终索引 {idx} 超过安全上限")
                    return
                while len(current) <= idx:
                    current.append(None)
                current[idx] = value
            else:
                current = self._convert_to_object(current)
                current[final_key] = value
        elif isinstance(current, dict):
            current[final_key] = value

    def _convert_to_object(self, arr):
        """将数组转换为对象"""
        result = {}
        for i, item in enumerate(arr):
            result[str(i)] = item
        return result

    def _delete_by_path(self, obj, path):
        """根据路径删除值"""
        if not path or not obj:
            return

        keys = path.split('.')
        current = obj

        for i in range(len(keys) - 1):
            key = keys[i]

            # 处理数组索引
            if isinstance(current, list) and key.isdigit():
                idx = int(key)
                if idx < 0 or idx >= len(current):
                    return
                current = current[idx]
            else:
                if key not in current:
                    return
                current = current[key]

        final_key = keys[-1]
        if isinstance(current, list) and final_key.isdigit():
            idx = int(final_key)
            if idx >= 0 and idx < len(current):
                del current[idx]
        elif final_key in current:
            del current[final_key]

    def _get_by_path(self, obj, path):
        """根据路径获取值"""
        if not path or not obj:
            return None

        keys = path.split('.')
        current = obj

        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]

        return current

    # 自动备份保留上限（供显式清理调用，默认不自动执行）
    MAX_BACKUPS = 50

    def _prune_backups(self, keep=None):
        """
        保留最近 N 个备份，删除多余的（目录名即时间戳，可直接按名称排序）。

        注意：默认不在保存流程中自动调用——删除备份属于破坏性操作，
        需要显式触发（例如通过维护接口或人工执行），避免误删历史快照。
        """
        keep = keep or self.MAX_BACKUPS
        try:
            if not os.path.exists(BACKUP_DIR):
                return 0
            entries = sorted(
                [d for d in os.listdir(BACKUP_DIR) if os.path.isdir(os.path.join(BACKUP_DIR, d))],
                reverse=True
            )
            removed = 0
            for name in entries[keep:]:
                try:
                    shutil.rmtree(os.path.join(BACKUP_DIR, name))
                    removed += 1
                except OSError:
                    pass
            if removed:
                print(f"[Backup] 已清理 {removed} 个历史备份，保留最近 {keep} 个")
            return removed
        except Exception as e:
            print(f"清理历史备份失败: {e}")
            return 0

    def create_backup(self):
        """创建备份"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            from datetime import datetime
            import shutil

            backup_name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_path = os.path.join(BACKUP_DIR, backup_name)
            os.makedirs(backup_path, exist_ok=True)

            # 保存备份数据
            with open(os.path.join(backup_path, 'workbench_data.json'), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '备份创建成功',
                'backup_name': backup_name
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def list_backups(self):
        """列出所有备份"""
        try:
            backups = []
            if os.path.exists(BACKUP_DIR):
                for item in os.listdir(BACKUP_DIR):
                    item_path = os.path.join(BACKUP_DIR, item)
                    if os.path.isdir(item_path):
                        backup_file = os.path.join(item_path, 'workbench_data.json')
                        backups.append({
                            'name': item,
                            'date': item.split('_')[0] if '_' in item else item,
                            'time': item.split('_')[1].replace('-', ':') if '_' in item else '',
                            'has_data': os.path.exists(backup_file)
                        })

            # 按时间倒序排列
            backups.sort(key=lambda x: x['name'], reverse=True)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'backups': backups
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def restore_backup(self, backup_name):
        """恢复备份"""
        try:
            if not backup_name:
                self.send_error(400, 'No backup name provided')
                return

            backup_file = os.path.join(BACKUP_DIR, backup_name, 'workbench_data.json')

            if not os.path.exists(backup_file):
                self.send_error(404, f'Backup not found: {backup_name}')
                return

            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '备份恢复成功',
                'data': data
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def get_system_status(self):
        """获取系统状态"""
        try:
            import platform

            uptime = time.time() - SERVER_START_TIME
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)

            # 获取数据文件信息
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')
            data_size = os.path.getsize(json_file) if os.path.exists(json_file) else 0

            # 获取数据量统计
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            stats = {
                'uptime': f'{hours}h {minutes}m {seconds}s',
                'uptime_seconds': int(uptime),
                'data_size': data_size,
                'records': {
                    'projects': len(data.get('projects', [])),
                    'organizations': len(data.get('organizations', [])),
                    'players': len(data.get('players', [])),
                    'finances': len(data.get('finances', [])),
                    'users': len(data.get('users', [])),
                    'auditLogs': len(data.get('auditLogs', []))
                },
                'system': {
                    'python_version': platform.python_version(),
                    'platform': platform.system() + ' ' + platform.release(),
                    'data_dir': DATA_DIR,
                    'archive_dir': ARCHIVES_DIR,
                    'resources_dir': RESOURCES_DIR
                }
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(stats, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    _icon_cache = {}

    def get_file_icon(self):
        """获取文件/文件夹图标，返回 PNG 图片"""
        try:
            from server.archive.icon_extractor import get_file_icon, get_folder_icon

            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            icon_type = params.get('type', [None])[0]
            ext = params.get('ext', [None])[0]

            cache_key = f"{icon_type or ''}_{ext or ''}"
            if cache_key in self._icon_cache:
                png_data = self._icon_cache[cache_key]
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                self.wfile.write(png_data)
                return

            if icon_type == 'folder':
                png_data = get_folder_icon(48)
            elif ext and ext != 'default':
                png_data = get_file_icon(ext, 48)
            else:
                png_data = get_file_icon('', 48)

            if not png_data:
                png_data = self._generate_default_icon(icon_type == 'folder')

            self._icon_cache[cache_key] = png_data
            self.send_response(200)
            self.send_header('Content-type', 'image/png')
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(png_data)
        except Exception as e:
            print(f"获取图标失败: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _generate_default_icon(self, is_folder=False):
        """生成默认文件/文件夹图标 PNG"""
        try:
            from PIL import Image, ImageDraw
            import io
            size = 48
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            if is_folder:
                draw.rectangle([6, 12, 39, 36], fill=(255, 213, 79, 255), outline=(218, 165, 32, 255), width=2)
                draw.rectangle([6, 12, 15, 15], fill=(218, 165, 32, 255))
            else:
                draw.rectangle([9, 6, 39, 39], fill=(220, 230, 245, 255), outline=(100, 149, 237, 255), width=2)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue()
        except Exception as e:
            print(f"生成默认图标失败: {e}")
            return None

    def browse_directories(self):
        """浏览本地目录，返回指定路径下的子目录列表"""
        try:
            import platform
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            current_path = params.get('path', [None])[0]

            if current_path:
                current_path = unquote(current_path)

            if not current_path:
                if platform.system() == 'Windows':
                    drives = []
                    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        drive = f'{letter}:\\'
                        if os.path.exists(drive):
                            drives.append(drive)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': True,
                        'currentPath': '',
                        'parentPath': None,
                        'directories': drives
                    }, ensure_ascii=False).encode())
                    return
                else:
                    current_path = '/'

            if not os.path.isdir(current_path):
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '路径不是有效目录'
                }, ensure_ascii=False).encode())
                return

            parent = os.path.dirname(current_path.rstrip(os.sep)) or None
            if platform.system() == 'Windows':
                drive_root = os.path.splitdrive(current_path)[0] + '\\'
                if current_path.rstrip(os.sep) == drive_root.rstrip('\\'):
                    parent = None

            directories = []
            try:
                for item in sorted(os.listdir(current_path)):
                    item_path = os.path.join(current_path, item)
                    if os.path.isdir(item_path):
                        try:
                            os.listdir(item_path)
                            directories.append(item)
                        except PermissionError:
                            pass
            except PermissionError:
                self.send_response(403)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '无权限访问此目录'
                }, ensure_ascii=False).encode())
                return

            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'currentPath': current_path,
                'parentPath': parent,
                'directories': directories
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def scan_temp_files(self):
        """扫描临时文件"""
        try:
            total_size = 0
            file_count = 0
            old_files = []

            if os.path.exists(ASSETS_DIR):
                for root, dirs, files in os.walk(ASSETS_DIR):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stat = os.stat(file_path)
                            total_size += stat.st_size
                            file_count += 1

                            file_mtime = stat.st_mtime
                            file_age_days = (time.time() - file_mtime) / 86400

                            if file_age_days > 30:
                                old_files.append({
                                    'path': os.path.relpath(file_path, ASSETS_DIR),
                                    'size': stat.st_size,
                                    'age_days': int(file_age_days),
                                    'modified': time.strftime('%Y-%m-%d', time.localtime(file_mtime))
                                })
                        except Exception as e:
                            print(f"无法访问文件 {file_path}: {e}")

            old_files.sort(key=lambda x: x['age_days'], reverse=True)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'total_size': total_size,
                'file_count': file_count,
                'old_files': old_files[:50]
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            days = data.get('days', 30)

            deleted_count = 0
            deleted_size = 0
            errors = []

            cutoff_time = time.time() - (days * 86400)

            if os.path.exists(ASSETS_DIR):
                for root, dirs, files in os.walk(ASSETS_DIR):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stat = os.stat(file_path)
                            if stat.st_mtime < cutoff_time:
                                file_size = stat.st_size
                                os.remove(file_path)
                                deleted_count += 1
                                deleted_size += file_size
                                print(f"已删除: {file_path}")
                        except Exception as e:
                            errors.append(f"{file}: {str(e)}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'deleted_count': deleted_count,
                'deleted_size': deleted_size,
                'errors': errors[:10]
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    # ========== 通知 API 实现 ==========

    def handle_notifications(self):
        """处理通知相关请求"""
        parsed = urlparse(self.path)

        if self.command == 'GET':
            if parsed.path == '/api/notifications':
                self.get_notifications()
            elif parsed.path == '/api/notifications/unread-count':
                self.get_unread_count()
            else:
                self.send_error(404, 'Not found')

        elif self.command == 'POST':
            if parsed.path == '/api/notifications/read':
                self.mark_as_read()
            elif parsed.path == '/api/notifications/read-all':
                self.mark_all_read()
            elif parsed.path == '/api/notifications/create':
                self.create_notification()
            else:
                self.send_error(404, 'Not found')

        elif self.command == 'DELETE':
            if parsed.path.startswith('/api/notifications/'):
                self.delete_notification()
            else:
                self.send_error(404, 'Not found')
        else:
            self.send_error(405, 'Method not allowed')

    def get_notifications(self):
        """获取通知列表"""
        try:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            page = int(params.get('page', [1])[0])
            page_size = int(params.get('pageSize', [20])[0])
            notification_type = params.get('type', ['all'])[0]
            is_read = params.get('isRead', ['all'])[0]

            notifications_file = os.path.join(DATA_DIR, 'notifications.json')
            notifications = []

            if os.path.exists(notifications_file):
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)

            filtered = notifications

            if notification_type != 'all':
                filtered = [n for n in filtered if n.get('type') == notification_type]

            if is_read != 'all':
                is_read_bool = is_read == 'true'
                filtered = [n for n in filtered if n.get('isRead') == is_read_bool]

            filtered.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

            total = len(filtered)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = filtered[start:end]

            unread_count = len([n for n in notifications if not n.get('isRead')])

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'data': paginated,
                'total': total,
                'unreadCount': unread_count,
                'page': page,
                'pageSize': page_size
            }, ensure_ascii=False).encode())
        except Exception as e:
            print(f"获取通知失败: {e}")
            self.send_error(500, str(e))

    def get_unread_count(self):
        """获取未读通知数量"""
        try:
            notifications_file = os.path.join(DATA_DIR, 'notifications.json')
            notifications = []

            if os.path.exists(notifications_file):
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)

            unread_count = len([n for n in notifications if not n.get('isRead')])

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'count': unread_count
            }).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def mark_as_read(self):
        """标记单个通知为已读"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            notification_id = data.get('id')

            if not notification_id:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '缺少通知ID'}).encode())
                return

            notifications_file = os.path.join(DATA_DIR, 'notifications.json')
            notifications = []

            if os.path.exists(notifications_file):
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)

            for notification in notifications:
                if notification.get('id') == notification_id:
                    notification['isRead'] = True
                    notification['readAt'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time()))
                    break

            with open(notifications_file, 'w', encoding='utf-8') as f:
                json.dump(notifications, f, ensure_ascii=False, indent=2)

            unread_count = len([n for n in notifications if not n.get('isRead')])

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'unreadCount': unread_count
            }).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def mark_all_read(self):
        """标记所有通知为已读"""
        try:
            notifications_file = os.path.join(DATA_DIR, 'notifications.json')
            notifications = []

            if os.path.exists(notifications_file):
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)

            now = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time()))
            for notification in notifications:
                if not notification.get('isRead'):
                    notification['isRead'] = True
                    notification['readAt'] = now

            with open(notifications_file, 'w', encoding='utf-8') as f:
                json.dump(notifications, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '已全部标记为已读',
                'count': len(notifications)
            }).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def create_notification(self):
        """创建新通知（系统内部使用）"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            import uuid
            notification = {
                'id': str(uuid.uuid4()),
                'title': data.get('title', ''),
                'content': data.get('content', ''),
                'type': data.get('type', 'info'),
                'isRead': False,
                'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time())),
                'link': data.get('link', None),
                'metadata': data.get('metadata', {})
            }

            notifications_file = os.path.join(DATA_DIR, 'notifications.json')
            notifications = []

            if os.path.exists(notifications_file):
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)

            notifications.insert(0, notification)

            with open(notifications_file, 'w', encoding='utf-8') as f:
                json.dump(notifications, f, ensure_ascii=False, indent=2)

            self.send_response(201)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'data': notification
            }).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def delete_notification(self):
        """删除通知"""
        try:
            notification_id = self.path.split('/')[-1]

            notifications_file = os.path.join(DATA_DIR, 'notifications.json')
            notifications = []

            if os.path.exists(notifications_file):
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)

            original_len = len(notifications)
            notifications = [n for n in notifications if n.get('id') != notification_id]

            if len(notifications) == original_len:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'message': '通知不存在'}).encode())
                return

            with open(notifications_file, 'w', encoding='utf-8') as f:
                json.dump(notifications, f, ensure_ascii=False, indent=2)

            unread_count = len([n for n in notifications if not n.get('isRead')])

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'unreadCount': unread_count
            }).encode())
        except Exception as e:
            self.send_error(500, str(e))

    @staticmethod
    def create_system_notification(title, content, type='info', link=None):
        """创建系统通知的便捷方法"""
        try:
            import uuid
            notification = {
                'id': str(uuid.uuid4()),
                'title': title,
                'content': content,
                'type': type,
                'isRead': False,
                'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time())),
                'link': link
            }

            notifications_file = os.path.join(DATA_DIR, 'notifications.json')
            notifications = []

            if os.path.exists(notifications_file):
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)

            notifications.insert(0, notification)

            with open(notifications_file, 'w', encoding='utf-8') as f:
                json.dump(notifications, f, ensure_ascii=False, indent=2)

            print(f"[通知] 已创建系统通知: {title}")
            return notification
        except Exception as e:
            print(f"创建系统通知失败: {e}")
            return None

    # ========== 认证 API 实现 ==========

    def auth_register(self):
        """用户注册（使用 bcrypt 加密密码）"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            # ========== XSS 防护 ==========
            # 清洗用户输入
            data = sanitize_form(data, {
                'username': {'trim': True, 'escape_html': True, 'filter_dangerous': True},
                'password': {'trim': False, 'escape_html': False, 'filter_dangerous': False},
                'role': {'trim': True, 'escape_html': True, 'filter_dangerous': True}
            })

            username = data.get('username', '').strip()
            password = data.get('password', '')
            role = data.get('role', 'viewer')

            # ========== 数据校验 ==========
            valid, errors = Validator.validate_all({
                'username': username,
                'password': password,
                'role': role
            }, FormSchemas.USER)

            if not valid:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据校验失败',
                    'errors': errors
                }, ensure_ascii=False).encode())
                return

            # 解码客户端传输的密码
            password = decode_client_password(password)

            # 加载现有数据
            data_file = os.path.join(DATA_DIR, 'workbench_data.json')
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    store_data = json.load(f)
            else:
                # 创建完整的数据结构（所有数组）
                store_data = {
                    'projects': [],
                    'organizations': [],
                    'players': [],
                    'finances': [],
                    'users': [],
                    'auditLogs': [],
                    'checklistState': {},
                    '_version_timestamp': int(time.time() * 1000)
                }

            # 确保所有数组字段存在
            for key in ['projects', 'organizations', 'players', 'finances', 'users', 'auditLogs']:
                if key not in store_data:
                    store_data[key] = []
                elif not isinstance(store_data[key], list):
                    store_data[key] = []

            # 检查用户名是否已存在
            if any(u.get('username') == username for u in store_data['users']):
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '用户名已存在'
                }, ensure_ascii=False).encode())
                return

            # 加密密码
            hashed_password = hash_password(password)
            if not hashed_password:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '密码加密失败'
                }, ensure_ascii=False).encode())
                return

            # 创建用户
            user = {
                'id': 'u' + str(int(time.time() * 1000)),
                'username': username,
                'password': hashed_password,
                'passwordHashed': True,  # 标记密码已加密
                'role': role,
                'createdAt': time.strftime('%Y-%m-%d %H:%M:%S')
            }

            store_data['users'].append(user)

            # 保存数据（走统一写入，保证同时落 SQLite，避免重启后账号从库里读不出来）
            self._write_json_data(store_data)

            print(f"用户注册成功: {username}")

            # 返回成功响应（不包含密码）
            user_response = {k: v for k, v in user.items() if k != 'password'}
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '注册成功',
                'user': user_response
            }, ensure_ascii=False).encode())

        except Exception as e:
            print(f"用户注册失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def auth_login(self):
        """用户登录（使用 bcrypt 验证密码）"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            # ========== XSS 防护 ==========
            # 清洗用户输入
            data = sanitize_form(data, {
                'username': {'trim': True, 'escape_html': True, 'filter_dangerous': True},
                'password': {'trim': False, 'escape_html': False, 'filter_dangerous': False}
            })

            username = data.get('username', '').strip()
            password = data.get('password', '')

            client_ip = self.client_address[0] if self.client_address else '127.0.0.1'

            if login_rate_limiter.is_rate_limited(client_ip):
                self.send_response(429)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '登录尝试过于频繁，请5分钟后再试',
                    'error': 'RATE_LIMITED'
                }, ensure_ascii=False).encode())
                return

            # ========== 数据校验 ==========
            # 校验用户名
            username_result = Validator.validate_required(username, '用户名')
            if not username_result['valid']:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': username_result['message']
                }, ensure_ascii=False).encode())
                return

            # 校验密码
            password_result = Validator.validate_required(password, '密码')
            if not password_result['valid']:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': password_result['message']
                }, ensure_ascii=False).encode())
                return

            # 解码客户端传输的密码
            password = decode_client_password(password)

            # 加载数据
            data_file = os.path.join(DATA_DIR, 'workbench_data.json')
            if not os.path.exists(data_file):
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '用户名或密码错误'
                }, ensure_ascii=False).encode())
                return

            with open(data_file, 'r', encoding='utf-8') as f:
                store_data = json.load(f)

            users = store_data.get('users', [])
            user = next((u for u in users if u.get('username') == username), None)

            if not user:
                login_rate_limiter.record_attempt(client_ip)
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '用户名或密码错误'
                }, ensure_ascii=False).encode())
                return

            # 检查密码是否已加密
            stored_password = user.get('password', '')
            password_hashed = user.get('passwordHashed', False)

            if password_hashed:
                # 使用 bcrypt 验证
                if not verify_password(password, stored_password):
                    login_rate_limiter.record_attempt(client_ip)
                    self.send_response(401)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'message': '用户名或密码错误'
                    }, ensure_ascii=False).encode())
                    return
            else:
                # 旧密码（明文），直接比较
                if stored_password != password:
                    login_rate_limiter.record_attempt(client_ip)
                    self.send_response(401)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'message': '用户名或密码错误'
                    }, ensure_ascii=False).encode())
                    return

                # 自动迁移密码：将明文密码加密
                hashed_password = hash_password(password)
                if hashed_password:
                    user['password'] = hashed_password
                    user['passwordHashed'] = True
                    # 保存更新后的数据（走统一写入，避免明文->bcrypt 的迁移结果重启后回退）
                    self._write_json_data(store_data)
                    print(f"用户密码已自动迁移: {username}")

            # 生成 JWT Token
            login_rate_limiter.reset(client_ip)
            token_data = create_token_response(
                user_id=user['id'],
                username=user['username'],
                role=user.get('role', 'viewer')
            )

            # 更新当前用户
            store_data['currentUser'] = {k: v for k, v in user.items() if k != 'password'}

            # 保存数据（走统一写入，保证登录态与用户数据同步落 SQLite）
            self._write_json_data(store_data)

            print(f"用户登录成功: {username}")

            # 返回成功响应（包含 Token）
            user_response = {k: v for k, v in user.items() if k != 'password'}
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '登录成功',
                'user': user_response,
                **token_data  # 包含 access_token, refresh_token 等
            }, ensure_ascii=False).encode())

        except Exception as e:
            print(f"用户登录失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def auth_migrate_password(self):
        """密码迁移接口（用于批量迁移旧用户密码）"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            user_id = data.get('userId', '')
            new_password = data.get('newPassword', '')

            if not user_id or not new_password:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '用户ID和新密码不能为空'
                }, ensure_ascii=False).encode())
                return

            # 解码客户端传输的密码
            new_password = decode_client_password(new_password)

            # 加载数据
            data_file = os.path.join(DATA_DIR, 'workbench_data.json')
            if not os.path.exists(data_file):
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据文件不存在'
                }, ensure_ascii=False).encode())
                return

            with open(data_file, 'r', encoding='utf-8') as f:
                store_data = json.load(f)

            # 查找用户
            user_index = next((i for i, u in enumerate(store_data.get('users', [])) if u.get('id') == user_id), -1)

            if user_index == -1:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '用户不存在'
                }, ensure_ascii=False).encode())
                return

            # 加密新密码
            hashed_password = hash_password(new_password)
            if not hashed_password:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '密码加密失败'
                }, ensure_ascii=False).encode())
                return

            # 更新密码
            store_data['users'][user_index]['password'] = hashed_password
            store_data['users'][user_index]['passwordHashed'] = True
            store_data['users'][user_index]['passwordMigratedAt'] = time.strftime('%Y-%m-%d %H:%M:%S')
            store_data['users'][user_index].pop('mustChangePassword', None)

            # 保存数据（走统一写入，保证改密结果同步落 SQLite）
            self._write_json_data(store_data)

            print(f"用户密码迁移成功: {store_data['users'][user_index].get('username')}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '密码迁移成功'
            }, ensure_ascii=False).encode())

        except Exception as e:
            print(f"密码迁移失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def auth_check_password(self):
        """检查用户密码是否已加密"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            user_id = data.get('userId', '')

            if not user_id:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '用户ID不能为空'
                }, ensure_ascii=False).encode())
                return

            # 加载数据
            data_file = os.path.join(DATA_DIR, 'workbench_data.json')
            if not os.path.exists(data_file):
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据文件不存在'
                }, ensure_ascii=False).encode())
                return

            with open(data_file, 'r', encoding='utf-8') as f:
                store_data = json.load(f)

            # 查找用户
            user = next((u for u in store_data.get('users', []) if u.get('id') == user_id), None)

            if not user:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '用户不存在'
                }, ensure_ascii=False).encode())
                return

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'passwordHashed': user.get('passwordHashed', False)
            }, ensure_ascii=False).encode())

        except Exception as e:
            print(f"检查密码状态失败: {e}")
            self.send_error(500, str(e))

    def auth_verify_token(self):
        """验证 JWT Token"""
        try:
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

            # Token 有效，返回用户信息
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': 'Token 有效',
                'user': {
                    'user_id': payload.get('user_id'),
                    'username': payload.get('username'),
                    'role': payload.get('role')
                },
                'expires_at': payload.get('exp')
            }, ensure_ascii=False).encode())

        except Exception as e:
            print(f"Token 验证失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def auth_refresh_token(self):
        """刷新 JWT Token"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            refresh_token = data.get('refresh_token', '')

            if not refresh_token:
                self.send_response(400)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '缺少刷新 Token'
                }, ensure_ascii=False).encode())
                return

            # 验证刷新 Token
            payload = jwt_handler.verify_token(refresh_token)

            if not payload:
                self.send_response(401)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '刷新 Token 无效或已过期',
                    'error': 'INVALID_REFRESH_TOKEN'
                }, ensure_ascii=False).encode())
                return

            if payload.get('type') != 'refresh':
                self.send_response(401)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '不是有效的刷新 Token',
                    'error': 'INVALID_TOKEN_TYPE'
                }, ensure_ascii=False).encode())
                return

            # 验证用户是否仍然存在且有效
            data_file = os.path.join(DATA_DIR, 'workbench_data.json')
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    store_data = json.load(f)

                users = store_data.get('users', [])
                user = next((u for u in users if u.get('id') == payload.get('user_id')), None)

                if not user:
                    self.send_response(401)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'message': '用户不存在',
                        'error': 'USER_NOT_FOUND'
                    }, ensure_ascii=False).encode())
                    return

                # 生成新的 Token
                token_data = create_token_response(
                    user_id=user['id'],
                    username=user['username'],
                    role=user.get('role', 'viewer')
                )

                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': 'Token 刷新成功',
                    **token_data
                }, ensure_ascii=False).encode())
            else:
                self.send_response(401)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据文件不存在',
                    'error': 'DATA_NOT_FOUND'
                }, ensure_ascii=False).encode())

        except Exception as e:
            print(f"Token 刷新失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def end_headers(self):
        """添加 CORS 头"""
        try:
            self.send_header('Access-Control-Allow-Origin', '*')
            super().end_headers()
        except ConnectionAbortedError:
            pass
        except BrokenPipeError:
            pass

    # ========== 数据同步 API 实现 ==========

    def get_sync_status(self):
        """获取数据同步状态"""
        try:
            db_file = os.path.join(DATA_DIR, 'workbench.db')
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            status = {
                'db_exists': os.path.exists(db_file),
                'json_exists': os.path.exists(json_file),
                'db_records': 0,
                'json_records': 0,
                'needs_migration': False,
                'recommendation': ''
            }

            # 统计数据库记录数
            if status['db_exists']:
                try:
                    data_store = get_data_store()
                    db_data = data_store.load_all_data()
                    status['db_records'] = (
                        len(db_data.get('projects', [])) +
                        len(db_data.get('organizations', [])) +
                        len(db_data.get('players', [])) +
                        len(db_data.get('finances', [])) +
                        len(db_data.get('users', []))
                    )
                except:
                    pass

            # 统计 JSON 记录数
            if status['json_exists']:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    status['json_records'] = (
                        len(json_data.get('projects', [])) +
                        len(json_data.get('organizations', [])) +
                        len(json_data.get('players', [])) +
                        len(json_data.get('finances', [])) +
                        len(json_data.get('users', []))
                    )
                except:
                    pass

            # 判断是否需要迁移
            if status['json_exists'] and not status['db_exists']:
                status['needs_migration'] = True
                status['recommendation'] = '建议执行 JSON 到 SQLite 迁移'
            elif status['json_exists'] and status['db_exists']:
                if status['json_records'] > status['db_records']:
                    status['needs_migration'] = True
                    status['recommendation'] = 'JSON 数据较新，建议重新迁移'
                else:
                    status['recommendation'] = '数据库已存在，无需迁移'
            elif not status['json_exists'] and status['db_exists']:
                status['recommendation'] = '仅数据库存在，可导出到 JSON'
            else:
                status['recommendation'] = '没有找到数据文件'

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'status': status
            }, ensure_ascii=False).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def import_from_json_api(self):
        """从 JSON 导入到 SQLite（需要 admin 权限）"""
        try:
            # 检查权限
            is_valid, _, error = self._check_auth_and_permission('manage_config')
            if not is_valid:
                self._send_permission_error(error)
                return

            json_file = os.path.join(DATA_DIR, 'workbench_data.json')

            if not os.path.exists(json_file):
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': 'JSON 数据文件不存在'
                }, ensure_ascii=False).encode())
                return

            # 加载 JSON 数据
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # 保存到数据库
            data_store = get_data_store()
            if data_store.save_all_data(json_data):
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': '数据导入成功',
                    'records': {
                        'projects': len(json_data.get('projects', [])),
                        'organizations': len(json_data.get('organizations', [])),
                        'players': len(json_data.get('players', [])),
                        'finances': len(json_data.get('finances', [])),
                        'users': len(json_data.get('users', []))
                    }
                }, ensure_ascii=False).encode())
            else:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据导入失败'
                }, ensure_ascii=False).encode())
        except Exception as e:
            print(f"导入数据失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def export_to_json_api(self):
        """从 SQLite 导出到 JSON（需要 admin 权限）"""
        try:
            # 检查权限
            is_valid, _, error = self._check_auth_and_permission('manage_config')
            if not is_valid:
                self._send_permission_error(error)
                return

            db_file = os.path.join(DATA_DIR, 'workbench.db')

            if not os.path.exists(db_file):
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '数据库文件不存在'
                }, ensure_ascii=False).encode())
                return

            # 从数据库加载数据
            data_store = get_data_store()
            data = data_store.load_all_data()

            # 保存到 JSON 文件
            json_file = os.path.join(DATA_DIR, 'workbench_data.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '数据导出成功',
                'records': {
                    'projects': len(data.get('projects', [])),
                    'organizations': len(data.get('organizations', [])),
                    'players': len(data.get('players', [])),
                    'finances': len(data.get('finances', [])),
                    'users': len(data.get('users', []))
                }
            }, ensure_ascii=False).encode())
        except Exception as e:
            print(f"导出数据失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def handle_export_data(self):
        """处理数据导出请求，支持 JSON 和 CSV 格式

        请求体:
            {
                "dataType": "projects"|"players"|"organizations"|"finance"|"knowledge",
                "format": "csv"|"json",
                "fields": ["name", "type", ...]  // 可选，指定导出字段
            }
        """
        import csv
        from io import StringIO

        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_response(400)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '请求体为空'
                }, ensure_ascii=False).encode())
                return

            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))

            data_type = body.get('dataType', '')
            export_format = body.get('format', 'json')
            fields = body.get('fields', [])

            # 数据类型映射：前端 key -> 数据文件中的 key
            type_mapping = {
                'projects': 'projects',
                'players': 'players',
                'organizations': 'organizations',
                'finance': 'finances',
                'knowledge': 'knowledge'
            }

            data_key = type_mapping.get(data_type)
            if not data_key:
                self.send_response(400)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': f'不支持的数据类型: {data_type}，支持的类型: {", ".join(type_mapping.keys())}'
                }, ensure_ascii=False).encode())
                return

            # 从数据文件读取数据
            data = self._read_json_data()
            records = data.get(data_key, [])

            if not isinstance(records, list):
                records = []

            # 按 fields 过滤字段
            if fields and isinstance(fields, list) and len(fields) > 0:
                filtered_records = []
                for record in records:
                    if isinstance(record, dict):
                        filtered_record = {}
                        for field in fields:
                            if field in record:
                                value = record[field]
                                # 将列表和字典转为 JSON 字符串以便 CSV 导出
                                if isinstance(value, (list, dict)):
                                    value = json.dumps(value, ensure_ascii=False)
                                filtered_record[field] = value
                        filtered_records.append(filtered_record)
                    else:
                        filtered_records.append(record)
                records = filtered_records

            # JSON 格式导出
            if export_format == 'json':
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(records, ensure_ascii=False, indent=2).encode())
                return

            # CSV 格式导出
            if export_format == 'csv':
                if not records:
                    # 空数据，返回只有表头的 CSV
                    output = StringIO()
                    if fields:
                        writer = csv.writer(output)
                        writer.writerow(fields)
                    csv_content = output.getvalue()
                    output.close()
                else:
                    # 收集所有字段（优先使用指定的 fields，否则从数据中提取）
                    if fields:
                        csv_fields = fields
                    else:
                        csv_fields = []
                        for record in records:
                            if isinstance(record, dict):
                                for key in record.keys():
                                    if key not in csv_fields:
                                        csv_fields.append(key)

                    output = StringIO()
                    writer = csv.writer(output)
                    writer.writerow(csv_fields)

                    for record in records:
                        if isinstance(record, dict):
                            row = []
                            for field in csv_fields:
                                value = record.get(field, '')
                                if isinstance(value, (list, dict)):
                                    value = json.dumps(value, ensure_ascii=False)
                                if value is None:
                                    value = ''
                                row.append(str(value))
                            writer.writerow(row)
                        else:
                            writer.writerow([str(record)])

                    csv_content = output.getvalue()
                    output.close()

                # 生成文件名
                filename = f'{data_type}_{time.strftime("%Y%m%d_%H%M%S")}.csv'

                self.send_response(200)
                self.send_header('Content-type', 'text/csv; charset=utf-8')
                self.send_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                self.end_headers()
                # 添加 BOM 以支持 Excel 正确识别 UTF-8
                self.wfile.write(b'\xef\xbb\xbf')
                self.wfile.write(csv_content.encode('utf-8'))
                return

            # 不支持的格式
            self.send_response(400)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': f'不支持的导出格式: {export_format}，支持: json, csv'
            }, ensure_ascii=False).encode())

        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': '请求体 JSON 格式错误'
            }, ensure_ascii=False).encode())
        except Exception as e:
            print(f"导出数据失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def send_head(self):
        """重写 send_head 方法以支持压缩和缓存"""
        path = self.translate_path(self.path)

        # 检查是否是目录
        if os.path.isdir(path):
            parts = urlparse(self.path)
            if not parts.path.endswith('/'):
                # 重定向到带斜杠的 URL
                self.send_response(301)
                new_parts = (parts[0], parts[1], parts[2] + '/',
                            parts[4], parts[5])
                new_url = urlparse.urlunparse(new_parts)
                self.send_header("Location", new_url)
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)

        # 检查文件是否存在
        if not os.path.exists(path):
            self.send_error(404, "File not found")
            return None

        # 读取文件内容
        try:
            with open(path, 'rb') as f:
                content = f.read()
        except IOError:
            self.send_error(404, "File not found")
            return None

        # 获取 MIME 类型
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type is None:
            mime_type = 'application/octet-stream'

        # 检查客户端是否支持 gzip
        accept_encoding = self.headers.get('Accept-Encoding', '')
        supports_gzip = 'gzip' in accept_encoding

        # 判断是否应该压缩
        should_compress = supports_gzip and self.should_compress(mime_type, len(content))

        # 准备响应内容
        if should_compress:
            compressed_content = self.compress_content(content)
            response_content = compressed_content
        else:
            response_content = content

        # 检查 ETag 条件请求
        if_none_match = self.headers.get('If-None-Match', '')
        if if_none_match:
            current_etag = f'"{self.generate_etag(content)}"'
            if if_none_match == current_etag:
                self.send_response(304)
                self.end_headers()
                return None

        # 发送响应头
        self.send_response(200)
        self.send_header('Content-type', mime_type)

        # 添加压缩头
        if should_compress:
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Vary', 'Accept-Encoding')

        self.send_header('Content-Length', len(response_content))

        # 添加缓存头
        self.add_cache_headers(mime_type, content)

        self.end_headers()

        # 返回响应内容
        return BytesIO(response_content)

def ensure_default_admin():
    """确保存在默认管理员账号"""
    try:
        data_file = os.path.join(DATA_DIR, 'workbench_data.json')
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                store_data = json.load(f)
        else:
            store_data = {
                '_version': '2.3',
                'projects': [], 'organizations': [], 'players': [],
                'finances': [], 'users': [], 'auditLogs': [],
                'notifications': [], 'knowledge': {'solutions': [], 'practices': [], 'training': []},
                'checklistState': {}, 'config': {}, 'materialTypes': [],
                'archiveConfig': {}, 'archiveMappings': {},
                '_version_timestamp': int(time.time() * 1000)
            }

        for key in ['projects', 'organizations', 'players', 'finances', 'users', 'auditLogs', 'notifications']:
            if key not in store_data or not isinstance(store_data[key], list):
                store_data[key] = []

        admin_exists = any(u.get('username') == 'admin' for u in store_data.get('users', []))
        if not admin_exists:
            import secrets
            import string
            temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
            hashed_password = hash_password(temp_password)
            admin_user = {
                'id': 'u' + str(int(time.time() * 1000)),
                'username': 'admin',
                'password': hashed_password,
                'passwordHashed': True,
                'role': 'admin',
                'realName': '系统管理员',
                'email': 'admin@example.com',
                'createdAt': time.strftime('%Y-%m-%d %H:%M:%S'),
                'mustChangePassword': True
            }
            store_data['users'].append(admin_user)
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(store_data, f, ensure_ascii=False, indent=2)
            # 首次初始化也要同步到 SQLite：读取时以 SQLite 优先，
            # 若只写 JSON，重启后从库里读到的 users 是空的
            try:
                from server.database import get_data_store
                get_data_store().save_all_data(store_data)
            except Exception as sync_err:
                print(f"初始管理员同步到 SQLite 失败（可忽略，下次保存会补齐）: {sync_err}")
            print(f'已创建管理员账号: admin / {temp_password}（首次登录后请立即修改密码）')
            setup_file = os.path.join(DATA_DIR, 'initial_password.txt')
            with open(setup_file, 'w', encoding='utf-8') as f:
                f.write(f'username: admin\npassword: {temp_password}\n')
                f.write('请首次登录后立即修改密码，并删除此文件\n')
            print(f'初始密码已保存到: {setup_file}')
        else:
            print('管理员账号已存在')
    except Exception as e:
        print(f"初始化管理员账号失败: {e}")

def initialize_notifications():
    """初始化示例通知"""
    notifications_file = os.path.join(DATA_DIR, 'notifications.json')

    if os.path.exists(notifications_file):
        return

    import datetime
    now = time.time()

    sample_notifications = [
        {
            'id': 'welcome-1',
            'title': '欢迎使用媒体艺术智能工作台 v2.0',
            'content': '系统已升级到最新版本，新增通知功能、优化的图标显示和更多改进。点击查看更新日志。',
            'type': 'success',
            'isRead': False,
            'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now - 3600)),
            'link': '/guide'
        },
        {
            'id': 'tip-1',
            'title': '💡 使用提示：定期备份您的数据',
            'content': '建议每周至少备份一次数据，以防意外丢失。您可以在设置页面中配置自动备份。',
            'type': 'info',
            'isRead': False,
            'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now - 7200)),
            'link': '/settings'
        },
        {
            'id': 'warning-1',
            'title': '⚠️ 请检查临时文件目录',
            'content': 'assets目录中的临时文件占用空间可能较大，建议定期清理以释放磁盘空间。',
            'type': 'warning',
            'isRead': True,
            'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now - 86400)),
            'link': '/settings'
        },
        {
            'id': 'feature-1',
            'title': '🎨 新功能：原生Windows图标支持',
            'content': '文件和文件夹现在使用Windows系统原生图标，显示效果更加清晰自然。',
            'type': 'info',
            'isRead': True,
            'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now - 172800)),
            'link': None
        }
    ]

    with open(notifications_file, 'w', encoding='utf-8') as f:
        json.dump(sample_notifications, f, ensure_ascii=False, indent=2)

    print("已初始化示例通知")

with socketserver.ThreadingTCPServer(("", PORT), WorkbenchHandler) as httpd:
    httpd.allow_reuse_address = True
    ensure_default_admin()
    initialize_notifications()
    print(f"工作台服务器运行中...")
    print(f"访问地址: http://localhost:{PORT}")
    print(f"数据存储目录: {PERSISTENT_DIR}")
    print(f"素材目录: {ASSETS_DIR}")
    print(f"归档目录: {ARCHIVES_DIR}")
    print(f"资源目录: {RESOURCES_DIR}")
    print(f"数据目录: {DATA_DIR}")
    print(f"备份目录: {BACKUP_DIR}")
    print("按 Ctrl+C 停止服务器")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
