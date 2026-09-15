"""启动期维护：数据库完整性自检 + 备份轮转。

背景：
- 本项目曾出现过 `workbench.db` 损坏，直到启动时报错才发现，缺乏主动体检；
- `data/backup` 的自动备份长期只增不减（一度 143 份 / 124MB），既占空间，
  也让「该恢复哪一份」难以判断。

这里把两件事收进启动流程：先体检、再按需轮转。两件事都只做只读/清理，出错不阻断启动。
"""

import os
import re
import shutil
import logging

logger = logging.getLogger(__name__)

# 自动备份目录名形如 2026-09-11_18-49 或 2026-05-02_14-03-21（秒可选）
# 带前缀的（如 migration_xxx）是迁移快照，不在自动轮转范围内，避免误删
_AUTO_BACKUP_NAME = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}(?:-\d{2})?$')


def check_db_integrity(db_path):
    """对 SQLite 做完整性自检。

    @return: (是否完好, 结果摘要)
    """
    if not db_path or not os.path.isfile(db_path):
        return False, f'数据库文件不存在: {db_path}'
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute('PRAGMA integrity_check').fetchone()
            result = row[0] if row else 'unknown'
        finally:
            conn.close()
        ok = str(result).strip().lower() == 'ok'
        return ok, result
    except Exception as e:
        return False, f'自检失败: {e}'


def rotate_backups(backup_dir, keep=20):
    """只保留最新的 keep 份自动备份，其余删除。

    仅处理纯时间戳命名的目录；带前缀的（migration_* 等）一律保留。
    时间戳为 `YYYY-MM-DD_HH-MM(-SS)`，字典序即时间序，直接按名倒序即可取最新。

    @return: 被删除的份数
    """
    if not backup_dir or not os.path.isdir(backup_dir) or keep < 0:
        return 0
    try:
        names = [d for d in os.listdir(backup_dir)
                 if _AUTO_BACKUP_NAME.match(d) and os.path.isdir(os.path.join(backup_dir, d))]
    except OSError as e:
        logger.warning(f"读取备份目录失败: {e}")
        return 0

    names.sort(reverse=True)
    removed = 0
    for name in names[keep:]:
        shutil.rmtree(os.path.join(backup_dir, name), ignore_errors=True)
        if not os.path.exists(os.path.join(backup_dir, name)):
            removed += 1
    return removed
