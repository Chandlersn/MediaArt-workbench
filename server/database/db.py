# -*- coding: utf-8 -*-
"""
SQLite 数据库连接与 ORM 模块
提供数据库连接、事务管理和基础 CRUD 操作
"""

import os
import json
import hashlib
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 数据库文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_FILE = os.path.join(DATA_DIR, 'workbench.db')
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), 'schema.sql')

# 线程本地存储，用于多线程环境
_local = threading.local()

# HTTP routes and backup restoration share this definition. Authentication and
# permissions remain the responsibility of the caller.
WRITABLE_SECTIONS = frozenset({
    'projects', 'organizations', 'players', 'finances', 'users', 'config',
    'materialTypes', 'knowledge', 'notifications', 'templates', 'auditLogs',
    'checklistState', 'checklists', 'certificates', 'certSettings',
    'printTemplates', 'projectChecklists', 'archiveConfig', 'archiveMappings',
})
CONFIG_KEYS = frozenset({
    'stages', 'projectTypes', 'orgTypes', 'statusList', 'financeTypes',
    'incomeCategories', 'expenseCategories', 'stageMaterials', 'resourceCategories',
})


class SnapshotConflictError(Exception):
    """The caller edited a section that has changed since it was loaded."""

    def __init__(self, sections):
        self.sections = sorted(sections)
        super().__init__('数据已被其他操作修改，请重新加载：' + ', '.join(self.sections))


class Database:
    """SQLite 数据库管理类"""

    def __init__(self, db_path: str = None):
        self.db_path = os.path.abspath(db_path or DB_FILE)
        self._connection_key = os.path.normcase(os.path.realpath(self.db_path))
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_db(self):
        """初始化数据库表结构

        关键修复：无论数据库文件是否存在，每次启动都执行 schema.sql。
        schema.sql 全部使用 CREATE TABLE IF NOT EXISTS / INSERT OR IGNORE，
        对既有数据库是幂等且安全的。这样后来新增的表（如 certificates）也能
        在旧库上自动补齐，无需删库重建——否则旧库永远缺新表，对应数据只写
        JSON 备份、SQLite 读取为空，表现为「导入后刷新就消失」。
        """
        self._create_tables()

    def _create_tables(self):
        """创建数据库表"""
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        self.execute_script(schema_sql)
        print(f"数据库表结构已创建: {self.db_path}")

    def execute_script(self, script):
        """执行建表脚本而不触发 sqlite3.executescript 的隐式提交。"""
        with self.transaction() as conn:
            start = 0
            for index, character in enumerate(script):
                if character == ';' and sqlite3.complete_statement(script[start:index + 1]):
                    conn.execute(script[start:index + 1])
                    start = index + 1
            if script[start:].strip():
                conn.execute(script[start:])

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（线程安全）"""
        if not hasattr(_local, 'connections'):
            _local.connections = {}
        if self._connection_key not in _local.connections:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row  # 使用 Row 工厂，支持字典式访问
            conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
            conn.execute("PRAGMA journal_mode = WAL")  # 使用 WAL 模式提高并发性能
            _local.connections[self._connection_key] = conn
        return _local.connections[self._connection_key]

    def close_connection(self):
        """关闭数据库连接"""
        conn = getattr(_local, 'connections', {}).pop(self._connection_key, None)
        if conn is not None:
            conn.close()

    @contextmanager
    def transaction(self, immediate=False):
        """事务上下文管理器"""
        conn = self.get_connection()
        savepoint = 'sp_' + uuid.uuid4().hex if conn.in_transaction else None
        try:
            if savepoint:
                conn.execute(f'SAVEPOINT {savepoint}')
            else:
                conn.execute('BEGIN IMMEDIATE' if immediate else 'BEGIN')
            yield conn
            if savepoint:
                conn.execute(f'RELEASE SAVEPOINT {savepoint}')
            else:
                conn.commit()
        except Exception:
            if savepoint and conn.in_transaction:
                conn.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
                conn.execute(f'RELEASE SAVEPOINT {savepoint}')
            elif not savepoint:
                conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL 语句（**不自动提交**）。

        ⚠️ 写操作（INSERT/UPDATE/DELETE）请改用：
            with data_store.db.transaction() as conn:
                conn.execute(sql, params)
        本方法不 commit，且连接是线程本地（每请求独立），裸写会「执行成功但不落库」，
        并随线程结束被回滚 —— 审计日志 / 通知曾因此静默丢失。仅适合读或已在外层事务内。
        """
        conn = self.get_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: List[tuple]) -> sqlite3.Cursor:
        """批量执行 SQL 语句"""
        conn = self.get_connection()
        return conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> List[Dict]:
        """查询多条记录"""
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetchval(self, sql: str, params: tuple = ()) -> Any:
        """查询单个值"""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else None


class Model:
    """基础模型类，提供 CRUD 操作"""

    table_name: str = ''
    primary_key: str = 'id'

    def __init__(self, db: Database = None):
        self.db = db or Database()

    def _serialize(self, data: Dict) -> Dict:
        """序列化数据（将字典/列表转为 JSON 字符串）"""
        serialized = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value, ensure_ascii=False)
            else:
                serialized[key] = value
        return serialized

    def _deserialize(self, data: Dict) -> Dict:
        """反序列化数据（将 JSON 字符串转为字典/列表）"""
        deserialized = {}
        for key, value in data.items():
            if isinstance(value, str) and value:
                if value.startswith(('[', '{')):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, (dict, list)):
                            deserialized[key] = parsed
                        else:
                            deserialized[key] = value
                    except json.JSONDecodeError:
                        deserialized[key] = value
                else:
                    deserialized[key] = value
            else:
                deserialized[key] = value
        return deserialized

    def _to_db_field(self, field: str) -> str:
        """将驼峰命名转换为下划线命名"""
        import re
        return re.sub(r'([A-Z])', r'_\1', field).lower()

    def _from_db_field(self, field: str) -> str:
        """将下划线命名转换为驼峰命名"""
        parts = field.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])

    def _convert_to_db(self, data: Dict) -> Dict:
        """将数据字段名转换为数据库字段名"""
        return {self._to_db_field(k): v for k, v in data.items()}

    def _convert_from_db(self, data: Dict) -> Dict:
        """将数据库字段名转换为数据字段名"""
        return {self._from_db_field(k): v for k, v in data.items()}

    def _new_id(self) -> str:
        """生成主键：<表名前两位小写><10 位十六进制>，如 players -> pl3f9a2b1c4d。"""
        import uuid
        prefix = ''.join(c for c in self.table_name if c.isalpha())[:2].lower() or 'id'
        return f'{prefix}{uuid.uuid4().hex[:10]}'

    def create(self, data: Dict) -> str:
        """创建记录

        ⚠️ 业务表的 id 是 `TEXT PRIMARY KEY`、**没有 AUTOINCREMENT**：调用方不带 id
        时必须在此生成，否则会写入 NULL 主键 —— 记录之后既查不到也改不了、删不掉
        （曾经 players / organizations 的 create 接口就踩过这个坑）。
        """
        data = dict(data or {})
        if self.primary_key == 'id' and not data.get('id'):
            data['id'] = self._new_id()
        data = self._convert_to_db(data)
        data = self._serialize(data)

        # 添加时间戳
        if 'created_at' not in data:
            data['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if 'updated_at' not in data:
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        fields = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO {self.table_name} ({fields}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(sql, tuple(data.values()))

        return data.get(self.primary_key)

    def get_by_id(self, id: str) -> Optional[Dict]:
        """根据 ID 查询记录"""
        sql = f"SELECT * FROM {self.table_name} WHERE {self.primary_key} = ?"
        row = self.db.fetchone(sql, (id,))
        if row:
            row = self._convert_from_db(row)
            row = self._deserialize(row)
        return row

    def get_all(self, order_by: str = None, limit: int = None, offset: int = None) -> List[Dict]:
        """查询所有记录"""
        sql = f"SELECT * FROM {self.table_name}"

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit:
            sql += f" LIMIT {limit}"
            if offset:
                sql += f" OFFSET {offset}"

        rows = self.db.fetchall(sql)
        return [self._deserialize(self._convert_from_db(row)) for row in rows]

    def find(self, where: str = '', params: tuple = (), order_by: str = None,
             limit: int = None, offset: int = None) -> List[Dict]:
        """条件查询"""
        sql = f"SELECT * FROM {self.table_name}"

        if where:
            sql += f" WHERE {where}"

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit:
            sql += f" LIMIT {limit}"
            if offset:
                sql += f" OFFSET {offset}"

        rows = self.db.fetchall(sql, params)
        return [self._deserialize(self._convert_from_db(row)) for row in rows]

    def find_one(self, where: str, params: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        sql = f"SELECT * FROM {self.table_name} WHERE {where} LIMIT 1"
        row = self.db.fetchone(sql, params)
        if row:
            row = self._convert_from_db(row)
            row = self._deserialize(row)
        return row

    def update(self, id: str, data: Dict) -> bool:
        """更新记录"""
        data = self._convert_to_db(data)
        data = self._serialize(data)

        # 更新时间戳
        data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        fields = ', '.join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {self.table_name} SET {fields} WHERE {self.primary_key} = ?"

        with self.db.transaction() as conn:
            cursor = conn.execute(sql, tuple(data.values()) + (id,))
            return cursor.rowcount > 0

    def delete(self, id: str) -> bool:
        """删除记录"""
        sql = f"DELETE FROM {self.table_name} WHERE {self.primary_key} = ?"

        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (id,))
            return cursor.rowcount > 0

    def count(self, where: str = '', params: tuple = ()) -> int:
        """统计记录数"""
        sql = f"SELECT COUNT(*) FROM {self.table_name}"

        if where:
            sql += f" WHERE {where}"

        return self.db.fetchval(sql, params)

    def exists(self, id: str) -> bool:
        """检查记录是否存在"""
        sql = f"SELECT 1 FROM {self.table_name} WHERE {self.primary_key} = ? LIMIT 1"
        return self.db.fetchval(sql, (id,)) is not None


# ========== 具体模型类 ==========

class ProjectModel(Model):
    """项目模型"""
    table_name = 'projects'
    primary_key = 'id'


class OrganizationModel(Model):
    """机构模型"""
    table_name = 'organizations'
    primary_key = 'id'


class PlayerModel(Model):
    """选手模型"""
    table_name = 'players'
    primary_key = 'id'


class FinanceModel(Model):
    """财务模型"""
    table_name = 'finances'
    primary_key = 'id'


class CertificateModel(Model):
    """证书模型"""
    table_name = 'certificates'
    primary_key = 'cert_number'


class UserModel(Model):
    """用户模型"""
    table_name = 'users'
    primary_key = 'id'


class SettingsModel(Model):
    """配置模型"""
    table_name = 'settings'
    primary_key = 'key'


class MaterialTypeModel(Model):
    """资料类型模型"""
    table_name = 'material_types'
    primary_key = 'id'


class KnowledgeModel(Model):
    """知识库模型"""
    table_name = 'knowledge'
    primary_key = 'id'


class NotificationModel(Model):
    """通知模型"""
    table_name = 'notifications'
    primary_key = 'id'


class AuditLogModel(Model):
    """审计日志模型"""
    table_name = 'audit_logs'
    primary_key = 'id'


class TemplateModel(Model):
    """模板模型"""
    table_name = 'templates'
    primary_key = 'id'


class ChecklistModel(Model):
    """清单模型"""
    table_name = 'checklists'
    primary_key = 'id'


class ChecklistStateModel(Model):
    """清单状态模型"""
    table_name = 'checklist_states'
    primary_key = 'id'


# ========== 数据访问层 ==========

class DataStore:
    """数据访问层，提供统一的数据操作接口"""

    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.projects = ProjectModel(self.db)
        self.organizations = OrganizationModel(self.db)
        self.players = PlayerModel(self.db)
        self.finances = FinanceModel(self.db)
        self.users = UserModel(self.db)
        self.settings = SettingsModel(self.db)
        self.material_types = MaterialTypeModel(self.db)
        self.knowledge = KnowledgeModel(self.db)
        self.notifications = NotificationModel(self.db)
        self.audit_logs = AuditLogModel(self.db)
        self.templates = TemplateModel(self.db)
        self.checklists = ChecklistModel(self.db)
        self.checklist_states = ChecklistStateModel(self.db)
        self.certificates = CertificateModel(self.db)
        self._ensure_certificates_table()
        self._ensure_certificates_columns()
        self._migrate_certificates_to_session_pk()
        self._ensure_knowledge_columns()
        self._ensure_users_columns()

    def _ensure_certificates_table(self):
        """确保证书表存在（兼容已有数据库，避免重新建库）

        复合主键 (cert_number, session_id)：同一证书编号可存在于不同导入会话，
        会话隔离靠 session_id；单会话内按 cert_number 去重（INSERT OR REPLACE）。
        """
        ddl = """
        CREATE TABLE IF NOT EXISTS certificates (
            cert_number TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            org_id TEXT,
            org_name TEXT,
            player_id TEXT,
            player_name TEXT,
            group_name TEXT,
            award TEXT,
            cert_round TEXT,
            work_name TEXT,
            instructor TEXT,
            language TEXT,
            promotion TEXT,
            packed TEXT,
            missing_work_name INTEGER DEFAULT 0,
            is_withdrawn INTEGER DEFAULT 0,
            receiving_org TEXT,
            source_sheet TEXT,
            import_id TEXT,
            created_at TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (cert_number, session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_certificates_project_id ON certificates(project_id);
        CREATE INDEX IF NOT EXISTS idx_certificates_org_id ON certificates(org_id);
        CREATE INDEX IF NOT EXISTS idx_certificates_player_id ON certificates(player_id);
        CREATE INDEX IF NOT EXISTS idx_certificates_award ON certificates(award);
        CREATE INDEX IF NOT EXISTS idx_certificates_cert_round ON certificates(cert_round);
        """
        self.db.execute_script(ddl)

    def _migrate_certificates_to_session_pk(self):
        """把既有「单主键 cert_number」的证书表迁移为复合主键 (cert_number, session_id)。

        旧库里证书表是单主键，无法在同一编号存在于多个导入会话时隔离；重建为复合主键，
        旧数据统一归入一个 legacy 会话（session_id='legacy-import'），避免丢失。
        仅在检测到表仍为单主键时执行一次。整段用事务包裹，迁移失败则原表不动。
        """
        try:
            rows = self.db.fetchall("PRAGMA table_info(certificates)")
            if not rows:
                return
            cols = {r['name'] for r in rows}
            pk_cols = [r['name'] for r in rows if r['pk']]
            composite = ('session_id' in cols and set(pk_cols) == {'cert_number', 'session_id'})
            if not composite:
                legacy = 'legacy-import'
                # 目标列顺序（与复合主键表一致）
                target_cols = [
                    'cert_number', 'session_id', 'project_id', 'org_id', 'org_name',
                    'player_id', 'player_name', 'group_name', 'award', 'cert_round',
                    'work_name', 'instructor', 'language', 'promotion', 'packed',
                    'missing_work_name', 'is_withdrawn', 'receiving_org', 'source_sheet',
                    'import_id', 'created_at', 'updated_at'
                ]
                int_cols = {'missing_work_name', 'is_withdrawn'}

                # 逐列构造 SELECT 表达式：
                # - session_id：固定写入 legacy 会话字面量
                # - 旧表缺失的列：整数列给 0，updated_at 用 CURRENT_TIMESTAMP，其余空串
                # - 旧表存在的列：整数列 COALESCE(c,0)，文本列 COALESCE(c,'')（保空串而非 NULL）
                def src_expr(c):
                    if c == 'session_id':
                        return f"'{legacy}'"
                    if c == 'updated_at':
                        return 'CURRENT_TIMESTAMP' if c not in cols else 'COALESCE(updated_at, CURRENT_TIMESTAMP)'
                    if c not in cols:
                        return '0' if c in int_cols else "''"
                    if c in int_cols:
                        return f"COALESCE({c}, 0)"
                    return f"COALESCE({c}, '')"

                select_expr = ', '.join(src_expr(c) for c in target_cols)
                with self.db.transaction() as conn:
                    conn.execute("""
                        CREATE TABLE certificates_new (
                            cert_number TEXT NOT NULL,
                            session_id TEXT NOT NULL DEFAULT '',
                            project_id TEXT, org_id TEXT, org_name TEXT, player_id TEXT,
                            player_name TEXT, group_name TEXT, award TEXT, cert_round TEXT,
                            work_name TEXT, instructor TEXT, language TEXT, promotion TEXT,
                            packed TEXT, missing_work_name INTEGER DEFAULT 0,
                            is_withdrawn INTEGER DEFAULT 0, receiving_org TEXT,
                            source_sheet TEXT, import_id TEXT, created_at TEXT,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (cert_number, session_id)
                        )
                    """)
                    conn.execute(
                        f"INSERT OR REPLACE INTO certificates_new ({', '.join(target_cols)}) "
                        f"SELECT {select_expr} FROM certificates"
                    )
                    conn.execute("DROP TABLE certificates")
                    conn.execute("ALTER TABLE certificates_new RENAME TO certificates")
                print("[DB] certificates 表已迁移为 (cert_number, session_id) 复合主键，旧数据归入会话 legacy-import")
            # 无论新旧库，确保 session_id 索引存在
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_certificates_session_id ON certificates(session_id)")
        except Exception as e:
            print(f"[DB] certificates 主键迁移失败（可忽略，不影响既有字段）: {e}")

    def _ensure_certificates_columns(self):
        """补齐证书表后续新增字段（SQLite 无 ADD COLUMN IF NOT EXISTS，需自查 pragma）"""
        required = {
            'receiving_org': 'TEXT',   # 收件/打包单位：台账导出的分表维度
        }
        try:
            rows = self.db.fetchall("PRAGMA table_info(certificates)")
            existing = {r['name'] for r in rows}
            for col, ddl in required.items():
                if col not in existing:
                    self.db.execute(f"ALTER TABLE certificates ADD COLUMN {col} {ddl}")
        except Exception as e:
            print(f"[DB] 证书表字段迁移失败（可忽略，不影响既有字段）: {e}")

    def _ensure_knowledge_columns(self):
        """补齐知识库表新增字段（tags / fields / links）。

        SQLite 无 ADD COLUMN IF NOT EXISTS，需自查 pragma。这 3 列以 JSON 承载
        结构化内容：tags=标签数组、fields=按类型模板的结构化字段对象、links=关联
        业务实体数组。缺失时 _filter_fields 会把这些字段丢掉，导致保存后结构化内容
        整段消失——所以必须在启动时为既有库补齐。
        """
        required = {
            'tags': 'TEXT',   # JSON 数组：标签
            'fields': 'TEXT', # JSON 对象：结构化字段（guide/troubleshoot/case/tip/reference 各有模板）
            'links': 'TEXT',  # JSON 数组：关联业务实体（project/player/org）
        }
        try:
            rows = self.db.fetchall("PRAGMA table_info(knowledge)")
            existing = {r['name'] for r in rows}
            for col, ddl in required.items():
                if col not in existing:
                    self.db.execute(f"ALTER TABLE knowledge ADD COLUMN {col} {ddl}")
        except Exception as e:
            print(f"[DB] 知识库表字段迁移失败（可忽略，不影响既有字段）: {e}")

    def _ensure_users_columns(self):
        """补齐 users 表新增字段（is_active）。

        启用/停用账号需要持久化状态。SQLite 无 ADD COLUMN IF NOT EXISTS，需自查
        pragma 后追加。旧库缺失该列时，账号默认为启用态（1）。
        """
        required = {
            'is_active': 'INTEGER DEFAULT 1',
        }
        try:
            rows = self.db.fetchall("PRAGMA table_info(users)")
            existing = {r['name'] for r in rows}
            for col, ddl in required.items():
                if col not in existing:
                    self.db.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        except Exception as e:
            print(f"[DB] users 表字段迁移失败（可忽略，不影响既有字段）: {e}")

    def load_all_data(self, sections=None) -> Dict:
        """读取同一 SQLite 快照，并返回各可写数据段的并发控制版本。"""
        with self.db.transaction():
            data = self._read_snapshot(sections=sections)
            data['_revisions'] = self._snapshot_revisions(data)
            return data

    def _read_snapshot(self, sections=None) -> Dict:
        """调用方负责事务；备份保留完整审计、通知记录，不做分页截断。"""
        loaders = {
            '_version': self.get_version,
            'projects': lambda: self.projects.get_all(order_by='created_at DESC'),
            'organizations': lambda: self.organizations.get_all(order_by='created_at DESC'),
            'players': lambda: self.players.get_all(order_by='created_at DESC'),
            'finances': lambda: self.finances.get_all(order_by='date DESC'),
            'users': lambda: self.users.get_all(order_by='created_at DESC'),
            'materialTypes': self.material_types.get_all,
            'knowledge': self._load_knowledge,
            'config': self._load_config,
            'archiveConfig': self._load_archive_config,
            'archiveMappings': self._load_archive_mappings,
            'checklistState': self._load_checklist_states,
            'templates': self._load_templates,
            'checklists': self.checklists.get_all,
            'certificates': self.certificates.get_all,
            'certSettings': self._load_cert_settings,
            'printTemplates': self._load_print_templates,
            'projectChecklists': self._load_project_checklists,
            'auditLogs': lambda: self.audit_logs.get_all(order_by='created_at DESC'),
            'notifications': lambda: self.notifications.get_all(order_by='created_at DESC'),
            'currentUser': self._get_current_user,
        }
        selected = set(loaders) if sections is None else set(sections)
        if selected - set(loaders):
            raise ValueError('读取包含未知数据段')
        return {key: load() for key, load in loaders.items() if key in selected}

    @staticmethod
    def _snapshot_revisions(data: Dict) -> Dict:
        def encode(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True,
                              separators=(',', ':'), allow_nan=False)

        revisions = {}
        for key in WRITABLE_SECTIONS.intersection(data):
            value = data.get(key)
            # Entity rows have no meaningful SQL order. Keep nested arrays (such
            # as template fields and checklist items) in their original order.
            if isinstance(value, list):
                value = sorted(value, key=encode)
            elif key == 'knowledge' and isinstance(value, dict):
                value = {kind: sorted(rows, key=encode) for kind, rows in value.items()}
            revisions[key] = hashlib.sha256(encode(value).encode('utf-8')).hexdigest()
        return revisions

    def _validate_snapshot(self, data):
        if not isinstance(data, dict):
            raise ValueError('保存数据必须是对象')
        json.dumps(data, allow_nan=False)
        list_sections = {
            'projects', 'organizations', 'players', 'finances', 'users',
            'materialTypes', 'notifications', 'auditLogs', 'checklists',
            'certificates', 'printTemplates',
        }
        for key in WRITABLE_SECTIONS.intersection(data):
            payload = data[key]
            if key in list_sections:
                self._validate_records(key, payload)
            elif not isinstance(payload, dict):
                raise ValueError(f'{key} 必须是对象')
        if 'knowledge' in data:
            for kind, rows in data['knowledge'].items():
                if kind not in {'guide', 'troubleshoot', 'case', 'tip', 'reference',
                                'solutions', 'practices', 'training'}:
                    raise ValueError(f'未知知识库分类: {kind}')
                self._validate_records('knowledge', rows)
            ids = [self._record_identity(row['id']) for rows in data['knowledge'].values() for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError('知识库记录 ID 重复')
        if 'config' in data and set(data['config']) - CONFIG_KEYS:
            raise ValueError('config 包含不属于业务配置的数据键')
        if 'templates' in data:
            for key in ('categories', 'items'):
                if key in data['templates'] and not isinstance(data['templates'][key], list):
                    raise ValueError(f'templates.{key} 必须是数组')
        if 'checklistState' in data:
            if any(type(v) not in (bool, int) or v not in (0, 1)
                   for v in data['checklistState'].values()):
                raise ValueError('checklistState 必须使用布尔值')

    @staticmethod
    def _record_identity(value):
        # Historical JSON exports may use numbers for TEXT primary keys.
        if type(value) not in (str, int, float) or not str(value).strip():
            raise ValueError('记录缺少有效主键')
        return str(value)

    @staticmethod
    def _validate_records(section, rows):
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'{section} 必须是记录对象数组')
        seen = set()
        for row in rows:
            identity = row.get('certNumber', row.get('cert_number')) if section == 'certificates' else row.get('id')
            identity = DataStore._record_identity(identity)
            session = row.get('sessionId', row.get('session_id', ''))
            if section == 'certificates' and type(session) not in (str, int, float):
                raise ValueError('证书 sessionId 必须是字符串或数字')
            key = (identity, str(session)) if section == 'certificates' else identity
            if key in seen:
                raise ValueError(f'{section} 记录主键重复')
            seen.add(key)

    @staticmethod
    def _foreign_key_violations(conn):
        """按逻辑主键识别旧孤儿；全表替换可能改变 rowid。"""
        violations = set()
        for table, rowid, parent, fk_id in conn.execute('PRAGMA foreign_key_check'):
            columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            keys = [row[1] for row in sorted(columns, key=lambda row: row[5]) if row[5]]
            columns_sql = ', '.join('"' + key.replace('"', '""') + '"' for key in keys)
            identity = conn.execute(f'SELECT {columns_sql} FROM "{table}" WHERE rowid = ?', (rowid,)).fetchone()
            foreign_columns = [row[3] for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')
                               if row[0] == fk_id]
            refs_sql = ', '.join('"' + key.replace('"', '""') + '"' for key in foreign_columns)
            references = conn.execute(f'SELECT {refs_sql} FROM "{table}" WHERE rowid = ?', (rowid,)).fetchone()
            violations.add((table, tuple(identity) if identity else rowid, parent, fk_id,
                            tuple(references) if references else None))
        return violations

    def save_all_data(self, data: Dict, revision_result: Optional[Dict] = None) -> bool:
        """原子保存出现的数据段。HTTP 必须提供 _revisions；内部迁移可省略。"""
        conn = self.db.get_connection()
        if conn.in_transaction:
            raise RuntimeError('快照保存必须拥有独立事务')
        try:
            self._validate_snapshot(data)
            touched_sections = WRITABLE_SECTIONS.intersection(data)
            # Toggle only outside transactions; otherwise SQLite ignores it.
            # This also prevents any future ON DELETE actions during replacement.
            conn.execute('PRAGMA foreign_keys = OFF')
            with self.db.transaction(immediate=True):
                old_violations = self._foreign_key_violations(conn)
                if '_revisions' in data:
                    expected = data['_revisions']
                    if not isinstance(expected, dict):
                        raise ValueError('_revisions 必须是对象')
                    current = self._snapshot_revisions(self._read_snapshot(sections=touched_sections))
                    conflicts = [key for key in touched_sections
                                 if expected.get(key) != current[key]]
                    if conflicts:
                        raise SnapshotConflictError(conflicts)
                sections = [
                    ('printTemplates', self._save_print_templates, 'printTemplates', 'print_templates'),
                    ('projects', self._save_projects, 'projects', 'projects'),
                    ('organizations', self._save_organizations, 'organizations', 'organizations'),
                    ('users', self._save_users, 'users', None),
                    ('players', self._save_players, 'players', 'players'),
                    ('finances', self._save_finances, 'finances', 'finances'),
                    ('config', self._save_config, 'config', None),
                    ('materialTypes', self._save_material_types, 'materialTypes', None),
                    ('knowledge', self._save_knowledge, 'knowledge', None),
                    ('notifications', self._save_notifications, 'notifications', None),
                    ('templates', self._save_templates, 'templates', None),
                    ('auditLogs', self._save_audit_logs, 'auditLogs', None),
                    ('checklistState', self._save_checklist_states, 'checklistState', None),
                    ('certificates', self._save_certificates, 'certificates', 'certificates'),
                    ('certSettings', self._save_cert_settings, 'certSettings', None),
                    ('projectChecklists', self._save_project_checklists, 'projectChecklists', None),
                    ('checklists', self._save_checklists, 'checklists', 'checklists'),
                    ('archiveConfig', self._save_archive_config, 'archiveConfig', None),
                    ('archiveMappings', self._save_archive_mappings, 'archiveMappings', None),
                ]

                for label, save_fn, key, clear_table in sections:
                    if key not in data:
                        continue
                    payload = data[key]
                    if clear_table and not payload and not data.get('_snapshot') and '_revisions' not in data:
                        continue
                    if clear_table:
                        conn.execute(f"DELETE FROM {clear_table}")
                    if save_fn(payload, conn) is False:
                        raise ValueError(f'{label} 数据未通过校验')
                if self._foreign_key_violations(conn) - old_violations:
                    raise ValueError('关联校验失败：引用记录不存在，或删除的项目/机构仍被使用')
                self._update_version(data.get('_version', '2.3'), conn)
                saved_revisions = self._snapshot_revisions(
                    self._read_snapshot(sections=touched_sections)) if revision_result is not None else {}
            if revision_result is not None:
                revision_result.update({key: saved_revisions[key]
                                        for key in touched_sections})
            # 标记搜索索引过期。真正的重建推迟到「数据变化后的第一次搜索」，
            # 这样保存路径不会被索引构建拖慢。
            try:
                from server.search.index import mark_dirty
                with self.db.transaction(immediate=True):
                    mark_dirty(conn)
            except Exception as e:
                print(f"标记搜索索引过期失败（不影响保存）: {e}")

            # 每日自动备份：跨天后的第一次保存会补一份（当天已备份则直接跳过，
            # 内存缓存保证不会每次都去列目录）。后端长期不重启也能覆盖到。
            try:
                from server.config import BASE_DIR as _BASE_DIR
                from server.database.maintenance import ensure_daily_backup
                ensure_daily_backup(
                    os.path.join(_BASE_DIR, 'data', 'backup'),
                    lambda: self.load_all_data()
                )
            except Exception as e:
                print(f"每日自动备份跳过（不影响保存）: {e}")
            return True
        except SnapshotConflictError:
            raise
        except Exception as e:
            print(f"保存数据失败，全部修改已回滚: {e}")
            return False
        finally:
            conn.execute('PRAGMA foreign_keys = ON')

    # 按当前连接读取 schema，避免其他数据库或恢复后的旧列缓存串库。
    def _get_table_columns(self, table_name: str, conn) -> set:
        """动态获取表的实际列名，过滤前端派生字段。"""
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}

    def _filter_fields(self, data: Dict, allowed: set) -> Dict:
        """只保留表中实际存在的字段"""
        return {k: v for k, v in data.items() if k in allowed}

    def _upsert(self, table: str, data: Dict, conn, delete_first: bool = False):
        """插入已清空表的记录；任何约束失败都必须由外层事务回滚。"""
        allowed = self._get_table_columns(table, conn)
        filtered = self._filter_fields(data, allowed)
        if not filtered:
            raise ValueError(f'{table} 记录没有可写入字段')
        identity_fields = ('cert_number', 'session_id') if table == 'certificates' else ('id',)
        for key in identity_fields:
            if key in filtered and filtered[key] is not None:
                filtered[key] = str(filtered[key])
        if table in ('players', 'finances'):
            for key in ('org_id', 'project_id'):
                if filtered.get(key) == '':
                    filtered[key] = None
                elif filtered.get(key) is not None:
                    filtered[key] = str(filtered[key])
        fields = ', '.join(filtered.keys())
        placeholders = ', '.join(['?' for _ in filtered])
        conn.execute(f"INSERT INTO {table} ({fields}) VALUES ({placeholders})", tuple(filtered.values()))
        return True

    def _save_projects(self, projects, conn):
        """保存项目数据"""
        if not isinstance(projects, list):
            return
        for project in projects:
            if not isinstance(project, dict):
                continue
            model = ProjectModel(self.db)
            self._upsert('projects', model._serialize(model._convert_to_db(project)), conn)

    def _save_organizations(self, organizations, conn):
        """保存机构数据"""
        if not isinstance(organizations, list):
            return
        for org in organizations:
            if not isinstance(org, dict):
                continue
            model = OrganizationModel(self.db)
            self._upsert('organizations', model._serialize(model._convert_to_db(org)), conn)

    def _save_players(self, players, conn):
        """保存选手数据"""
        if not isinstance(players, list):
            return
        for player in players:
            if not isinstance(player, dict):
                continue
            model = PlayerModel(self.db)
            self._upsert('players', model._serialize(model._convert_to_db(player)), conn)

    def _save_finances(self, finances, conn):
        """保存财务数据"""
        if not isinstance(finances, list):
            return
        for finance in finances:
            if not isinstance(finance, dict):
                continue
            model = FinanceModel(self.db)
            self._upsert('finances', model._serialize(model._convert_to_db(finance)), conn)

    def _save_certificates(self, certificates, conn):
        """保存证书数据"""
        if not isinstance(certificates, list):
            return
        for cert in certificates:
            if not isinstance(cert, dict):
                continue
            model = CertificateModel(self.db)
            self._upsert('certificates', model._serialize(model._convert_to_db(cert)), conn)

    def _save_cert_settings(self, settings, conn):
        """保存证书模块配置（编号模板等），整体以 JSON 存进 settings 表"""
        if settings is None:
            return True
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ('certSettings', json.dumps(settings, ensure_ascii=False),
             datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        return True

    def _load_cert_settings(self) -> Dict:
        """加载证书模块配置"""
        row = self.settings.get_by_id('certSettings')
        if not row or not row.get('value'):
            return {}
        try:
            data = json.loads(row['value'])
        except Exception:
            data = row['value']
        return data if isinstance(data, dict) else {}

    def _save_project_checklists(self, data, conn):
        """保存按项目组织的清单全量结构（tabs → cards → items，含勾选态与自定义项）。

        整体以 JSON 存进 settings 表，与 certSettings / templates 同写法。
        每个项目独立一份（键为项目ID，'__global__' 表示「全部项目」视图），互不干扰，
        因此不同项目可以拥有完全不同的清单项。
        """
        if data is None:
            return True
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ('projectChecklists', json.dumps(data, ensure_ascii=False),
             datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        return True

    def _load_project_checklists(self) -> Dict:
        """加载按项目组织的清单数据，结构同 _save_project_checklists 写入的 JSON。

        settings 读取会经过 Model._deserialize，以 { 或 [ 开头的字符串可能已被解析成对象，
        故 json.loads 抛 TypeError 时回退用原值（与 _load_cert_settings 一致）。
        """
        row = self.settings.get_by_id('projectChecklists')
        if not row or not row.get('value'):
            return {}
        try:
            data = json.loads(row['value'])
        except Exception:
            data = row['value']
        return data if isinstance(data, dict) else {}

    def _save_users(self, users, conn):
        """管理员恢复账户时，任何一条无效记录都使整个恢复回滚。"""
        model = UserModel(self.db)
        for user in users:
            if not user.get('username') or not user.get('password'):
                raise ValueError('用户记录缺少 username/password')
        conn.execute("DELETE FROM users")
        for user in users:
            self._upsert('users', model._serialize(model._convert_to_db(user)), conn)
        return True

    def _save_config(self, config: Dict, conn):
        """保存配置数据"""
        conn.executemany('DELETE FROM settings WHERE key = ?', [(key,) for key in CONFIG_KEYS])
        for key, value in config.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )

    def _save_material_types(self, material_types, conn):
        """保存资料类型"""
        conn.execute("DELETE FROM material_types")
        if not isinstance(material_types, list):
            return
        for mt in material_types:
            if not isinstance(mt, dict):
                continue
            model = MaterialTypeModel(self.db)
            self._upsert('material_types', model._serialize(model._convert_to_db(mt)), conn)

    def _save_knowledge(self, knowledge: Dict, conn):
        """保存知识库数据（5 类语义化：guide / troubleshoot / case / tip / reference）。"""
        conn.execute("DELETE FROM knowledge")
        for ktype, items in knowledge.items():
            if isinstance(items, list):
                for item in items:
                    item = dict(item, type=ktype)
                    model = KnowledgeModel(self.db)
                    self._upsert('knowledge', model._serialize(model._convert_to_db(item)), conn)

    def _save_notifications(self, notifications, conn):
        """保存通知数据"""
        conn.execute("DELETE FROM notifications")
        if not isinstance(notifications, list):
            return
        for notification in notifications:
            if not isinstance(notification, dict):
                continue
            model = NotificationModel(self.db)
            self._upsert('notifications', model._serialize(model._convert_to_db(notification)), conn)

    def _load_print_templates(self) -> List[Dict[str, Any]]:
        """加载打印模板列表（底图 + 勾选字段）。

        前端持有的字段名是 `printTemplates`，存储时转回下划线列名。
        `fields` 是 JSON 字符串，这里反序列化成对象返回。
        """
        rows = self.db.fetchall(
            "SELECT * FROM print_templates ORDER BY created_at DESC")
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = {self._snake_to_camel(k): v for k, v in row.items()}
            raw_fields = item.pop('fields', None)
            item['fields'] = json.loads(raw_fields) if raw_fields else []
            out.append(item)
        return out

    @staticmethod
    def _snake_to_camel(name: str) -> str:
        parts = (name or '').split('_')
        return parts[0] + ''.join(p.capitalize() for p in parts[1:])

    def _save_print_templates(self, templates, conn):
        """保存打印模板列表。

        ⚠️ 与 `templates`（合同/表单，存在 settings 里）是两张不同的表，不要混淆。
        """
        if templates is None:
            return True
        if not isinstance(templates, list):
            return False

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for t in templates:
            tid = self._record_identity(t.get('id'))
            fields = t.get('fields')
            if isinstance(fields, str):
                fields = json.loads(fields)
            if fields is not None and not isinstance(fields, list):
                raise ValueError('打印模板 fields 必须是数组')
            fields_json = json.dumps(fields, ensure_ascii=False) if isinstance(fields, list) else (
                fields if isinstance(fields, str) else '[]')
            conn.execute(
                """
                INSERT INTO print_templates
                    (id, name, doc_type, background, page_width, page_height, page_size,
                     fields, project_id, cert_round, year,
                     source_path, source_ext, source_mtime, note, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    tid,
                    t.get('name') or tid,
                    t.get('docType') or 'certificate',
                    t.get('background') or '',
                    t.get('pageWidth'),
                    t.get('pageHeight'),
                    t.get('pageSize'),
                    fields_json,
                    t.get('projectId'),
                    t.get('certRound'),
                    t.get('year'),
                    t.get('sourcePath'),
                    t.get('sourceExt'),
                    t.get('sourceMtime'),
                    t.get('note'),
                    t.get('createdAt') or now,
                    t.get('updatedAt') or now,
                )
            )
        return True

    def _save_templates(self, templates, conn):
        """保存模板数据

        前端约定结构为 {"categories": [...], "items": [...]}。
        """
        if templates is None:
            return True
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ('templates', json.dumps(templates, ensure_ascii=False),
             datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        return True

    def _save_audit_logs(self, logs, conn):
        """保存审计日志"""
        conn.execute("DELETE FROM audit_logs")
        for log in logs:
            if not isinstance(log, dict):
                continue
            model = AuditLogModel(self.db)
            self._upsert('audit_logs', model._serialize(model._convert_to_db(log)), conn)
        return True

    def _save_checklists(self, checklists, conn):
        for row in checklists:
            self._upsert('checklists', self.checklists._serialize(
                self.checklists._convert_to_db(row)), conn)

    def _save_archive_config(self, config, conn):
        conn.execute("DELETE FROM settings WHERE substr(key, 1, 14) = 'archiveConfig_'")
        for key, value in config.items():
            conn.execute(
                'INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                ('archiveConfig_' + key, json.dumps(value, ensure_ascii=False),
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            )

    def _save_archive_mappings(self, mappings, conn):
        conn.execute(
            'INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
            ('archiveMappings', json.dumps(mappings, ensure_ascii=False),
             datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        )

    def _save_checklist_states(self, states: Dict, conn):
        """保存清单状态"""
        conn.execute("DELETE FROM checklist_states")
        for key, checked in states.items():
            conn.execute(
                "INSERT INTO checklist_states (id, checklist_key, checked, updated_at) VALUES (?, ?, ?, ?)",
                (f"cls_{key}", key, 1 if checked else 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )

    def _load_knowledge(self) -> Dict:
        """加载知识库数据（5 类语义化结构，并迁移旧型 solutions/practices/training）。

        旧库里 type 可能是 solutions/practices/training，统一映射到新 5 型：
        solutions→guide / practices→tip / training→reference。前端 useKnowledgeStore
        的 normalize() 也做同样映射，两端保持一致。
        """
        knowledge = {
            'guide': [], 'troubleshoot': [], 'case': [], 'tip': [], 'reference': []
        }
        LEGACY_MAP = {'solutions': 'guide', 'practices': 'tip', 'training': 'reference'}
        items = self.knowledge.get_all()
        for item in items:
            raw_type = item.get('type', 'guide')
            target = LEGACY_MAP.get(raw_type, raw_type)
            if target in knowledge:
                knowledge[target].append(item)
        return knowledge

    def _load_config(self) -> Dict:
        """加载配置数据（含资源中心可配置分类 resourceCategories）"""
        config = {}
        placeholders = ','.join('?' for _ in CONFIG_KEYS)
        rows = self.settings.find(f'key IN ({placeholders})', tuple(CONFIG_KEYS))
        for row in rows:
            key = row['key']
            value = row['value']
            if value is not None:
                try:
                    config[key] = json.loads(value)
                except:
                    config[key] = value
        return config

    def _load_archive_config(self) -> Dict:
        """加载归档配置；实体未配置过资料类型时回填默认值。

        初始状态（首次使用、尚未保存过配置）下，「项目 / 机构资料类型」会是空的，
        配置页与详情页上传下拉都没有可选项。这里在**该实体的键完全缺失**时回填
        由归档分类（taxonomy.SUBDIRS）推导的默认资料类型。

        注意：只在「键缺失」时回填——若用户主动把某实体的类型删空（保存了空列表，
        键存在但值为空），则尊重用户选择，不再强加默认值。
        """
        config = {}
        rows = self.settings.find("key LIKE 'archiveConfig_%'")
        for row in rows:
            key = row['key'].replace('archiveConfig_', '')
            value = row['value']
            if value is not None:
                try:
                    config[key] = json.loads(value)
                except:
                    config[key] = value
        try:
            from server.archive.taxonomy import default_material_types
            for entity in ('projects', 'organizations'):
                if entity not in config:
                    config[entity] = {'materialTypes': default_material_types(entity)}
        except Exception as e:
            print(f"[DB] 回填默认资料类型失败（可忽略）: {e}")
        return config

    def _load_archive_mappings(self) -> Dict:
        """加载归档映射"""
        row = self.settings.get_by_id('archiveMappings')
        if row and row.get('value'):
            if isinstance(row['value'], dict):
                return row['value']
            try:
                return json.loads(row['value'])
            except:
                return {}
        return {}

    def _load_checklist_states(self) -> Dict:
        """加载清单状态"""
        states = {}
        rows = self.checklist_states.get_all()
        for row in rows:
            states[row['checklistKey']] = bool(row.get('checked', 0))
        return states

    def _load_templates(self) -> Dict:
        """加载模板数据

        返回结构与前端 TemplatesView 一致：{"categories": [...], "items": [...]}。
        """
        empty = {'categories': [], 'items': []}
        row = self.settings.get_by_id('templates')
        if not row or not row.get('value'):
            return empty
        try:
            data = json.loads(row['value'])
        except Exception:
            data = row['value']
        if not isinstance(data, dict):
            return empty
        categories = data.get('categories')
        items = data.get('items')
        return {
            **data,
            'categories': categories if isinstance(categories, list) else [],
            'items': items if isinstance(items, list) else []
        }

    def _get_current_user(self) -> Optional[Dict]:
        """获取当前用户"""
        row = self.settings.get_by_id('currentUser')
        if row and row.get('value'):
            try:
                return json.loads(row['value'])
            except:
                return None
        return None

    def get_version(self) -> str:
        """获取数据版本"""
        row = self.db.fetchone("SELECT version FROM data_version WHERE id = 1")
        return row['version'] if row else '2.3'

    def _update_version(self, version: str, conn):
        """更新数据版本"""
        conn.execute(
            "UPDATE data_version SET version = ?, updated_at = ? WHERE id = 1",
            (version, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )

    def export_to_json(self, json_file: str) -> bool:
        """导出数据到 JSON 文件"""
        try:
            data = self.load_all_data()
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"数据已导出到: {json_file}")
            return True
        except Exception as e:
            print(f"导出数据失败: {e}")
            return False

    def import_from_json(self, json_file: str) -> bool:
        """从 JSON 文件导入数据"""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data.pop('_revisions', None)
            data['_snapshot'] = True
            return self.save_all_data(data)
        except Exception as e:
            print(f"导入数据失败: {e}")
            return False


# 全局数据库实例
_db_instance = None

def get_db() -> Database:
    """获取数据库实例（单例模式）"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

def get_data_store() -> DataStore:
    """获取数据存储实例"""
    return DataStore(get_db())
