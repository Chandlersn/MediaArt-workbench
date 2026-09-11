# -*- coding: utf-8 -*-
"""
数据迁移脚本
支持 JSON 到 SQLite 的迁移、回滚和数据同步
"""

import os
import sys
import json
import shutil
from datetime import datetime
from typing import Dict, Optional, List

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.database import get_data_store, get_db

# 文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')
JSON_FILE = os.path.join(DATA_DIR, 'workbench_data.json')
DB_FILE = os.path.join(DATA_DIR, 'workbench.db')


class DataMigrator:
    """数据迁移器"""

    def __init__(self):
        self.data_store = get_data_store()
        self.db = self.data_store.db

    def check_json_exists(self) -> bool:
        """检查 JSON 数据文件是否存在"""
        return os.path.exists(JSON_FILE)

    def check_db_exists(self) -> bool:
        """检查数据库文件是否存在"""
        return os.path.exists(DB_FILE)

    def load_json_data(self) -> Optional[Dict]:
        """加载 JSON 数据"""
        try:
            if not self.check_json_exists():
                print(f"JSON 数据文件不存在: {JSON_FILE}")
                return None

            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            print(f"成功加载 JSON 数据: {JSON_FILE}")
            return data
        except Exception as e:
            print(f"加载 JSON 数据失败: {e}")
            return None

    def create_backup(self, prefix: str = 'migration') -> Optional[str]:
        """创建备份"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_name = f"{prefix}_{timestamp}"
            backup_path = os.path.join(BACKUP_DIR, backup_name)
            os.makedirs(backup_path, exist_ok=True)

            # 备份 JSON 文件
            if os.path.exists(JSON_FILE):
                shutil.copy2(JSON_FILE, os.path.join(backup_path, 'workbench_data.json'))
                print(f"已备份 JSON 文件到: {backup_path}")

            # 备份数据库文件
            if os.path.exists(DB_FILE):
                shutil.copy2(DB_FILE, os.path.join(backup_path, 'workbench.db'))
                print(f"已备份数据库文件到: {backup_path}")

            return backup_path
        except Exception as e:
            print(f"创建备份失败: {e}")
            return None

    def migrate_json_to_sqlite(self, create_backup: bool = True) -> bool:
        """将 JSON 数据迁移到 SQLite"""
        try:
            print("\n========== 开始 JSON 到 SQLite 迁移 ==========")

            # 检查 JSON 文件
            if not self.check_json_exists():
                print("错误: JSON 数据文件不存在")
                return False

            # 创建备份
            if create_backup:
                backup_path = self.create_backup('pre_migration')
                if not backup_path:
                    print("警告: 创建备份失败，继续迁移")

            # 加载 JSON 数据
            json_data = self.load_json_data()
            if not json_data:
                print("错误: 无法加载 JSON 数据")
                return False

            # 保存到数据库
            print("正在将数据写入 SQLite 数据库...")
            if self.data_store.save_all_data(json_data):
                print("✓ 数据迁移成功!")
                print(f"  - 项目数量: {len(json_data.get('projects', []))}")
                print(f"  - 机构数量: {len(json_data.get('organizations', []))}")
                print(f"  - 选手数量: {len(json_data.get('players', []))}")
                print(f"  - 财务记录: {len(json_data.get('finances', []))}")
                print(f"  - 用户数量: {len(json_data.get('users', []))}")
                return True
            else:
                print("✗ 数据迁移失败!")
                return False

        except Exception as e:
            print(f"迁移过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def export_sqlite_to_json(self, create_backup: bool = True) -> bool:
        """将 SQLite 数据导出到 JSON"""
        try:
            print("\n========== 开始 SQLite 到 JSON 导出 ==========")

            # 检查数据库文件
            if not self.check_db_exists():
                print("错误: 数据库文件不存在")
                return False

            # 创建备份
            if create_backup:
                backup_path = self.create_backup('pre_export')
                if not backup_path:
                    print("警告: 创建备份失败，继续导出")

            # 从数据库加载数据
            print("正在从 SQLite 数据库读取数据...")
            data = self.data_store.load_all_data()

            # 保存到 JSON 文件
            print(f"正在写入 JSON 文件: {JSON_FILE}")
            with open(JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print("✓ 数据导出成功!")
            print(f"  - 项目数量: {len(data.get('projects', []))}")
            print(f"  - 机构数量: {len(data.get('organizations', []))}")
            print(f"  - 选手数量: {len(data.get('players', []))}")
            print(f"  - 财务记录: {len(data.get('finances', []))}")
            print(f"  - 用户数量: {len(data.get('users', []))}")
            return True

        except Exception as e:
            print(f"导出过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def rollback_from_backup(self, backup_name: str) -> bool:
        """从备份恢复数据"""
        try:
            print(f"\n========== 从备份恢复: {backup_name} ==========")

            backup_path = os.path.join(BACKUP_DIR, backup_name)
            if not os.path.exists(backup_path):
                print(f"错误: 备份不存在: {backup_path}")
                return False

            # 恢复 JSON 文件
            json_backup = os.path.join(backup_path, 'workbench_data.json')
            if os.path.exists(json_backup):
                shutil.copy2(json_backup, JSON_FILE)
                print(f"✓ 已恢复 JSON 文件")

            # 恢复数据库文件
            db_backup = os.path.join(backup_path, 'workbench.db')
            if os.path.exists(db_backup):
                # 关闭数据库连接
                self.db.close_connection()
                shutil.copy2(db_backup, DB_FILE)
                print(f"✓ 已恢复数据库文件")

            print("✓ 数据恢复成功!")
            return True

        except Exception as e:
            print(f"恢复过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def verify_migration(self) -> bool:
        """验证迁移结果"""
        try:
            print("\n========== 验证迁移结果 ==========")

            # 加载 JSON 数据
            json_data = self.load_json_data()
            if not json_data:
                print("错误: 无法加载 JSON 数据")
                return False

            # 从数据库加载数据
            db_data = self.data_store.load_all_data()

            # 比较数据
            errors = []

            # 检查项目数量
            json_count = len(json_data.get('projects', []))
            db_count = len(db_data.get('projects', []))
            if json_count != db_count:
                errors.append(f"项目数量不匹配: JSON={json_count}, DB={db_count}")

            # 检查机构数量
            json_count = len(json_data.get('organizations', []))
            db_count = len(db_data.get('organizations', []))
            if json_count != db_count:
                errors.append(f"机构数量不匹配: JSON={json_count}, DB={db_count}")

            # 检查选手数量
            json_count = len(json_data.get('players', []))
            db_count = len(db_data.get('players', []))
            if json_count != db_count:
                errors.append(f"选手数量不匹配: JSON={json_count}, DB={db_count}")

            # 检查财务数量
            json_count = len(json_data.get('finances', []))
            db_count = len(db_data.get('finances', []))
            if json_count != db_count:
                errors.append(f"财务记录数量不匹配: JSON={json_count}, DB={db_count}")

            # 检查用户数量
            json_count = len(json_data.get('users', []))
            db_count = len(db_data.get('users', []))
            if json_count != db_count:
                errors.append(f"用户数量不匹配: JSON={json_count}, DB={db_count}")

            if errors:
                print("✗ 验证失败:")
                for error in errors:
                    print(f"  - {error}")
                return False
            else:
                print("✓ 验证通过! 数据迁移完整无误")
                return True

        except Exception as e:
            print(f"验证过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def list_backups(self):
        """列出所有备份"""
        print("\n========== 可用备份列表 ==========")

        if not os.path.exists(BACKUP_DIR):
            print("没有找到备份目录")
            return []

        backups = []
        for item in os.listdir(BACKUP_DIR):
            item_path = os.path.join(BACKUP_DIR, item)
            if os.path.isdir(item_path):
                has_json = os.path.exists(os.path.join(item_path, 'workbench_data.json'))
                has_db = os.path.exists(os.path.join(item_path, 'workbench.db'))
                backups.append({
                    'name': item,
                    'has_json': has_json,
                    'has_db': has_db
                })

        if not backups:
            print("没有找到备份")
            return []

        backups.sort(key=lambda x: x['name'], reverse=True)

        for backup in backups:
            files = []
            if backup['has_json']:
                files.append('JSON')
            if backup['has_db']:
                files.append('DB')
            print(f"  - {backup['name']} ({', '.join(files)})")

        return backups

    def get_migration_status(self) -> Dict:
        """获取迁移状态"""
        status = {
            'json_exists': self.check_json_exists(),
            'db_exists': self.check_db_exists(),
            'json_records': 0,
            'db_records': 0,
            'needs_migration': False,
            'recommendation': ''
        }

        # 统计 JSON 记录数
        if status['json_exists']:
            json_data = self.load_json_data()
            if json_data:
                status['json_records'] = (
                    len(json_data.get('projects', [])) +
                    len(json_data.get('organizations', [])) +
                    len(json_data.get('players', [])) +
                    len(json_data.get('finances', [])) +
                    len(json_data.get('users', []))
                )

        # 统计数据库记录数
        if status['db_exists']:
            try:
                db_data = self.data_store.load_all_data()
                status['db_records'] = (
                    len(db_data.get('projects', [])) +
                    len(db_data.get('organizations', [])) +
                    len(db_data.get('players', [])) +
                    len(db_data.get('finances', [])) +
                    len(db_data.get('users', []))
                )
            except:
                pass

        # 判断是否需要迁移
        if status['json_exists'] and not status['db_exists']:
            status['needs_migration'] = True
            status['recommendation'] = '建议执行 JSON 到 SQLite 迁移'
        elif status['json_exists'] and status['db_exists']:
            if status['json_records'] > status['db_records']:
                status['needs_migration'] = True
                status['recommendation'] = 'JSON 数据较新，建议重新迁移'
            else:
                status['recommendation'] = '数据库已存在，无需迁移'
        elif not status['json_exists'] and status['db_exists']:
            status['recommendation'] = '仅数据库存在，可导出到 JSON'
        else:
            status['recommendation'] = '没有找到数据文件'

        return status


def main():
    """主函数"""
    print("=" * 60)
    print("媒体艺术展览工作台 - 数据迁移工具")
    print("=" * 60)

    migrator = DataMigrator()

    # 显示迁移状态
    status = migrator.get_migration_status()
    print("\n当前状态:")
    print(f"  JSON 文件: {'存在' if status['json_exists'] else '不存在'}")
    print(f"  数据库文件: {'存在' if status['db_exists'] else '不存在'}")
    print(f"  JSON 记录数: {status['json_records']}")
    print(f"  数据库记录数: {status['db_records']}")
    print(f"  建议: {status['recommendation']}")

    # 交互式菜单
    while True:
        print("\n" + "=" * 60)
        print("请选择操作:")
        print("  1. 执行 JSON 到 SQLite 迁移")
        print("  2. 导出 SQLite 到 JSON")
        print("  3. 验证迁移结果")
        print("  4. 列出所有备份")
        print("  5. 从备份恢复")
        print("  6. 查看迁移状态")
        print("  0. 退出")
        print("=" * 60)

        choice = input("请输入选项 (0-6): ").strip()

        if choice == '1':
            confirm = input("确认执行迁移? (y/n): ").strip().lower()
            if confirm == 'y':
                migrator.migrate_json_to_sqlite(create_backup=True)
        elif choice == '2':
            confirm = input("确认导出到 JSON? (y/n): ").strip().lower()
            if confirm == 'y':
                migrator.export_sqlite_to_json(create_backup=True)
        elif choice == '3':
            migrator.verify_migration()
        elif choice == '4':
            migrator.list_backups()
        elif choice == '5':
            backups = migrator.list_backups()
            if backups:
                backup_name = input("请输入备份名称: ").strip()
                if backup_name:
                    confirm = input(f"确认从 {backup_name} 恢复? (y/n): ").strip().lower()
                    if confirm == 'y':
                        migrator.rollback_from_backup(backup_name)
        elif choice == '6':
            status = migrator.get_migration_status()
            print("\n当前状态:")
            print(f"  JSON 文件: {'存在' if status['json_exists'] else '不存在'}")
            print(f"  数据库文件: {'存在' if status['db_exists'] else '不存在'}")
            print(f"  JSON 记录数: {status['json_records']}")
            print(f"  数据库记录数: {status['db_records']}")
            print(f"  建议: {status['recommendation']}")
        elif choice == '0':
            print("\n再见!")
            break
        else:
            print("无效选项，请重新选择")


if __name__ == '__main__':
    main()
