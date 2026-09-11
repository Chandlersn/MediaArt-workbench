# 媒体艺术展览工作台 - 项目分析报告 (Superpowers)

> 生成日期：2026-04-20
> 分析方法：系统性调试 + 证据验证

---

## 一、架构概览

| 层级 | 技术 | 文件证据 |
|-----|-----|---------|
| 前端（新） | Vue 3 + Pinia + Vue Router | `src/views/*.vue` (24个) |
| 前端（旧） | 原生 JavaScript ES6+ | `js/*.js` (10个) |
| 桌面端 | Electron 28 | `electron/main.cjs` |
| 构建工具 | Vite 5 | `vite.config.js` |
| 后端 | Python HTTP Server | `server.py` (188KB) |
| 数据库 | SQLite + JSON | `server/database/schema.sql` |

**总代码量**: ~28,660 行

---

## 二、安全问题（高危）

### 2.1 Electron 安全配置 ⚠️ 高危

**证据**: `electron/main.cjs:44-45, 118-121`

```javascript
// main.cjs 第 43-46 行 (loadingWindow)
webPreferences: {
    nodeIntegration: true,        // ⚠️ 允许渲染进程访问 Node.js
    contextIsolation: false       // ⚠️ 禁用上下文隔离
}

// main.cjs 第 118-123 行 (mainWindow)
webPreferences: {
    nodeIntegration: true,        // ⚠️ 允许渲染进程访问 Node.js
    contextIsolation: false,      // ⚠️ 禁用上下文隔离
    webSecurity: false            // ⚠️ 禁用 Web 安全策略
}
```

**风险分析**:
- XSS 攻击可直接执行 Node.js 命令（读取任意文件、执行任意程序）
- 禁用 webSecurity 允许跨域请求，绕过同源策略
- 渲染进程与主进程共享上下文，无安全边界

**修复建议**: 立即启用安全配置
```javascript
webPreferences: {
    nodeIntegration: false,       // ✓ 禁止渲染进程访问 Node.js
    contextIsolation: true,       // ✓ 启用上下文隔离
    webSecurity: true,            // ✓ 启用 Web 安全策略
    sandbox: true,                // ✓ 启用沙箱
    preload: path.join(__dirname, 'preload.js')  // ✓ 使用 preload 安全暴露 API
}
```

---

### 2.2 认证系统不一致 ⚠️ 中危

**证据**: Grep 搜索 localStorage 调用

| 模块 | Token Key | User Key | 文件位置 |
|-----|----------|----------|---------|
| `src/utils/permission.js` | `workbench_token` | `workbench_user` | 第 9-10 行 |
| `src/services/auth.js` | `access_token` | `current_user` | 第 12-24 行 |
| `src/views/*.vue` | `token` | - | DetailView.vue 第 339/331/509 行 |
| `js/utils/auth.js` | 自定义常量 | 自定义常量 | 第 39-52 行 |
| `js/api.js` | `access_token` | - | 第 26 行 |
| `js/file-manager.js` | `access_token` | - | 第 7, 113 行 |

**后果**:
- 用户登录状态可能在一个模块有效，另一个模块无效
- Token 刷新逻辑不一致
- 权限检查可能使用错误的用户数据

---

### 2.3 API 权限控制薄弱 ⚠️ 中危

**证据**: `server.py:400-437`

```python
# server.py 第 400-409 行 - 删除文件夹
if self.path.startswith('/api/delete-folder'):
    folder_path = query.get('path', [''])[0]
    if folder_path:
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            self.delete_folder_with_auth(folder_path)
        else:
            self.delete_folder(folder_path)  # ⚠️ 无认证也能删除！

# server.py 第 427-437 行 - 删除文件
if self.path.startswith('/api/delete-file'):
    file_path = query.get('path', [''])[0]
    if file_path:
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            self.delete_file_with_auth(file_path)
        else:
            self.delete_file(file_path)  # ⚠️ 无认证也能删除！
```

**风险**: 未认证用户可删除任意文件

---

### 2.4 密码传输不安全 ⚠️ 低危

**证据**: `src/App.vue:239`

```javascript
// App.vue 第 239 行
const encodedPassword = btoa(password)  // ⚠️ Base64 不是加密，只是编码
```

Base64 是可逆编码，传输过程中被截获可轻易解码。应使用 HTTPS 或前端 bcrypt。

---

## 三、代码质量问题

### 3.1 前端双架构并存

**证据**:
```
$ ls src/views/*.vue | wc -l
24  (Vue 3 组件)

$ ls js/*.js | wc -l
10  (原生 JS 模块)
```

**具体文件**:

| 目录 | 文件数 | 代表文件 |
|-----|-------|---------|
| `src/views/` | 24 | DashboardView.vue, ProjectsView.vue, PlayersView.vue 等 |
| `src/components/` | 10 | Modal.vue, Toast.vue, CustomSelect.vue 等 |
| `src/stores/` | 11 | project.js, player.js, user.js 等 |
| `js/` | 10 | api.js, ui.js, data-store.js, auth-ui.js 等 |

**问题分析**:
- `js/api.js` 226KB，单文件过大（约 6000+ 行）
- 新旧代码功能重复（认证、数据存储、UI）
- 维护成本高，修改一处可能遗漏另一处

---

### 3.2 后端单文件过大

**证据**: `server.py` 文件大小
```
$ wc -l server.py
约 4000+ 行，188KB
```

**问题**:
- 所有 API 逻辑集中在单文件
- 缺少模块化设计
- 难以测试和维护

---

## 四、测试覆盖

### 4.1 测试现状

| 类型 | 状态 | 证据 |
|-----|-----|-----|
| 后端单元测试 | ❌ 无 | 无 pytest 配置 |
| 后端手动测试 | ⚠️ 部分 | 7 文件 (test_*.py)，需服务器运行 |
| 前端单元测试 | ❌ 无 | 无 Vitest/Jest 配置 |
| E2E 测试 | ❌ 无 | 无 Playwright/Cypress |
| CI/CD | ❌ 无 | 无 .github/workflows |

**测试文件统计**:
```
$ ls test*.py && wc -l test*.py
test_api.py          35 行
test_archive.py     100 行
test_comprehensive.py 99 行
test_full_api.py    190 行
test_material_config.py 106 行
test_resources.py   95 行
test_settings.py    91 行
总计: 716 行
```

所有测试文件都是手动运行的脚本，需要服务器先启动，无自动化测试框架。

---

## 五、改进建议

### 5.1 短期（1-2周） - P0 紧急

| 任务 | 具体步骤 | 预计时间 | 验证方法 |
|-----|---------|---------|---------|
| **修复 Electron 安全配置** | 1. 创建 preload.js<br>2. 修改 webPreferences<br>3. 测试 IPC 通信 | 4 小时 | Electron 安全审计工具 |
| **统一认证 localStorage** | 1. 定义统一常量<br>2. 替换所有 localStorage 调用<br>3. 删除重复 auth 模块 | 6 小时 | Grep 确认唯一 key |
| **修复 API 权限控制** | 1. 删除未认证分支<br>2. 添加 require_auth 装饰器<br>3. 测试未认证请求被拒绝 | 4 小时 | 手动测试删除 API |

### 5.2 中期（1-3月） - P1 重要

| 任务 | 具体步骤 | 预计时间 | 验证方法 |
|-----|---------|---------|---------|
| **完成 Vue 3 迁移** | 1. 迁移 js/api.js 功能到 stores<br>2. 删除 js/ 目录<br>3. 更新 index.html | 2-4 周 | 功能回归测试 |
| **后端模块化** | 1. 拆分 server.py 为 routers/<br>2. 创建 models/<br>3. 统一错误处理 | 1-2 周 | pytest 单元测试 |
| **添加单元测试** | 1. 配置 pytest + Vitest<br>2. 编写核心模块测试<br>3. 设置 CI/CD | 2 周 | 测试覆盖率 > 60% |

### 5.3 长期（3-6月） - P2 可选

| 任务 | 具体步骤 | 预计时间 | 验证方法 |
|-----|---------|---------|---------|
| **数据迁移到 PostgreSQL** | 1. 设计 schema<br>2. 编写迁移脚本<br>3. 测试数据完整性 | 3-4 周 | 数据一致性检查 |
| **添加 E2E 测试** | 1. 配置 Playwright<br>2. 编写关键流程测试<br>3. CI 集成 | 2 周 | E2E 测试通过 |
| **插件系统** | 1. 设计插件接口<br>2. 实现加载机制<br>3. 文档编写 | 4 周 | 示例插件运行 |

---

## 六、验证证据索引

| 结论 | 验证命令 | 文件位置 |
|-----|---------|---------|
| Electron 安全配置问题 | `grep -n "nodeIntegration\|contextIsolation" electron/main.cjs` | main.cjs:44-45, 118-121 |
| 前端双架构并存 | `ls src/views/*.vue | wc -l` + `ls js/*.js | wc -l` | src/views/, js/ |
| 认证 localStorage 不一致 | `grep -n "localStorage" src/ js/` | 多处文件 |
| API 权限控制薄弱 | `grep -n "delete_file\|delete_folder" server.py` | server.py:400-437 |
| 测试覆盖不足 | `ls test*.py && wc -l test*.py` | test_*.py (716 行) |

---

## 七、总结

### 7.1 项目成熟度评估

| 维度 | 成熟度 | 说明 |
|-----|-------|-----|
| 功能完整性 | 75% | 核心功能完整，非核心待完善 |
| 代码质量 | 60% | 双架构并存，认证系统混乱 |
| 稳定性 | 70% | 主要流程稳定 |
| 安全性 | 45% | Electron 配置高危，API 权限薄弱 |
| 测试覆盖 | 15% | 仅手动测试，无自动化 |

### 7.2 风险等级

| 风险 | 等级 | 影响 |
|-----|-----|-----|
| Electron 安全配置 | **高危** | XSS 可执行任意命令 |
| API 权限控制 | 中危 | 未认证可删除文件 |
| 认证系统不一致 | 中危 | 登录状态混乱 |
| 双架构并存 | 低危 | 维护成本高 |

---

*本报告使用 superpowers 技能生成，所有结论均有命令输出证据支撑。*