"""启动期维护：数据库完整性自检 + 每日自动备份 + 备份轮转。

背景：
- 本项目曾出现过 `workbench.db` 损坏，直到启动时报错才发现，缺乏主动体检；
- `data/backup` 的自动备份长期只增不减（一度 143 份 / 124MB），既占空间，
  也让「该恢复哪一份」难以判断；
- **`rotate_backups` 只删旧的、从不创建，手动备份又要用户自己点** ——
  结果是 `data/backup` 可能长期为空，本地单机一旦数据库损坏就无从恢复。
  所以补上 `ensure_daily_backup`（每日一份）。

这里把三件事收进启动流程：先体检、再备份、最后按需轮转。任一步出错都不阻断启动。
"""

import os
import re
import json
import shutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 备份目录名形如 2026-09-11_18-49 或 2026-05-02_14-03-21（秒可选）
# 带前缀的（如 migration_xxx）是迁移快照，不在自动轮转范围内，避免误删
#
# 这里区分两种备份：
#   _ANY_BACKUP_NAME  全部备份（自动 + 手动）—— 用于「今天是否已有备份」判断
#   _AUTO_BACKUP_NAME 仅自动备份（纯时间戳，无 uuid）—— **只有这类才参与轮转**
#
# 为什么手动备份不轮转：手动备份是用户主动创建的（通常在重要操作前），
# 被自动轮转删掉会让他在真正需要时找不到 —— 而每份只有几十 KB、创建频率也低，
# 不构成空间问题。
_ANY_BACKUP_NAME = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}(?:-\d{2})?(?:_[0-9a-f]{8})?$')
_AUTO_BACKUP_NAME = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}(?:-\d{2})?$')

# 内存缓存：今天是否已经处理过自动备份，避免每次保存都去列目录
_LAST_AUTO_BACKUP_DAY = None


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


def is_auto_backup(name):
    """该备份目录名是否为自动备份（纯时间戳，无 uuid）。

    自动备份由系统每日创建、受 keep=20 的保留策略约束；
    手动备份（用户主动创建）不参与轮转，一律保留。
    """
    return bool(_AUTO_BACKUP_NAME.match(name or ''))


def has_backup_for_day(backup_dir, day):
    """备份目录里是否已有指定日期的备份（自动或手动都算）。"""
    if not backup_dir or not os.path.isdir(backup_dir):
        return False
    try:
        for name in os.listdir(backup_dir):
            if name.startswith(day + '_') and _ANY_BACKUP_NAME.match(name):
                return True
    except OSError:
        return False
    return False


def ensure_daily_backup(backup_dir, payload_provider, keep=20, force=False):
    """每天创建一份自动备份（当天已有则跳过）。

    命名用**纯时间戳**（`YYYY-MM-DD_HH-MM`）：既落在 `rotate_backups` 的保留策略里，
    也与手动备份（时间戳 + uuid）区分得开。

    调用点有两个：启动时、以及每天首次保存后 —— 这样即便后端长期不重启，
    跨天之后也会自动补一份。

    @param payload_provider: 无参函数，返回要备份的数据。**延迟调用** ——
                             只在确实要写备份时才去读库，平时不产生开销。
    @return: 备份目录名；未创建时返回 None
    """
    global _LAST_AUTO_BACKUP_DAY
    if not backup_dir:
        return None

    day = datetime.now().strftime('%Y-%m-%d')
    if not force and _LAST_AUTO_BACKUP_DAY == day:
        return None

    try:
        if has_backup_for_day(backup_dir, day):
            _LAST_AUTO_BACKUP_DAY = day
            return None

        os.makedirs(backup_dir, exist_ok=True)
        name = datetime.now().strftime('%Y-%m-%d_%H-%M')
        target = os.path.join(backup_dir, name)
        os.makedirs(target, exist_ok=True)

        payload = payload_provider()
        with open(os.path.join(target, 'workbench_data.json'), 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        _LAST_AUTO_BACKUP_DAY = day
        removed = rotate_backups(backup_dir, keep=keep)
        logger.info(f"已创建每日自动备份 {name}"
                    + (f"（轮转删除 {removed} 份旧备份）" if removed else ""))
        return name
    except Exception as e:
        # 备份失败绝不能影响主流程（保存 / 启动）
        logger.warning(f"创建每日自动备份失败（不影响使用）: {e}")
        return None


def rotate_backups(backup_dir, keep=20):
    """只保留最新的 keep 份**自动**备份，其余删除。

    ⚠️ **手动备份（带 uuid 的那种）不参与轮转，一律保留** ——
    那是用户主动创建的（通常在重要操作前），被自动清理掉会让他在真正需要时找不到。
    带前缀的（migration_* 等）迁移快照同样保留。

    自动备份名为纯时间戳 `YYYY-MM-DD_HH-MM(-SS)`，字典序即时间序，
    直接按名倒序即可取最新。

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
