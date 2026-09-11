# -*- coding: utf-8 -*-
"""验证数据库迁移结果"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, 'data', 'workbench.db')

def verify():
    print("=" * 60)
    print("验证数据库迁移结果")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"错误: 数据库文件不存在: {DB_PATH}")
        return

    print(f"数据库文件: {DB_PATH}")
    print(f"文件大小: {os.path.getsize(DB_PATH):,} bytes")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查各表记录数
    tables = ['projects', 'organizations', 'players', 'finances', 'users', 'settings', 'material_types', 'knowledge', 'notifications']

    print("\n表记录统计:")
    for table in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            print(f"  - {table}: {count}")
        except Exception as e:
            print(f"  - {table}: 错误 - {e}")

    # 检查数据版本
    cursor.execute('SELECT version, schema_version FROM data_version WHERE id = 1')
    row = cursor.fetchone()
    if row:
        print(f"\n数据版本: {row[0]}")
        print(f"Schema 版本: {row[1]}")

    # 检查一些示例数据
    print("\n示例数据:")

    # 项目示例
    cursor.execute('SELECT id, name, status FROM projects LIMIT 3')
    print("\n项目:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]} ({row[2]})")

    # 机构示例
    cursor.execute('SELECT id, name, type FROM organizations LIMIT 3')
    print("\n机构:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]} ({row[2]})")

    # 选手示例
    cursor.execute('SELECT id, name, category FROM players LIMIT 3')
    print("\n选手:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]} ({row[2]})")

    conn.close()
    print("\n✓ 验证完成!")

if __name__ == '__main__':
    verify()
