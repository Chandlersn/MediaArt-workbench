#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""初始化管理员账号（全新部署必跑一次）。

背景：
    全新 clone 后数据库是空的，而 /api/auth/register 要求「已登录 + users:edit
    权限」才能调用，因此没有任何账号能登录、也无法注册，系统处于死锁状态。
    本脚本用于创建第一个管理员账号，打破这个死锁。

用法：
    python scripts/init_admin.py                      # 创建 admin，密码随机生成
    python scripts/init_admin.py myadmin              # 指定用户名，密码随机生成
    python scripts/init_admin.py myadmin mypassword   # 指定用户名与密码
    python scripts/init_admin.py --force              # 账号已存在时强制重置密码

说明：
    - 密码使用 bcrypt 加盐哈希，与后端登录校验方式一致，不存明文。
    - 随机密码会打印到终端，并写入 data/initial_password.txt
      （data/ 已在 .gitignore 中，不会进仓库）。
    - 重复运行且账号已存在时，默认不改动、直接提示，避免误重置线上密码；
      需要重置请显式加 --force。
"""

import os
import sys
import uuid
import secrets

# 保证可以从项目任意位置运行：把项目根目录加入模块搜索路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
INITIAL_PASSWORD_FILE = os.path.join(DATA_DIR, 'initial_password.txt')

MIN_PASSWORD_LENGTH = 8


def parse_args(argv):
    """解析命令行参数，返回 (用户名, 密码, 是否强制重置)。"""
    force = '--force' in argv
    positional = [a for a in argv if not a.startswith('--')]
    username = positional[0] if len(positional) >= 1 else 'admin'
    password = positional[1] if len(positional) >= 2 else None
    return username, password, force


def generate_password():
    """生成随机初始密码。"""
    return secrets.token_urlsafe(12)


def save_initial_password(username, password):
    """把随机密码落盘，方便首次部署时查阅（data/ 不进仓库）。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(INITIAL_PASSWORD_FILE, 'w', encoding='utf-8') as f:
            f.write(f'username: {username}\npassword: {password}\n')
        return True
    except OSError as e:
        print(f'警告：初始密码未能写入 {INITIAL_PASSWORD_FILE}（{e}）')
        return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    username, password, force = parse_args(argv)

    try:
        import bcrypt
        from server.database.store import data_store
    except ImportError as e:
        print(f'错误：缺少依赖或模块无法导入（{e}）')
        print('请先执行：pip install -r requirements.txt')
        return 1

    # 已存在同名账号：默认不改，避免误伤
    existing = data_store.users.find_one('username = ?', (username,))
    if existing and not force:
        print(f'账号 "{username}" 已存在（角色：{existing.get("role", "unknown")}），未做任何改动。')
        print('如需重置密码，请加 --force 重新运行。')
        return 0

    if password is None:
        password = generate_password()
        is_generated = True
    else:
        is_generated = False
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f'错误：密码至少需要 {MIN_PASSWORD_LENGTH} 位。')
            return 1

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    if existing and force:
        data_store.users.update(
            existing.get('id'),
            {'password': hashed},
        )
        action = '已重置密码'
    else:
        data_store.users.create({
            'id': str(uuid.uuid4()),
            'username': username,
            'password': hashed,
            'real_name': username,
            'role': 'admin',
        })
        action = '已创建管理员'

    print(f'{action}：{username}')
    if is_generated:
        print(f'初始密码：{password}')
        if save_initial_password(username, password):
            print(f'已同时写入：{INITIAL_PASSWORD_FILE}')
        print('请登录后立即修改密码。')
    else:
        print('请妥善保管你指定的密码。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
