# -*- coding: utf-8 -*-
"""
自动数据迁移脚本
自动将 JSON 数据迁移到 SQLite 数据库
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.database import get_data_store

# 文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
JSON_FILE = os.path.join(DATA_DIR, 'workbench_data.json')

def auto_migrate():
    """自动执行迁移"""
    import json
    
    print("=" * 60)
    print("自动数据迁移")
    print("=" * 60)
    
    # 检查 JSON 文件
    if not os.path.exists(JSON_FILE):
        print(f"错误: JSON 文件不存在: {JSON_FILE}")
        return False
    
    # 加载 JSON 数据
    print(f"正在加载 JSON 数据: {JSON_FILE}")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    print(f"加载成功:")
    print(f"  - 项目数量: {len(json_data.get('projects', []))}")
    print(f"  - 机构数量: {len(json_data.get('organizations', []))}")
    print(f"  - 选手数量: {len(json_data.get('players', []))}")
    print(f"  - 财务记录: {len(json_data.get('finances', []))}")
    print(f"  - 用户数量: {len(json_data.get('users', []))}")
    
    # 保存到数据库
    print("\n正在保存到 SQLite 数据库...")
    data_store = get_data_store()
    if data_store.save_all_data(json_data):
        print("\n✓ 数据迁移成功!")
        return True
    else:
        print("\n✗ 数据迁移失败!")
        return False

if __name__ == '__main__':
    success = auto_migrate()
    sys.exit(0 if success else 1)
