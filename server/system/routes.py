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

from server.config import BASE_DIR, SERVER_START_TIME
from server.database.store import data_store
from server.utils.auth_middleware import extract_user_from_request
from server.utils.trash import list_trash, restore_trash, purge_trash, purge_all
from server.archive.taxonomy import (
    authoritative_material_types, ARCHIVE_TOP_DIRS, ENTITY_LEVEL_DIRS,
)

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

    def _perm(self, request_context: Dict[str, Any], module: str,
              action: str) -> Optional[Dict[str, Any]]:
        """在 _auth 之上追加权限校验（用于系统类**写**接口）。

        此前这些接口只校验「已登录」，任意账号（含 viewer）都能改系统配置、
        清理文件、清空回收站。返回 None 表示放行。
        """
        from server.utils.permissions import has_permission
        user = request_context.get('user', {}) or {}
        if not has_permission(user.get('role', 'viewer'), module, action):
            return _ok({'success': False,
                        'message': f'权限不足，需要 {module}:{action} 权限',
                        'error': 'FORBIDDEN'}, 403)
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

            # 路径配置（读取仅需登录；修改需 settings:edit）
            if norm == '/api/config/archive-path':
                if (a := self._auth(request_context)):
                    return a
                if method != 'GET' and (p := self._perm(request_context, 'settings', 'edit')):
                    return p
                return self.get_archive_path() if method == 'GET' else self.set_archive_path(request_context)
            if norm == '/api/config/resources-path':
                if (a := self._auth(request_context)):
                    return a
                if method != 'GET' and (p := self._perm(request_context, 'settings', 'edit')):
                    return p
                return self.get_resources_path() if method == 'GET' else self.set_resources_path(request_context)

            # 审计日志
            if norm == '/api/audit-logs':
                if (a := self._auth(request_context)):
                    return a
                return self.list_audit_logs() if method == 'GET' else self.add_audit_log(request_context)
            if norm == '/api/audit-logs/clear' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.clear_audit_logs(request_context)

            # 临时文件清理
            if norm == '/api/cleanup/scan' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.cleanup_scan()
            if norm == '/api/cleanup/execute' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                if (p := self._perm(request_context, 'settings', 'delete')):
                    return p
                return self.cleanup_execute(request_context)

            # 阶段资料 / 资料类型配置保存
            if norm == '/api/save-stage-materials' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                if (p := self._perm(request_context, 'settings', 'edit')):
                    return p
                return self.save_stage_materials(request_context)

            # 回收站
            if norm == '/api/trash' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.list_trash_endpoint()
            if norm == '/api/trash/restore' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                if (p := self._perm(request_context, 'settings', 'edit')):
                    return p
                return self.restore_trash_endpoint(request_context)
            if norm == '/api/trash/purge' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                if (p := self._perm(request_context, 'settings', 'delete')):
                    return p
                return self.purge_trash_endpoint(request_context)
            if norm == '/api/trash/purge-all' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                if (p := self._perm(request_context, 'settings', 'delete')):
                    return p
                return self.purge_all_trash_endpoint()

            # 资料类型单一权威
            if norm == '/api/material-types' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.material_types_endpoint()

            # 归档↔库对账
            if norm == '/api/archive/reconcile' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.archive_reconcile_endpoint()

            return _ok({'success': False, 'error': 'Method Not Allowed'}, 405)
        except Exception as e:
            logger.error(f"处理系统请求失败: {e}", exc_info=True)
            return _ok({'success': False, 'error': 'Internal Server Error', 'message': str(e)}, 500)

    # ---------- 状态 ----------
    @staticmethod
    def _format_uptime(seconds: int) -> str:
        """把秒数格式化为可读的运行时长。"""
        seconds = max(0, int(seconds))
        d, rem = divmod(seconds, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        if d:
            return f'{d} 天 {h} 小时 {m} 分'
        if h:
            return f'{h} 小时 {m} 分'
        if m:
            return f'{m} 分 {s} 秒'
        return f'{s} 秒'

    def _data_files_size(self) -> int:
        """数据文件占用（SQLite 主库 + WAL/SHM + JSON 镜像）。"""
        total = 0
        for fn in ('workbench.db', 'workbench.db-wal', 'workbench.db-shm',
                   'workbench_data.json'):
            p = os.path.join(BASE_DIR, 'data', fn)
            try:
                if os.path.isfile(p):
                    total += os.path.getsize(p)
            except OSError:
                pass
        return total

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
            'uptime': self._format_uptime(time.time() - SERVER_START_TIME),
            'uptimeSeconds': int(time.time() - SERVER_START_TIME),
            'data_size': self._data_files_size(),
            'system': {
                'platform': f'{platform.system()} {platform.release()}'.strip(),
                'python_version': platform.python_version(),
            },
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
        """定位待预览的文件。

        ⚠️ 此前这里只在硬编码的 resources/ 目录里找、从不看归档目录 ——
        导致归档页（source=file）与详情页资料（project/player/org）的文本预览恒 404。
        现统一复用「归档优先」的定位逻辑。
        """
        if source == 'file':
            # 相对路径可能是归档路径（01_项目资料/…）或素材库路径，交给统一解析
            from server.resources.routes import _resolve_material_path
            rel = _qp(request_context, 'path', '') or _qp(request_context, 'fileName', '')
            target = _resolve_material_path(rel) if rel else None
            return target if target and os.path.isfile(target) else None

        kind = {'project': 'project', 'org': 'org', 'player': 'player'}.get(source)
        if not kind:
            return None
        # 项目 / 机构 / 选手资料：与 materials 路由同一套归档定位逻辑
        try:
            from server.materials.routes import MaterialsRouter
            return MaterialsRouter().locate(
                kind,
                _qp(request_context, 'name', ''),
                _qp(request_context, 'fileName', ''),
                _qp(request_context, 'materialType', ''))
        except Exception as e:
            logger.warning(f"定位预览文件失败: {e}")
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
        # 电子表格 → 解析为表格数据，交前端渲染成表格
        # 按**内容**嗅探真实格式（xlsx/xlsm、旧版 OLE2 的 xls、以及「.xls 实为 HTML 表格」）
        if ext in ('xlsx', 'xlsm', 'xls'):
            from server.utils.spreadsheet import spreadsheet_rows
            try:
                fmt, sheet, rows, truncated = spreadsheet_rows(data)
            except Exception as e:
                logger.warning(f"解析表格失败 {target}: {e}")
                fmt, sheet, rows, truncated = '', '', [], False
            if rows:
                return _ok({'success': True, 'kind': 'table', 'format': fmt,
                            'sheetName': sheet, 'rows': rows, 'truncated': truncated})
            return _ok({'success': False,
                        'message': '无法解析该表格（可能是加密文件，或格式不受支持）'})

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
                    'createdAt': r.get('created_at'),
                    'ip': r.get('ip_address') or '',
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
            # ⚠️ 必须走 transaction() 提交：Database.execute() 只是 conn.execute()，
            # 不 commit；连接又是线程本地（每请求独立），未提交的 INSERT 对其它请求
            # 不可见且随线程结束被回滚 —— 曾导致审计日志「写成功但查不到」。
            with data_store.db.transaction() as conn:
                conn.execute(
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

    def clear_audit_logs(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """一键清除全部审计日志（需「系统设置」的删除权限）。

        清除动作本身不再写回日志，避免用户看到「清完还剩一条」的困惑。
        """
        user = request_context.get('user', {}) or {}
        from server.utils.permissions import has_permission
        if not has_permission(user.get('role', 'viewer'), 'settings', 'delete'):
            return _ok({'success': False, 'message': '权限不足，需要「系统设置」的删除权限'}, 403)
        try:
            with data_store.db.transaction() as conn:
                cur = conn.execute("DELETE FROM audit_logs")
                removed = cur.rowcount if (cur.rowcount and cur.rowcount > 0) else 0
            return _ok({'success': True, 'removed': removed,
                        'message': f'已清除 {removed} 条日志'})
        except Exception as e:
            logger.error(f"清除审计日志失败: {e}")
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

    # ---------- 回收站 ----------
    def list_trash_endpoint(self) -> Dict[str, Any]:
        items = list_trash()
        return _ok({'success': True, 'items': items, 'count': len(items)})

    def restore_trash_endpoint(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        rid = (data.get('id') or '').strip()
        ok, msg = restore_trash(rid)
        return _ok({'success': ok, 'message': msg}, 200 if ok else 400)

    def purge_trash_endpoint(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'') or b'{}'
        data = json.loads(body) if body else {}
        rid = (data.get('id') or '').strip()
        if not rid:
            return _ok({'success': False, 'message': '缺少回收项 id'}, 400)
        removed = purge_trash(rid)
        return _ok({'success': removed, 'message': '已彻底删除' if removed else '回收项不存在'})

    def purge_all_trash_endpoint(self) -> Dict[str, Any]:
        n = purge_all()
        return _ok({'success': True, 'message': f'已清空 {n} 项'})

    # ---------- 资料类型单一权威 ----------
    def material_types_endpoint(self) -> Dict[str, Any]:
        """返回归档资料类型的单一权威来源（前端下拉与后端落库共用）。"""
        return _ok({'success': True, 'data': authoritative_material_types()})

    # ---------- 归档 ↔ 库对账（只读） ----------
    def _resolve_archive_path(self) -> str:
        cfg = _load_config_json()
        p = (cfg.get('archivePath') or '').strip()
        return p if p and os.path.isabs(p) else DEFAULT_ARCHIVE_DIR

    def archive_reconcile_endpoint(self) -> Dict[str, Any]:
        return _ok({'success': True, **self._reconcile_archive()})

    def _reconcile_archive(self) -> Dict[str, Any]:
        """只读对账：实体级分类（项目/选手/机构）的磁盘文件夹名 vs DB 实体名差集，
        以及非实体级分类（财务/知识/备份）的空一级目录。

        返回：
            missing_in_db  磁盘有、库里没有的文件夹（孤儿目录，可能被误删实体）
            missing_on_disk 库里有关、磁盘没有的实体（缺归档目录）
            empty_top_dirs 完全为空的一级分类目录
        """
        archive_path = self._resolve_archive_path()
        result: Dict[str, Any] = {
            'archive_path': archive_path,
            'missing_in_db': {},
            'missing_on_disk': {},
            'empty_top_dirs': [],
            'summary': {},
        }
        if not os.path.isdir(archive_path):
            result['summary'] = {'error': f'归档目录不存在: {archive_path}'}
            return result

        db_names: Dict[str, set] = {
            '01_项目资料': {r.get('name', '') for r in (data_store.projects.get_all() or [])},
            '02_选手档案': {r.get('name', '') for r in (data_store.players.get_all() or [])},
            '03_合作机构': {r.get('name', '') for r in (data_store.organizations.get_all() or [])},
        }

        for top in ARCHIVE_TOP_DIRS:
            top_path = os.path.join(archive_path, top)
            if top in ENTITY_LEVEL_DIRS:
                disk_entities: set = set()
                if os.path.isdir(top_path):
                    for name in os.listdir(top_path):
                        if os.path.isdir(os.path.join(top_path, name)):
                            disk_entities.add(name)
                db = db_names.get(top, set())
                miss_db = sorted(disk_entities - db)        # 孤儿：磁盘有、库无
                miss_disk = sorted(db - disk_entities)      # 缺目录：库有、磁盘无
                if miss_db:
                    result['missing_in_db'][top] = miss_db
                if miss_disk:
                    result['missing_on_disk'][top] = miss_disk
            else:
                # 非实体级：仅统计是否为空
                empty = True
                if os.path.isdir(top_path):
                    for _ in os.scandir(top_path):
                        empty = False
                        break
                if empty:
                    result['empty_top_dirs'].append(top)

        result['summary'] = {
            'orphan_dirs': sum(len(v) for v in result['missing_in_db'].values()),
            'missing_dirs': sum(len(v) for v in result['missing_on_disk'].values()),
            'empty_top_dirs': len(result['empty_top_dirs']),
        }
        return result
