-- ============================================
-- 媒体艺术展览工作台数据库表结构
-- 版本: 1.0
-- 创建时间: 2026-03-06
-- ============================================

-- ========== 项目表 ==========
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    status TEXT DEFAULT '筹备中',
    start_date TEXT,
    end_date TEXT,
    manager TEXT,
    description TEXT,
    org_ids TEXT,  -- JSON 数组存储
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_type ON projects(type);
CREATE INDEX IF NOT EXISTS idx_projects_start_date ON projects(start_date);

-- ========== 机构表 ==========
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    level TEXT DEFAULT '普通合作',
    contact TEXT,
    phone TEXT,
    address TEXT,
    note TEXT,
    coop_count INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_organizations_type ON organizations(type);
CREATE INDEX IF NOT EXISTS idx_organizations_level ON organizations(level);

-- ========== 选手表 ==========
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT,
    category TEXT,
    level TEXT,
    org_id TEXT,
    project_id TEXT,
    phone TEXT,
    note TEXT,
    stage TEXT DEFAULT '初赛',
    stage_history TEXT,  -- JSON 数组存储
    id_card TEXT,
    custom_fields TEXT,  -- JSON 对象存储
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_players_category ON players(category);
CREATE INDEX IF NOT EXISTS idx_players_stage ON players(stage);
CREATE INDEX IF NOT EXISTS idx_players_org_id ON players(org_id);
CREATE INDEX IF NOT EXISTS idx_players_project_id ON players(project_id);

-- ========== 财务表 ==========
CREATE TABLE IF NOT EXISTS finances (
    id TEXT PRIMARY KEY,
    org_id TEXT,
    project_id TEXT,
    type TEXT,  -- '收入' 或 '支出'
    category TEXT,
    amount REAL,
    date TEXT,
    title TEXT,
    note TEXT,
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_finances_type ON finances(type);
CREATE INDEX IF NOT EXISTS idx_finances_category ON finances(category);
CREATE INDEX IF NOT EXISTS idx_finances_date ON finances(date);
CREATE INDEX IF NOT EXISTS idx_finances_org_id ON finances(org_id);
CREATE INDEX IF NOT EXISTS idx_finances_project_id ON finances(project_id);

-- ========== 用户表 ==========
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT 'viewer',
    real_name TEXT,
    email TEXT,
    password_hashed INTEGER DEFAULT 0,
    password_migrated_at TEXT,
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- ========== 配置表 ==========
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,  -- JSON 存储
    description TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ========== 资料类型表 ==========
CREATE TABLE IF NOT EXISTS material_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT,
    required INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ========== 知识库表 ==========
CREATE TABLE IF NOT EXISTS knowledge (
    id TEXT PRIMARY KEY,
    type TEXT,  -- 'solutions', 'practices', 'training'
    title TEXT NOT NULL,
    description TEXT,
    author TEXT,
    date TEXT,
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge(type);

-- ========== 通知表 ==========
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    type TEXT DEFAULT 'info',
    read INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

-- ========== 审计日志表 ==========
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    action TEXT,
    resource_type TEXT,
    resource_id TEXT,
    details TEXT,  -- JSON 存储
    ip_address TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- ========== 模板表 ==========
CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    type TEXT,  -- 'contracts', 'forms'
    name TEXT NOT NULL,
    content TEXT,
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_templates_type ON templates(type);

-- ========== 清单表 ==========
CREATE TABLE IF NOT EXISTS checklists (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    items TEXT,  -- JSON 数组存储
    created_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ========== 清单状态表 ==========
CREATE TABLE IF NOT EXISTS checklist_states (
    id TEXT PRIMARY KEY,
    checklist_key TEXT NOT NULL,
    checked INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(checklist_key)
);

-- ========== 数据版本表 ==========
CREATE TABLE IF NOT EXISTS data_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version TEXT,
    schema_version TEXT DEFAULT '1.0',
    last_migration TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ========== 证书表 ==========
-- 复合主键 (cert_number, session_id)：同一证书编号可存在于不同「导入会话」中，
-- 会话隔离靠 session_id 区分；单会话内按 cert_number 去重（INSERT OR REPLACE）。
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

-- 初始化数据版本
INSERT OR IGNORE INTO data_version (id, version, schema_version)
VALUES (1, '2.3', '1.0');
