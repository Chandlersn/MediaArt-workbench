"""
回收站（软删除）工具。

把用户删除的文件 / 目录移动到 ``data/.trash``，并写入 ``.meta.json`` 记录原始路径，
支持列出、恢复、彻底清除。对应「删除无回收站」问题：原本 archive / materials /
resources 路由直接 ``os.remove``，误删即永久丢失；改为先入回收站，可恢复。

注意：
- 临时目录（data/temp）的过期清理不属于用户数据，仍走硬删，不进回收站。
- 恢复时若目标已存在则拒绝，避免覆盖当前文件。
"""
import os
import json
import time
import shutil
import uuid
import logging

from server.config import BASE_DIR

logger = logging.getLogger(__name__)

TRASH_DIR = os.path.join(BASE_DIR, 'data', '.trash')


def _ensure() -> None:
    os.makedirs(TRASH_DIR, exist_ok=True)


def _safe_name(name: str) -> str:
    """生成可作为目录名的安全片段（保留可读性，去掉路径分隔符等）。"""
    base = os.path.basename(name) or 'untitled'
    out = []
    for ch in base:
        if ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
            out.append('_')
        else:
            out.append(ch)
    return ''.join(out)[:120] or 'untitled'


def _size(p: str) -> int:
    if os.path.isfile(p):
        try:
            return os.path.getsize(p)
        except OSError:
            return 0
    total = 0
    for r, _, fs in os.walk(p):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def send_to_trash(src_path: str):
    """把 ``src_path`` 移动到回收站，返回 trash id（目录名）；源不存在返回 None。"""
    if not src_path or not os.path.exists(src_path):
        return None
    _ensure()
    ts = time.strftime('%Y%m%d_%H%M%S')
    stem = _safe_name(src_path)
    while True:
        rid = f'{ts}__{uuid.uuid4().hex[:8]}__{stem}'
        dest = os.path.join(TRASH_DIR, rid)
        if not os.path.exists(dest):
            break
    meta = {
        'id': rid,
        'original_path': os.path.abspath(src_path),
        'deleted_at': int(time.time()),
        'type': 'dir' if os.path.isdir(src_path) else 'file',
        'name': os.path.basename(src_path) or src_path,
    }
    try:
        shutil.move(src_path, dest)
    except Exception as e:  # pragma: no cover - 移动失败交由调用方决定
        logger.error(f'移入回收站失败 {src_path}: {e}')
        return None
    try:
        with open(os.path.join(TRASH_DIR, rid + '.meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f'写回收站元信息失败 {rid}: {e}')
    return rid


def list_trash() -> list:
    """返回回收站条目列表（按删除时间倒序）。"""
    _ensure()
    items = []
    for name in os.listdir(TRASH_DIR):
        if not name.endswith('.meta.json'):
            continue
        rid = name[:-len('.meta.json')]
        item_path = os.path.join(TRASH_DIR, rid)
        try:
            with open(os.path.join(TRASH_DIR, name), encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            meta = {'id': rid, 'name': rid}
        meta['exists'] = os.path.exists(item_path)
        meta['size'] = _size(item_path) if meta['exists'] else 0
        items.append(meta)
    items.sort(key=lambda m: m.get('deleted_at', 0), reverse=True)
    return items


def restore_trash(rid: str):
    """恢复到原始路径。返回 (ok: bool, message: str)。"""
    if not rid:
        return False, '缺少回收项 id'
    meta_p = os.path.join(TRASH_DIR, rid + '.meta.json')
    item_p = os.path.join(TRASH_DIR, rid)
    if not os.path.exists(meta_p) or not os.path.exists(item_p):
        return False, '回收项不存在或已清除'
    try:
        with open(meta_p, encoding='utf-8') as f:
            meta = json.load(f)
    except Exception as e:
        return False, f'元信息损坏: {e}'
    dest = meta.get('original_path')
    if not dest:
        return False, '原始路径缺失'
    try:
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.exists(dest):
            return False, f'目标已存在，拒绝覆盖: {dest}'
        shutil.move(item_p, dest)
        try:
            os.remove(meta_p)
        except OSError:
            pass
        return True, dest
    except Exception as e:
        return False, str(e)


def purge_trash(rid: str) -> bool:
    """彻底删除单个回收项（文件 + 元信息）。"""
    if not rid:
        return False
    item_p = os.path.join(TRASH_DIR, rid)
    meta_p = os.path.join(TRASH_DIR, rid + '.meta.json')
    removed = False
    if os.path.exists(item_p):
        if os.path.isdir(item_p):
            shutil.rmtree(item_p, ignore_errors=True)
        else:
            try:
                os.remove(item_p)
            except OSError:
                pass
        removed = True
    if os.path.exists(meta_p):
        try:
            os.remove(meta_p)
        except OSError:
            pass
        removed = True
    return removed


def purge_all() -> int:
    """清空整个回收站，返回清除条目数。"""
    _ensure()
    n = 0
    for name in os.listdir(TRASH_DIR):
        p = os.path.join(TRASH_DIR, name)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            n += 1
        except OSError:
            pass
    return n
