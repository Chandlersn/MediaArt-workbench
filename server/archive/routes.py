"""
Archive file system API routes module.
Handles file browsing, upload, download, and management in MediaArt_Archives folder.
"""

import os
import json
import logging
import shutil
from typing import Dict, Any, List
from urllib.parse import unquote

from server.archive.icon_extractor import get_file_icon, get_folder_icon
from server.utils.auth_middleware import require_auth, require_permission

logger = logging.getLogger(__name__)

# 归档根目录：与 resources / materials 走同一套解析 —— 优先 config.json 的 archivePath，
# 否则退回 BASE_DIR/MediaArt_Archives。
# ⚠️ 此前这里是 os.path.join(BASE_DIR, 'MediaArt_Archives')，绕过了配置：用户在设置里
# 改了归档目录后，归档管理页仍然读写默认目录（而资源中心走的是配置），两边会不一致。
from server.resources.routes import get_archives_dir
from server.utils.trash import send_to_trash
ARCHIVE_DIR = get_archives_dir()


def ensure_archive_dir():
    """Ensure archive directory exists with default top-level folders.

    一级分类来自 server/archive/taxonomy.py 的单一权威定义，不在此重复硬编码。
    """
    from server.archive.taxonomy import ARCHIVE_TOP_DIRS
    if not os.path.exists(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
    for folder in ARCHIVE_TOP_DIRS:
        folder_path = os.path.join(ARCHIVE_DIR, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)


class ArchiveRouter:
    """Router for archive file system operations."""

    def __init__(self):
        ensure_archive_dir()

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle archive-related requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path == '/api/count-files':
                return self.count_files(request_context)
            elif method == 'GET' and path == '/api/file-icon':
                return self.file_icon(request_context)
            elif method == 'GET' and path == '/api/list-archives':
                return self.list_archives(request_context)
            elif method == 'POST' and path == '/api/open-archive':
                return self.open_archive(request_context)
            elif method == 'DELETE' and path == '/api/delete-file':
                return self.delete_file(request_context)
            elif method == 'DELETE' and path == '/api/delete-folder':
                return self.delete_folder(request_context)
            elif method == 'POST' and path == '/api/create-folder':
                return self.create_folder(request_context)
            elif method == 'POST' and path == '/api/upload':
                return self.upload_file(request_context)
            elif method == 'PUT' and path == '/api/rename-folder':
                return self.rename_folder(request_context)
            elif method == 'PUT' and path == '/api/rename-file':
                return self.rename_file(request_context)
            elif method == 'GET' and path == '/api/archive-taxonomy':
                return self.archive_taxonomy(request_context)
            elif method == 'GET' and path == '/api/search-archives':
                return self.search_archives(request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling archive request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    def archive_taxonomy(self, request_context=None) -> Dict[str, Any]:
        """归档分类的单一权威定义（供前端取分类描述与二级目录）。

        定义来源：server/archive/taxonomy.py。只读、无需鉴权。
        """
        from server.archive.taxonomy import as_dict
        return {
            'status': 200,
            'body': as_dict(),
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('resources', 'view')
    def search_archives(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """递归搜索归档下的文件夹与文件（名称包含匹配，大小写不敏感）。

        参数：q=关键词；folder=可选搜索起点（相对归档根目录；留空=整个归档）。
        结果含相对归档根目录的 path 与所在目录 parent，供前端展示与跳转。
        """
        qp = request_context.get('query_params', {}) or {}
        q = (qp.get('q', [''])[0] or '').strip()
        folder = unquote(qp.get('folder', [''])[0] or '').strip()
        empty = {
            'status': 200,
            'body': {'results': [], 'count': 0, 'truncated': False},
            'headers': {'Content-Type': 'application/json'}
        }
        if not q:
            return empty
        try:
            base = self._get_full_path(folder)
            if not os.path.isdir(base):
                return empty
            needle = q.lower()
            limit = 300
            archive_root = os.path.normpath(ARCHIVE_DIR)
            results = []
            truncated = False
            for root, dirs, filenames in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for name in dirs:
                    if needle in name.lower():
                        rel = os.path.relpath(os.path.join(root, name), archive_root).replace('\\', '/')
                        results.append({
                            'name': name, 'path': rel, 'type': 'folder',
                            'parent': os.path.dirname(rel).replace('\\', '/')
                        })
                        if len(results) >= limit:
                            truncated = True
                            break
                if truncated:
                    break
                for name in filenames:
                    if name.startswith('.') or needle not in name.lower():
                        continue
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, archive_root).replace('\\', '/')
                    try:
                        st = os.stat(full)
                        size, modified = st.st_size, st.st_mtime
                    except OSError:
                        size, modified = 0, 0
                    results.append({
                        'name': name, 'path': rel, 'type': 'file',
                        'parent': os.path.dirname(rel).replace('\\', '/'),
                        'size': size, 'modified': modified
                    })
                    if len(results) >= limit:
                        truncated = True
                        break
                if truncated:
                    break
            # 文件夹在前，其余按路径排序，便于逐行扫读
            results.sort(key=lambda r: (0 if r['type'] == 'folder' else 1, r['path']))
            return {
                'status': 200,
                'body': {'results': results, 'count': len(results), 'truncated': truncated},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            logger.error(f"搜索归档失败: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'edit')
    def rename_file(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """重命名归档内的文件（同目录内改名）。

        用途：修正历史「机械名」（如 主体__类型_随机数），让人给出可读的标题。
        推荐格式：`主体_标题_日期.扩展名`（前端预填当前名，可改）。
        """
        from server.resources.routes import _sanitize_filename
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        path = data.get('path', '')
        safe_name = _sanitize_filename(data.get('newName', ''))
        if not safe_name:
            return {
                'status': 400,
                'body': {'success': False, 'message': '非法的文件名'},
                'headers': {'Content-Type': 'application/json'}
            }
        try:
            old_full = self._get_full_path(path)
            if not os.path.exists(old_full) or not os.path.isfile(old_full):
                return {
                    'status': 404,
                    'body': {'success': False, 'message': 'File not found'},
                    'headers': {'Content-Type': 'application/json'}
                }
            new_full = os.path.join(os.path.dirname(old_full), safe_name)
            if not new_full.startswith(os.path.normpath(ARCHIVE_DIR)):
                return {
                    'status': 403,
                    'body': {'success': False, 'message': '非法的路径'},
                    'headers': {'Content-Type': 'application/json'}
                }
            if os.path.exists(new_full):
                return {
                    'status': 409,
                    'body': {'success': False, 'message': '同名文件已存在'},
                    'headers': {'Content-Type': 'application/json'}
                }
            os.rename(old_full, new_full)
            return {
                'status': 200,
                'body': {'success': True, 'message': 'File renamed', 'newName': safe_name},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    def _get_full_path(self, rel_path: str) -> str:
        """Get full path from relative path, ensuring it's within archive dir."""
        # Normalize path
        rel_path = rel_path.strip('/').strip('\\')
        full_path = os.path.normpath(os.path.join(ARCHIVE_DIR, rel_path))

        # Security check: ensure path is within archive directory
        if not full_path.startswith(os.path.normpath(ARCHIVE_DIR)):
            raise ValueError('Invalid path: path traversal detected')

        return full_path

    @require_permission('resources', 'view')
    def count_files(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Count files and folders in a directory."""
        query_params = request_context.get('query_params', {})
        folder = query_params.get('folder', [''])[0]
        folder = unquote(folder) if folder else ''
        recursive = query_params.get('recursive', [''])[0].lower() == 'true'

        try:
            full_path = self._get_full_path(folder)

            if not os.path.exists(full_path):
                return {
                    'status': 200,
                    'body': {'folders': 0, 'files': 0},
                    'headers': {'Content-Type': 'application/json'}
                }

            if recursive:
                _, file_count = self._count_recursive(full_path)
                folder_count = 0
                for item in os.listdir(full_path):
                    if os.path.isdir(os.path.join(full_path, item)):
                        folder_count += 1
            else:
                folder_count = 0
                file_count = 0
                for item in os.listdir(full_path):
                    item_path = os.path.join(full_path, item)
                    if os.path.isdir(item_path):
                        folder_count += 1
                    else:
                        file_count += 1

            return {
                'status': 200,
                'body': {'folders': folder_count, 'files': file_count},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 200,
                'body': {'folders': 0, 'files': 0, 'error': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    def _count_recursive(self, dir_path: str) -> tuple:
        """Recursively count folders and files in a directory."""
        folder_count = 0
        file_count = 0
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isdir(item_path):
                folder_count += 1
                sub_folders, sub_files = self._count_recursive(item_path)
                folder_count += sub_folders
                file_count += sub_files
            else:
                file_count += 1
        return folder_count, file_count

    def file_icon(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        query_params = request_context.get('query_params', {})
        ext = query_params.get('ext', [''])[0]
        ext = unquote(ext) if ext else ''
        icon_type = query_params.get('type', ['file'])[0]
        size = 48

        try:
            size_str = query_params.get('size', ['48'])[0]
            size = int(size_str)
            if size < 16:
                size = 16
            elif size > 256:
                size = 256
        except (ValueError, IndexError):
            size = 48

        try:
            if icon_type == 'folder':
                png_data = get_folder_icon(size)
            else:
                png_data = get_file_icon(ext, size)

            if png_data:
                return {
                    'status': 200,
                    'body': png_data,
                    'headers': {
                        'Content-Type': 'image/png',
                        'Cache-Control': 'public, max-age=86400',
                    }
                }
            else:
                return {
                    'status': 404,
                    'body': json.dumps({'error': 'Icon not found'}).encode('utf-8'),
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error getting file icon: {e}")
            return {
                'status': 500,
                'body': json.dumps({'error': str(e)}).encode('utf-8'),
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'view')
    def list_archives(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """List files and folders in archive directory."""
        query_params = request_context.get('query_params', {})
        folder = query_params.get('folder', [''])[0]
        folder = unquote(folder) if folder else ''

        try:
            full_path = self._get_full_path(folder)

            if not os.path.exists(full_path):
                return {
                    'status': 200,
                    'body': [],
                    'headers': {'Content-Type': 'application/json'}
                }

            items = []
            for item in sorted(os.listdir(full_path)):
                item_path = os.path.join(full_path, item)
                rel_path = os.path.relpath(item_path, ARCHIVE_DIR).replace('\\', '/')

                if os.path.isdir(item_path):
                    items.append({
                        'name': item,
                        'path': rel_path,
                        'type': 'folder'
                    })
                else:
                    stat = os.stat(item_path)
                    items.append({
                        'name': item,
                        'path': rel_path,
                        'type': 'file',
                        'size': stat.st_size,
                        'modified': stat.st_mtime
                    })

            return {
                'status': 200,
                'body': items,
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'error': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'view')
    def open_archive(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Open a file with default application."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        path = data.get('path', '')

        try:
            full_path = self._get_full_path(path)

            if not os.path.exists(full_path):
                return {
                    'status': 404,
                    'body': {'success': False, 'message': 'File not found'},
                    'headers': {'Content-Type': 'application/json'}
                }

            # Use os.startfile on Windows, xdg-open on Linux
            import platform
            if platform.system() == 'Windows':
                os.startfile(full_path)
            else:
                import subprocess
                subprocess.call(['xdg-open', full_path])

            return {
                'status': 200,
                'body': {'success': True, 'message': 'File opened'},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'delete')
    def delete_file(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a file."""
        query_params = request_context.get('query_params', {})
        path = query_params.get('path', [''])[0]
        path = unquote(path) if path else ''

        try:
            full_path = self._get_full_path(path)

            if not os.path.exists(full_path) or os.path.isdir(full_path):
                return {
                    'status': 404,
                    'body': {'success': False, 'message': 'File not found'},
                    'headers': {'Content-Type': 'application/json'}
                }

            os.remove(full_path)

            return {
                'status': 200,
                'body': {'success': True, 'message': 'File deleted'},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'delete')
    def delete_folder(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a folder and its contents."""
        query_params = request_context.get('query_params', {})
        path = query_params.get('path', [''])[0]
        path = unquote(path) if path else ''

        try:
            full_path = self._get_full_path(path)

            if not os.path.exists(full_path) or not os.path.isdir(full_path):
                return {
                    'status': 404,
                    'body': {'success': False, 'message': 'Folder not found'},
                    'headers': {'Content-Type': 'application/json'}
                }

            rid = send_to_trash(full_path)
            return {
                'status': 200,
                'body': {'success': True,
                         'message': '文件夹已移入回收站' if rid else '文件夹已删除',
                         'trash_id': rid},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'edit')
    def create_folder(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new folder."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        path = data.get('path', '')

        try:
            full_path = self._get_full_path(path)

            if os.path.exists(full_path):
                return {
                    'status': 409,
                    'body': {'success': False, 'message': 'Folder already exists'},
                    'headers': {'Content-Type': 'application/json'}
                }

            os.makedirs(full_path, exist_ok=True)

            return {
                'status': 201,
                'body': {'success': True, 'message': 'Folder created'},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'edit')
    def upload_file(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Upload a file to archive directory."""
        body = request_context.get('body', b'')
        headers = request_context.get('headers', {})
        content_type = headers.get('Content-Type', headers.get('content-type', ''))

        if 'multipart/form-data' not in content_type:
            return {
                'status': 400,
                'body': {'success': False, 'message': 'Content-Type must be multipart/form-data'},
                'headers': {'Content-Type': 'application/json'}
            }

        try:
            boundary = None
            for part in content_type.split(';'):
                part = part.strip()
                if part.startswith('boundary='):
                    boundary = part[len('boundary='):]
                    break

            if not boundary:
                return {
                    'status': 400,
                    'body': {'success': False, 'message': 'Missing boundary in multipart data'},
                    'headers': {'Content-Type': 'application/json'}
                }

            boundary_bytes = boundary.encode('utf-8')
            parts = body.split(b'--' + boundary_bytes)

            target_path = ''
            file_data = None
            file_name = ''

            for part in parts:
                if not part or part.strip() == b'--' or part.strip() == b'':
                    continue

                if b'\r\n\r\n' not in part:
                    continue

                header_section, file_content = part.split(b'\r\n\r\n', 1)
                if file_content.endswith(b'\r\n'):
                    file_content = file_content[:-2]

                header_str = header_section.decode('utf-8', errors='replace')

                if 'name="targetPath"' in header_str:
                    target_path = file_content.decode('utf-8', errors='replace')
                elif 'name="file"' in header_str or 'filename=' in header_str:
                    for line in header_str.split('\r\n'):
                        if 'filename=' in line:
                            idx = line.index('filename=')
                            rest = line[idx + len('filename='):]
                            file_name = rest.strip('"').strip("'")
                            if file_name.startswith('"') or file_name.startswith("'"):
                                file_name = file_name[1:-1]
                            break
                    file_data = file_content

            if not file_data or not file_name:
                return {
                    'status': 400,
                    'body': {'success': False, 'message': 'No file provided'},
                    'headers': {'Content-Type': 'application/json'}
                }

            full_dir = self._get_full_path(target_path)
            if not os.path.exists(full_dir):
                os.makedirs(full_dir, exist_ok=True)

            file_path = os.path.join(full_dir, file_name)
            with open(file_path, 'wb') as f:
                f.write(file_data)

            return {
                'status': 200,
                'body': {'success': True, 'message': 'File uploaded', 'path': file_name},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('resources', 'edit')
    def rename_folder(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Rename a folder."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        old_path = data.get('oldPath', '')
        new_path = data.get('newPath', '')

        try:
            old_full = self._get_full_path(old_path)
            # newPath is just the new name, construct full path
            parent_dir = os.path.dirname(old_full)
            new_full = os.path.join(parent_dir, new_path)

            if not os.path.exists(old_full):
                return {
                    'status': 404,
                    'body': {'success': False, 'message': 'Folder not found'},
                    'headers': {'Content-Type': 'application/json'}
                }

            if os.path.exists(new_full):
                return {
                    'status': 409,
                    'body': {'success': False, 'message': 'Target folder already exists'},
                    'headers': {'Content-Type': 'application/json'}
                }

            os.rename(old_full, new_full)

            return {
                'status': 200,
                'body': {'success': True, 'message': 'Folder renamed'},
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'status': 500,
                'body': {'success': False, 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }
