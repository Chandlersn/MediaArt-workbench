# -*- coding: utf-8 -*-
"""
SQLite 数据库连接与 ORM 模块
提供数据库连接、事务管理和基础 CRUD 操作
"""

import os
import json
import sqlite3
import threading
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


class Database:
    """SQLite 数据库管理类"""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
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

        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            print(f"数据库表结构已创建: {self.db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（线程安全）"""
        if not hasattr(_local, 'connection') or _local.connection is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row  # 使用 Row 工厂，支持字典式访问
            conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
            conn.execute("PRAGMA journal_mode = WAL")  # 使用 WAL 模式提高并发性能
            _local.connection = conn
        return _local.connection

    def close_connection(self):
        """关闭数据库连接"""
        if hasattr(_local, 'connection') and _local.connection:
            _local.connection.close()
            _local.connection = None

    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

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
        with self.db.transaction() as conn:
            conn.executescript(ddl)

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

    def load_all_data(self) -> Dict:
        """加载所有数据（兼容 JSON 格式）"""
        import time
        start = time.time()

        def timed_load(name, fn):
            t = time.time()
            result = fn()
            print(f"  [性能] 加载 {name}: {time.time() - t:.3f}秒, 数量: {len(result) if hasattr(result, '__len__') else 'N/A'}")
            return result

        data = {
            '_version': timed_load('version', lambda: self.get_version()),
            'projects': timed_load('projects', lambda: self.projects.get_all(order_by='created_at DESC')),
            'organizations': timed_load('organizations', lambda: self.organizations.get_all(order_by='created_at DESC')),
            'players': timed_load('players', lambda: self.players.get_all(order_by='created_at DESC')),
            'finances': timed_load('finances', lambda: self.finances.get_all(order_by='date DESC')),
            'users': timed_load('users', lambda: self.users.get_all(order_by='created_at DESC')),
            'materialTypes': timed_load('materialTypes', lambda: self.material_types.get_all()),
            'knowledge': timed_load('knowledge', lambda: self._load_knowledge()),
            'config': timed_load('config', lambda: self._load_config()),
            'archiveConfig': timed_load('archiveConfig', lambda: self._load_archive_config()),
            'archiveMappings': timed_load('archiveMappings', lambda: self._load_archive_mappings()),
            'checklistState': timed_load('checklistState', lambda: self._load_checklist_states()),
            'templates': timed_load('templates', lambda: self._load_templates()),
            'checklists': timed_load('checklists', lambda: self.checklists.get_all()),
            'certificates': timed_load('certificates', lambda: self.certificates.get_all()),
            'certSettings': timed_load('certSettings', lambda: self._load_cert_settings()),
            'projectChecklists': timed_load('projectChecklists', lambda: self._load_project_checklists()),
            'auditLogs': timed_load('auditLogs', lambda: self.audit_logs.get_all(order_by='created_at DESC', limit=100)),
            'notifications': timed_load('notifications', lambda: self.notifications.get_all(order_by='created_at DESC', limit=50)),
            'currentUser': timed_load('currentUser', lambda: self._get_current_user())
        }

        print(f"[性能] load_all_data 总耗时: {time.time() - start:.3f}秒")
        return data

    def save_all_data(self, data: Dict) -> bool:
        """保存所有数据（兼容 JSON 格式）

        隔离与安全策略：
        - 每张表独立 try/except：单表失败不会回滚其他表已完成的写入。
        - "先清空再回填"的 DELETE 只在本次确实要回填该表时才执行，
          杜绝“删了却没数据可写”导致的数据丢失。
          （原先无条件 DELETE FROM templates / audit_logs，而这两张表没有任何
            写入器，等于每次保存都把表清空一次。）
        """
        failures = []
        try:
            with self.db.transaction() as conn:
                # 临时禁用外键约束，避免全量替换时的级联冲突
                conn.execute("PRAGMA foreign_keys = OFF")

                # (标签, 写入函数, JSON 键, 需要先清空的表)
                # 注意：users / knowledge / material_types / notifications /
                #      checklist_states / templates / audit_logs 的 DELETE 已下沉到
                #      各自的 _save_* 内部；此处只为没有内建清空的表补 DELETE。
                sections = [
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
                ]

                for label, save_fn, key, clear_table in sections:
                    if key not in data:
                        continue
                    payload = data[key]
                    # 防误删（泛化自原先只保护 certificates 的写法）：凡"先清空再回填"
                    # 的表，若本次载荷为空则**不执行清空+回填**，保留库中现有数据。
                    # 理由：空载荷几乎只出现在异常路径上（加载失败 → 内存快照为空 →
                    # 触发保存 → 把库里整表抹掉，且返回 success）。这比"无法通过全量
                    # 保存清空某表"的代价小得多（逐条删除到空属罕见操作）。
                    if clear_table and not payload:
                        print(f"[SQLite] 跳过 {label} 同步：传入为空，保留库中现有数据")
                        continue
                    try:
                        if clear_table:
                            conn.execute(f"DELETE FROM {clear_table}")
                        if save_fn(payload, conn) is False:
                            failures.append(label)
                    except Exception as e:
                        failures.append(label)
                        print(f"[SQLite] 同步 {label} 失败: {e}")
                        import traceback
                        traceback.print_exc()

                # 更新版本
                self._update_version(data.get('_version', '2.3'), conn)

                # 恢复外键约束
                conn.execute("PRAGMA foreign_keys = ON")

            if failures:
                print(f"[SQLite] 同步完毕，但以下部分未能写入: {', '.join(failures)}")
                return False
            return True
        except Exception as e:
            print(f"保存数据失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    # 表字段缓存（运行时动态从 PRAGMA table_info 读取，防止前端多余字段导致 INSERT 失败）
    _table_columns_cache: Dict = {}

    def _get_table_columns(self, table_name: str, conn) -> set:
        """动态获取表的实际列名（带缓存）"""
        if table_name not in self._table_columns_cache:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            self._table_columns_cache[table_name] = {row[1] for row in cursor.fetchall()}
        return self._table_columns_cache[table_name]

    def _filter_fields(self, data: Dict, allowed: set) -> Dict:
        """只保留表中实际存在的字段"""
        return {k: v for k, v in data.items() if k in allowed}

    def _upsert(self, table: str, data: Dict, conn, delete_first: bool = False):
        """通用 upsert：过滤字段后执行 INSERT OR REPLACE

        单条记录违反约束（NOT NULL / UNIQUE 等）时跳过该条并告警，返回 False。
        这样一条脏数据不会把整批同步、乃至同一事务里的其他表一起拖垮。
        """
        allowed = self._get_table_columns(table, conn)
        filtered = self._filter_fields(data, allowed)
        if not filtered:
            return False
        fields = ', '.join(filtered.keys())
        placeholders = ', '.join(['?' for _ in filtered])
        try:
            conn.execute(f"INSERT OR REPLACE INTO {table} ({fields}) VALUES ({placeholders})", tuple(filtered.values()))
            return True
        except sqlite3.IntegrityError as e:
            print(f"[SQLite] 跳过不合法的 {table} 记录 id={filtered.get('id', '?')!r}: {e}")
            return False

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
        """保存用户数据

        安全策略：users 表承载登录账号，绝不能因为一条脏数据就整表清空。
        因此先过滤出不满足 NOT NULL 约束（缺 username / password）的记录，
        只有在存在可写入记录时才执行 delete + insert。
        """
        if not isinstance(users, list):
            return True

        model = UserModel(self.db)
        valid_users = []
        for user in users:
            if not isinstance(user, dict):
                continue
            converted = model._convert_to_db(user)
            if not converted.get('username') or not converted.get('password'):
                print(
                    f"[SQLite] 跳过不合法的用户记录（缺少 username/password）: "
                    f"id={user.get('id')!r} username={user.get('username')!r} "
                    f"name={user.get('name')!r}"
                )
                continue
            valid_users.append(user)

        if users and not valid_users:
            # 全部不合法：宁可不同步，也不能把现有账号清空
            print("[SQLite] 警告：所有用户记录均不合法，跳过 users 表同步以保护现有账号")
            return False

        conn.execute("DELETE FROM users")
        for user in valid_users:
            self._upsert('users', model._serialize(model._convert_to_db(user)), conn)
        return True

    def _save_config(self, config: Dict, conn):
        """保存配置数据"""
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
                    item['type'] = ktype
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
        if not isinstance(logs, list):
            return True

        existing = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        if not logs and existing:
            print(f"[SQLite] 本次提交的审计日志为空、库中已有 {existing} 条，跳过清空以保护审计轨迹")
            return True

        conn.execute("DELETE FROM audit_logs")
        for log in logs:
            if not isinstance(log, dict):
                continue
            model = AuditLogModel(self.db)
            self._upsert('audit_logs', model._serialize(model._convert_to_db(log)), conn)
        return True

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
        rows = self.settings.find("key IN ('stages', 'projectTypes', 'orgTypes', 'statusList', 'financeTypes', 'incomeCategories', 'expenseCategories', 'stageMaterials', 'resourceCategories')")
        for row in rows:
            key = row['key']
            value = row['value']
            if value:
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
            if value:
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
            states[row['checklist_key']] = bool(row.get('checked', 0))
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
