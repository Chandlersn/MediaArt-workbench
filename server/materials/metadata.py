"""Exact material classification, separate from the coarser archive folders.

The index belongs to this deployment's files, not the editable business snapshot.
Keys are relative to the archive/trash roots and never contain machine paths.
"""
import json
import os
import tempfile
import threading

from server.config import BASE_DIR

INDEX_PATH = os.path.join(BASE_DIR, 'data', 'material_metadata.json')
_LOCK = threading.RLock()


def _path_key(path):
    from server.resources.routes import get_archives_dir
    candidate = os.path.normcase(os.path.abspath(path))
    for prefix, directory in (
        ('archive', get_archives_dir()),
        ('trash', os.path.join(BASE_DIR, 'data', '.trash')),
    ):
        root = os.path.normcase(os.path.abspath(directory))
        try:
            if os.path.commonpath([candidate, root]) == root:
                relative = os.path.relpath(candidate, root).replace('\\', '/')
                return f'{prefix}/{relative}'
        except ValueError:
            pass
    return None


def _read_index():
    try:
        with open(INDEX_PATH, encoding='utf-8') as stream:
            entries = json.load(stream)
    except FileNotFoundError:
        return {}
    if not isinstance(entries, dict):
        raise ValueError('Invalid material metadata index')
    return entries


def _write_index(entries):
    directory = os.path.dirname(INDEX_PATH)
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.material-metadata-', delete=False) as stream:
            temporary = stream.name
            json.dump(entries, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, INDEX_PATH)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def load_metadata():
    with _LOCK:
        return _read_index()


def get_metadata(path, entries=None):
    key = _path_key(path)
    if key is None:
        return None
    record = (load_metadata() if entries is None else entries).get(key)
    if not isinstance(record, dict):
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    # A replacement written outside the uploader must not inherit old labels.
    if record.get('size') != stat.st_size or record.get('mtime_ns') != stat.st_mtime_ns:
        return None
    return record


def store_material_file(directory, filename, content, material_type, stage=''):
    """Create distinct bytes + classification, or roll back the newly made file."""
    if filename != os.path.basename(filename) or _path_key(directory) is None:
        raise ValueError('Invalid material destination')
    with _LOCK:
        entries = _read_index()
        os.makedirs(directory, exist_ok=True)
        stem, extension = os.path.splitext(filename)
        suffix = 1
        while True:
            chosen = filename if suffix == 1 else f'{stem}_{suffix}{extension}'
            path = os.path.join(directory, chosen)
            try:
                stream = open(path, 'xb')
                break
            except FileExistsError:
                suffix += 1
        try:
            with stream:
                stream.write(content)
            stat = os.stat(path)
            entries[_path_key(path)] = {
                'type': material_type, 'stage': stage,
                'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            }
            _write_index(entries)
        except Exception:
            os.remove(path)
            raise
        return chosen


def move_metadata(old_path, new_path):
    """Follow a file or directory rename, including recycle-bin round trips."""
    old_key, new_key = _path_key(old_path), _path_key(new_path)
    if old_key is None or old_key == new_key:
        return
    with _LOCK:
        entries = _read_index()
        matched = [key for key in entries if key == old_key or key.startswith(old_key + '/')]
        if not matched:
            return
        if new_key is None:
            raise ValueError('Material metadata destination is outside archive/trash')
        for key in matched:
            entries[new_key + key[len(old_key):]] = entries.pop(key)
        _write_index(entries)


def remove_metadata(path):
    key = _path_key(path)
    if key is None:
        return
    with _LOCK:
        entries = _read_index()
        remaining = {name: value for name, value in entries.items()
                     if name != key and not name.startswith(key + '/')}
        if len(remaining) != len(entries):
            _write_index(remaining)
