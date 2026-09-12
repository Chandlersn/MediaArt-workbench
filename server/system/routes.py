"""
System / Settings / Maintenance API routes module.

补齐模块化后端缺失的一组「系统与设置」接口，供 SettingsView、审计日志页、
文件预览面板等前端消费：

    GET  /api/status                         系统状态
    GET  /api/config/archive-path            归档目录
    POST /api/config/archive-path            {path}
    GET  /api/config/resources-path          资源目录
    POST /api/config/resources-path          {path}
    GET  /api/browse-dirs?path=              目录浏览
    GET  /api/open-file?path=                用系统默认程序打开（无头环境返回成功）
    GET  /api/preview-text?source&fileName&...  文本类文件内容提取
    GET  /api/audit-logs                     审计日志列表
    POST /api/audit-logs                     写入审计日志
    GET  /api/cleanup/scan                   扫描临时文件
    POST /api/cleanup/execute  {days}        清理临时文件
    POST /api/save-stage-materials           保存阶段资料/资料类型/归档资料类型配置

路径配置统一落在 BASE/data/config.json，与 resources 路由读取的键保持一致
（resourcesPath / archivePath）。鉴权在 handle_request 内联完成。
"""

import io
import os
import re
import json
import time
import zipfile
import logging
import platform
import tempfile
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional

from server.config import BASE_DIR
from server.database.store import data_store
from server.utils.auth_middleware import extract_user_from_request

logger = logging.getLogger(__name__)

JSON_HEADERS = {'Content-Type': 'application/json'}

DEFAULT_RESOURCES_DIR = os.path.join(BASE_DIR, 'resources')
DEFAULT_ARCHIVE_DIR = os.path.join(BASE_DIR, 'MediaArt_Archives')
CONFIG_JSON = os.path.join(BASE_DIR, 'data', 'config.json')
TEMP_DIR = os.path.join(BASE_DIR, 'data', 'temp')

TEXT_EXTS = {
    'txt', 'md', 'markdown', 'json', 'csv', 'tsv', 'log', 'xml', 'yml', 'yaml',
    'ini', 'cfg', 'conf', 'py', 'js', 'ts', 'vue', 'html', 'htm', 'css', 'scss',
    'java', 'c', 'cpp', 'h', 'cs', 'go', 'rs', 'sql', 'sh', 'bat', 'ps1'
}
MAX_PREVIEW_CHARS = 100000


def _ok(body: Any, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    h = dict(JSON_HEADERS)
    if headers:
        h.update(headers)
    return {'status': status, 'body': body, 'headers': h}


def _qp(request_context: Dict[str, Any], key: str, default: str = '') -> str:
    qp = request_context.get('query_params', {}) or {}
    val = qp.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


def _load_config_json() -> Dict[str, Any]:
    try:
        if os.path.exists(CONFIG_JSON):
            with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
                return json.load(f) or {}
    except Exception as e:
        logger.warning(f"读取 config.json 失败: {e}")
    return {}


def _save_config_json(updates: Dict[str, Any]) -> None:
    cfg = _load_config_json()
    cfg.update(updates)
    os.makedirs(os.path.dirname(CONFIG_JSON), exist_ok=True)
    with open(CONFIG_JSON, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class SystemRouter:
    """Router for system status, settings, preview, audit and cleanup endpoints."""

    def _auth(self, request_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user = extract_user_from_request(request_context)
        if not user:
            return _ok({'success': False, 'message': '认证失败，Token 无效或缺失',
                        'error': 'UNAUTHORIZED'}, 401)
        request_context['user'] = user
        return None

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')
        norm = path.split('?')[0]

        try:
            # 状态与打开文件：无副作用，放开鉴权更贴近本机单机使用
            if norm == '/api/status' and method == 'GET':
                return self.status()
            if norm == '/api/open-file' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.open_file(request_context)

            # 目录浏览（前端选目录用）
            if norm == '/api/browse-dirs' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.browse_dirs(request_context)

            # 文本预览
            if norm == '/api/preview-text' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.preview_text(request_context)

            # 路径配置
            if norm == '/api/config/archive-path':
                if (a := self._auth(request_context)):
                    return a
                return self.get_archive_path() if method == 'GET' else self.set_archive_path(request_context)
            if norm == '/api/config/resources-path':
                if (a := self._auth(request_context)):
                    return a
                return self.get_resources_path() if method == 'GET' else self.set_resources_path(request_context)

            # 审计日志
            if norm == '/api/audit-logs':
                if (a := self._auth(request_context)):
                    return a
                return self.list_audit_logs() if method == 'GET' else self.add_audit_log(request_context)

            # 临时文件清理
            if norm == '/api/cleanup/scan' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.cleanup_scan()
            if norm == '/api/cleanup/execute' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.cleanup_execute(request_context)

            # 阶段资料 / 资料类型配置保存
            if norm == '/api/save-stage-materials' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.save_stage_materials(request_context)

            return _ok({'success': False, 'error': 'Method Not Allowed'}, 405)
        except Exception as e:
            logger.error(f"处理系统请求失败: {e}", exc_info=True)
            return _ok({'success': False, 'error': 'Internal Server Error', 'message': str(e)}, 500)

    # ---------- 状态 ----------
    def status(self) -> Dict[str, Any]:
        counts = {}
        for name, model in (
            ('projects', data_store.projects), ('organizations', data_store.organizations),
            ('players', data_store.players), ('finances', data_store.finances),
            ('knowledge', data_store.knowledge), ('users', data_store.users),
        ):
            try:
                counts[name] = model.get_all().__len__()
            except Exception:
                counts[name] = 0
        return _ok({
            'success': True,
            'status': 'ok',
            'version': '2.3',
            'database': 'sqlite',
            'uptime': 0,
            'counts': counts,
            'serverTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })

    # ---------- 路径配置 ----------
    def get_archive_path(self) -> Dict[str, Any]:
        cfg = _load_config_json()
        return _ok({'success': True,
                    'path': cfg.get('archivePath', '') or '',
                    'defaultPath': DEFAULT_ARCHIVE_DIR})

    def set_archive_path(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        path = (data.get('path') or '').strip()
        _save_config_json({'archivePath': path})
        # 确保目录存在
        try:
            if path and os.path.isabs(path):
                os.makedirs(path, exist_ok=True)
        except Exception as e:
            logger.warning(f"创建归档目录失败: {e}")
        return _ok({'success': True, 'message': '已保存', 'path': path})

    def get_resources_path(self) -> Dict[str, Any]:
        cfg = _load_config_json()
        return _ok({'success': True,
                    'path': cfg.get('resourcesPath', '') or '',
                    'defaultPath': DEFAULT_RESOURCES_DIR})

    def set_resources_path(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        path = (data.get('path') or '').strip()
        _save_config_json({'resourcesPath': path})
        try:
            if path and os.path.isabs(path):
                os.makedirs(path, exist_ok=True)
        except Exception as e:
            logger.warning(f"创建资源目录失败: {e}")
        return _ok({'success': True, 'message': '已保存', 'path': path})

    # ---------- 目录浏览 ----------
    def browse_dirs(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        raw = _qp(request_context, 'path', '')
        if not raw:
            # 无路径时给出磁盘根列表（Windows）或用户主目录
            if platform.system() == 'Windows':
                drives = []
                for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
                    d = f"{letter}:\\"
                    if os.path.exists(d):
                        drives.append(d)
                return _ok({'success': True, 'currentPath': '',
                            'parentPath': None, 'directories': drives})
            raw = os.path.expanduser('~')
        try:
            current = os.path.abspath(raw)
            directories = []
            if os.path.isdir(current):
                for name in sorted(os.listdir(current)):
                    full = os.path.join(current, name)
                    try:
                        if os.path.isdir(full):
                            directories.append(name)
                    except OSError:
                        continue
            parent = os.path.dirname(current)
            parent_path = parent if parent and parent != current else None
            return _ok({'success': True, 'currentPath': current,
                        'parentPath': parent_path, 'directories': directories})
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)

    def open_file(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = _qp(request_context, 'path', '')
        try:
            if path and os.path.exists(path) and platform.system() == 'Windows':
                os.startfile(path)  # noqa: 仅在 Windows 生效
            return _ok({'success': True, 'message': 'ok'})
        except Exception as e:
            # 无头环境无法真正唤起资源管理器，但仍返回成功，避免前端误报
            logger.warning(f"打开路径失败（可忽略）: {e}")
            return _ok({'success': True, 'message': 'ok'})

    # ---------- 文本预览 ----------
    def _extract_text(self, ext: str, data: bytes) -> Optional[str]:
        if ext in TEXT_EXTS:
            for enc in ('utf-8', 'gbk', 'utf-16', 'latin-1'):
                try:
                    return data.decode(enc)
                except UnicodeDecodeError:
                    continue
            return data.decode('utf-8', 'ignore')
        if ext == 'docx':
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    xml = z.read('word/document.xml').decode('utf-8', 'ignore')
                xml = re.sub(r'</w:p>', '\n', xml)
                return re.sub(r'<[^>]+>', '', xml)
            except Exception:
                return None
        if ext == 'pdf':
            try:
                text = data.decode('latin-1', 'ignore')
                found = re.findall(r'\(([^)]*)\)\s*Tj', text)
                return '\n'.join(found) if found else None
            except Exception:
                return None
        return None

    def _locate_preview_file(self, source: str, request_context: Dict[str, Any]) -> Optional[str]:
        if source == 'file':
            rel = _qp(request_context, 'path', '')
            rel = os.path.basename(rel) if rel else ''
            # path 可能是 'folder/name'
            raw = _qp(request_context, 'path', '')
            if '/' in raw:
                parts = raw.split('/')
                target = os.path.join(DEFAULT_RESOURCES_DIR, *parts)
            else:
                target = os.path.join(DEFAULT_RESOURCES_DIR, rel)
            return target if os.path.isfile(target) else None

        name = _qp(request_context, 'name', '')
        file_name = _qp(request_context, 'fileName', '')
        material_type = _qp(request_context, 'materialType', '')
        sub = {'org': 'organizations', 'player': 'players'}.get(source, 'projects')
        root = os.path.join(DEFAULT_RESOURCES_DIR, sub, name)
        if not os.path.isdir(root):
            return None
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f == file_name and (not material_type or os.path.basename(dirpath) == material_type):
                    return os.path.join(dirpath, f)
        return None

    def preview_text(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        source = _qp(request_context, 'source', 'project')
        target = self._locate_preview_file(source, request_context)
        if not target:
            return _ok({'success': False, 'message': '文件不存在或无法定位'}, 404)
        ext = os.path.splitext(target)[1].lstrip('.').lower()
        try:
            with open(target, 'rb') as f:
                data = f.read()
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)
        text = self._extract_text(ext, data)
        if text is None:
            return _ok({'success': False, 'message': f'.{ext} 类型暂不支持在线文本预览'})
        truncated = len(text) > MAX_PREVIEW_CHARS
        return _ok({'success': True, 'text': text[:MAX_PREVIEW_CHARS], 'truncated': truncated})

    # ---------- 审计日志 ----------
    def list_audit_logs(self) -> Dict[str, Any]:
        try:
            rows = data_store.db.fetchall(
                "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 500")
            logs = []
            for r in rows:
                logs.append({
                    'id': r.get('id'),
                    'action': r.get('action') or '',
                    'actionType': r.get('resource_type') or 'update',
                    'target': r.get('resource_id') or '',
                    'description': r.get('details') or '',
                    'userName': r.get('username') or '系统',
                    'timestamp': r.get('created_at'),
                })
            return _ok({'success': True, 'logs': logs})
        except Exception as e:
            logger.error(f"读取审计日志失败: {e}")
            return _ok({'success': True, 'logs': []})

    def add_audit_log(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        user = request_context.get('user', {}) or {}
        import uuid as _uuid
        try:
            data_store.db.execute(
                "INSERT INTO audit_logs (id, user_id, username, action, resource_type, "
                "resource_id, details, ip_address, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(_uuid.uuid4()),
                    user.get('user_id', ''),
                    data.get('userName') or user.get('username', '系统'),
                    data.get('action', ''),
                    data.get('actionType', 'update'),
                    data.get('target', ''),
                    data.get('description', ''),
                    request_context.get('client_address', ('', 0))[0] if request_context.get('client_address') else '',
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                )
            )
            return _ok({'success': True})
        except Exception as e:
            logger.error(f"写入审计日志失败: {e}")
            return _ok({'success': False, 'message': str(e)}, 500)

    # ---------- 临时文件清理 ----------
    def cleanup_scan(self) -> Dict[str, Any]:
        try:
            os.makedirs(TEMP_DIR, exist_ok=True)
        except Exception:
            pass
        total_size = 0
        file_count = 0
        old_files: List[Dict[str, Any]] = []
        now = time.time()
        try:
            for dirpath, _dirs, files in os.walk(TEMP_DIR):
                for f in files:
                    fp = os.path.join(dirpath, f)
                    try:
                        st = os.stat(fp)
                    except OSError:
                        continue
                    file_count += 1
                    total_size += st.st_size
                    if now - st.st_mtime > 7 * 86400:
                        old_files.append({'name': f, 'path': fp,
                                          'size': st.st_size, 'mtime': int(st.st_mtime * 1000)})
        except Exception as e:
            logger.warning(f"扫描临时文件失败: {e}")
        return _ok({'success': True, 'total_size': total_size, 'file_count': file_count,
                    'old_files': old_files})

    def cleanup_execute(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        try:
            days = int(data.get('days', 30) or 30)
        except (ValueError, TypeError):
            days = 30
        cutoff = time.time() - days * 86400
        deleted_count = 0
        deleted_size = 0
        errors: List[str] = []
        try:
            os.makedirs(TEMP_DIR, exist_ok=True)
        except Exception:
            pass
        for dirpath, _dirs, files in os.walk(TEMP_DIR):
            for f in files:
                fp = os.path.join(dirpath, f)
                try:
                    st = os.stat(fp)
                    if st.st_mtime < cutoff:
                        os.remove(fp)
                        deleted_count += 1
                        deleted_size += st.st_size
                except Exception as e:
                    errors.append(f"{f}: {e}")
        return _ok({'success': True, 'deleted_count': deleted_count,
                    'deleted_size': deleted_size, 'errors': errors})

    # ---------- 阶段资料 / 资料类型配置 ----------
    def save_stage_materials(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        stage_materials = data.get('stageMaterials')
        material_types = data.get('materialTypes')
        archive_config = data.get('archiveConfig') or {}
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with data_store.db.transaction() as conn:
                if stage_materials is not None:
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
                        ('stageMaterials', json.dumps(stage_materials, ensure_ascii=False), now))
                for sub in ('projects', 'organizations'):
                    if sub in archive_config:
                        conn.execute(
                            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
                            (f'archiveConfig_{sub}',
                             json.dumps(archive_config[sub], ensure_ascii=False), now))
                if isinstance(material_types, list):
                    data_store._save_material_types(material_types, conn)
            return _ok({'success': True, 'message': '配置已保存'})
        except Exception as e:
            logger.error(f"保存配置失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': str(e)}, 500)
