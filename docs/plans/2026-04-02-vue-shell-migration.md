# 工作台前端壳层升级计划（2026-04-02）

## 目标

- 在 **不改动 `style.css` 与业务视觉契约** 的前提下，完成 Vue 壳与遗留 HTML 的收口。
- 消除 **双壳并存**（同页两套 header/sidebar）导致的布局漂移风险。
- 对齐 **Vite / Electron / wait-on** 开发端口，便于稳定联调。
- 保留 **全局浮层 DOM**（登录框、素材弹窗、`FileManager` / `PlayerUI` 等依赖的 id），与遗留行为一致。

## 布局与样式契约（必须遵守）

- 页面框架仍由 **Vue `App.vue`** 输出：根节点 **`class="app-container"`**，内含 **`app-header` + `sidebar` + `main-content`**，class 名与旧版一致。
- **全局样式唯一来源**：根目录 `style.css`；不在迁移中引入第二套全局布局 CSS。
- **顶栏关键 id**（供 `AuthUI` / 主题 / 通知闭合逻辑使用）：`currentDate`、`themeToggle`、`notificationBell`、`notificationBadge`、`userInfo`、`loginBtn`、`currentUsername`。
- **`toastContainer` 与各类 `modal-overlay`** 留在 **`index.html` 中、位于 `#app` 之外**，与旧版「浮层在壳外」结构一致，避免重复 id。

## 阶段划分

### 阶段 A — 壳层与启动（本次已执行）

1. `index.html` 仅保留：`#app` + 全局 toast/modals + 与原先相同的脚本链。
2. 启动逻辑抽至 `js/workbench-bootstrap.js`：若存在 `#page-dashboard` 则 `UI.init()`（兼容未来若恢复静态页）；否则 **`ThemeUI.init()`** + 全局模块，**不调用** `UI.init()`，避免操作不存在的列表节点。
3. Electron `VITE_DEV_SERVER_PORT` 与 `package.json` 的 `wait-on` 统一为 **3004**（与 `vite.config.js` 一致）。

### 阶段 B — 可选回归与自动化（后续）

- 对 `/`、`/projects` 等路由做 **截图基线**（Playwright），防止后续改 `App.vue` 时 class 被误删。
- 将 `scripts/splice-index-vue-shell.ps1` 仅为应急工具；正常维护下 `index.html` 已为小模板，一般不再需要拼接。

### 阶段 C — 长期

- `preload` + `contextBridge` 收紧 Electron 暴露 API。
- ESLint 覆盖 `src/**/*.vue`。

## 验收清单

- [ ] `npm run dev`：页面单壳、侧栏与主栏布局正常。
- [ ] `npm run electron:dev`：能打开 `http://localhost:3004` 且接口代理正常。
- [ ] 登录 / 通知角标 / 主题切换：无控制台报错。
- [ ] `npm run build` 通过，`dist/index.html` 含 `#app` 与全局浮层脚本引用。

## 回滚说明若需要恢复旧静态大页

1. 从 Git 恢复升级前的 `index.html`。
2. 将 `js/workbench-bootstrap.js` 的引用改回内联启动脚本或删除该文件引用。
3. Electron 端口若曾修改，一并恢复。
