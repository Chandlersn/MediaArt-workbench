# 个人工作台安全与质量修复 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Electron 安全配置、统一认证系统、加强 API 权限控制，提升项目安全性和代码质量

**Architecture:** 采用渐进式修复策略，先解决高危安全问题（P0），再处理代码架构问题（P1），最后完成长期优化（P2）

**Tech Stack:** Electron 28, Vue 3, Python HTTP Server, SQLite

---

## 文件结构映射

### P0 任务涉及的文件

| 文件 | 操作 | 负责内容 |
|-----|-----|---------|
| `electron/preload.js` | 创建 | 安全暴露 IPC API |
| `electron/main.cjs` | 修改 | 启用安全配置 |
| `src/utils/auth-constants.js` | 创建 | 统一认证常量 |
| `src/utils/permission.js` | 修改 | 使用统一常量 |
| `src/services/auth.js` | 修改 | 使用统一常量 |
| `src/services/http.js` | 修改 | 使用统一常量 |
| `src/views/ProjectDetailView.vue` | 修改 | 使用统一常量 |
| `src/views/OrganizationDetailView.vue` | 修改 | 使用统一常量 |
| `src/views/PlayerDetailView.vue` | 修改 | 使用统一常量 |
| `server.py` | 修改 | 删除未认证 API 分支 |

---

## P0 任务：紧急安全修复

---

### Task 1: 创建 Electron preload.js（安全 IPC 暴露）

**Files:**
- Create: `electron/preload.js`

**依赖:** 无

**预计时间:** 30 分钟

- [ ] **Step 1: 创建 preload.js 文件**

```javascript
// electron/preload.js
// 安全暴露 Electron IPC API 到渲染进程

const { contextBridge, ipcRenderer } = require('electron');

// 只暴露必要的 API，不暴露整个 Node.js
contextBridge.exposeInMainWorld('electronAPI', {
  // 文件系统操作（受限）
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  
  // 安全的路径解析（不暴露 path 模块）
  resolvePath: (relativePath) => ipcRenderer.invoke('resolve-path', relativePath),
  
  // 应用信息
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  isPackaged: () => ipcRenderer.invoke('is-packaged'),
  
  // 平台信息
  platform: process.platform,
  
  // 安全的事件监听（不暴露完整 ipcRenderer）
  onServerReady: (callback) => {
    ipcRenderer.on('server-ready', (event, data) => callback(data));
  }
});
```

- [ ] **Step 2: 验证 preload.js 文件创建成功**

Run: `ls -la electron/preload.js`
Expected: 文件存在，大小约 500-800 bytes

- [ ] **Step 3: Commit preload.js**

```bash
git add electron/preload.js
git commit -m "security: create preload.js for safe IPC exposure"
```

---

### Task 2: 修复 Electron main.cjs 安全配置

**Files:**
- Modify: `electron/main.cjs:43-46` (loadingWindow)
- Modify: `electron/main.cjs:118-123` (mainWindow)

**依赖:** Task 1 (preload.js)

**预计时间:** 45 分钟

- [ ] **Step 1: 修改 loadingWindow 的 webPreferences**

找到 `electron/main.cjs` 第 43-46 行，替换为：

```javascript
// main.cjs 第 43-46 行（loadingWindow）
webPreferences: {
    nodeIntegration: false,      // 禁止渲染进程访问 Node.js
    contextIsolation: true,      // 启用上下文隔离
    sandbox: true,               // 启用沙箱
    preload: path.join(__dirname, 'preload.js')
}
```

- [ ] **Step 2: 修改 mainWindow 的 webPreferences**

找到 `electron/main.cjs` 第 118-123 行，替换为：

```javascript
// main.cjs 第 118-123 行（mainWindow）
webPreferences: {
    nodeIntegration: false,      // 禁止渲染进程访问 Node.js
    contextIsolation: true,      // 启用上下文隔离
    sandbox: true,               // 启用沙箱
    webSecurity: true,           // 启用 Web 安全策略
    backgroundThrottling: false,
    preload: path.join(__dirname, 'preload.js')
}
```

- [ ] **Step 3: 添加 IPC handlers（补充 preload 需要的 API）**

在 `electron/main.cjs` 文件末尾（约 418 行后）添加：

```javascript
// ========== IPC Handlers for preload.js ==========

ipcMain.handle('get-app-version', async () => {
    return app.getVersion();
});

ipcMain.handle('is-packaged', async () => {
    return app.isPackaged;
});

ipcMain.handle('resolve-path', async (event, relativePath) => {
    const basePath = getBasePath();
    return path.join(basePath, relativePath);
});
```

- [ ] **Step 4: 添加 preload.js require 路径处理**

确保文件顶部有 `path` 模块引入（已有）：

```javascript
const path = require('path');  // 第 2 行已有
```

- [ ] **Step 5: 验证修改正确**

Run: `grep -n "nodeIntegration\|contextIsolation\|webSecurity\|preload" electron/main.cjs`
Expected:
```
43:            nodeIntegration: false,
44:            contextIsolation: true,
45:            sandbox: true,
46:            preload: path.join(__dirname, 'preload.js')
118:            nodeIntegration: false,
119:            contextIsolation: true,
120:            sandbox: true,
121:            webSecurity: true,
122:            preload: path.join(__dirname, 'preload.js')
```

- [ ] **Step 6: Commit 安全配置修复**

```bash
git add electron/main.cjs
git commit -m "security: enable contextIsolation, disable nodeIntegration, add preload"
```

---

### Task 3: 创建统一认证常量文件

**Files:**
- Create: `src/utils/auth-constants.js`

**依赖:** 无

**预计时间:** 15 分钟

- [ ] **Step 1: 创建 auth-constants.js**

```javascript
// src/utils/auth-constants.js
/**
 * 认证系统统一常量
 * 所有模块必须使用这些常量，禁止硬编码 localStorage key
 */

// Token 存储 key
export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'workbench_access_token',
  REFRESH_TOKEN: 'workbench_refresh_token',
  USER_INFO: 'workbench_user',
  TOKEN_EXPIRES: 'workbench_token_expires',
  THEME: 'theme'
};

// 认证相关常量
export const AUTH_CONSTANTS = {
  // Token 刷新阈值（毫秒）
  REFRESH_THRESHOLD: 30 * 60 * 1000,  // 30 分钟
  
  // Token 默认有效期（秒）
  DEFAULT_EXPIRES_IN: 24 * 60 * 60,  // 24 小时
  
  // 角色等级
  ROLE_HIERARCHY: {
    admin: 100,
    editor: 50,
    viewer: 10
  }
};

// 获取 Token
export function getAccessToken() {
  return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
}

// 获取刷新 Token
export function getRefreshToken() {
  return localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
}

// 获取用户信息
export function getUserInfo() {
  const userStr = localStorage.getItem(STORAGE_KEYS.USER_INFO);
  if (!userStr) return null;
  try {
    return JSON.parse(userStr);
  } catch {
    return null;
  }
}

// 保存认证数据
export function saveAuthData(accessToken, refreshToken, expiresIn, user) {
  localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, accessToken);
  localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
  
  const expiresAt = Date.now() + expiresIn * 1000;
  localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRES, expiresAt.toString());
  
  if (user) {
    localStorage.setItem(STORAGE_KEYS.USER_INFO, JSON.stringify(user));
  }
}

// 清除认证数据
export function clearAuthData() {
  localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.USER_INFO);
  localStorage.removeItem(STORAGE_KEYS.TOKEN_EXPIRES);
}

// 检查是否已登录
export function isLoggedIn() {
  return !!getAccessToken() && !!getUserInfo();
}

// 检查 Token 是否即将过期
export function isTokenExpiringSoon() {
  const expiresAt = parseInt(localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRES) || '0');
  if (!expiresAt) return true;
  return expiresAt - Date.now() < AUTH_CONSTANTS.REFRESH_THRESHOLD;
}
```

- [ ] **Step 2: 验证文件创建**

Run: `ls -la src/utils/auth-constants.js`
Expected: 文件存在，大小约 1-2KB

- [ ] **Step 3: Commit 认证常量文件**

```bash
git add src/utils/auth-constants.js
git commit -m "refactor: create unified auth constants module"
```

---

### Task 4: 更新 src/utils/permission.js 使用统一常量

**Files:**
- Modify: `src/utils/permission.js`

**依赖:** Task 3 (auth-constants.js)

**预计时间:** 20 分钟

- [ ] **Step 1: 重写 permission.js 使用统一常量**

完全替换 `src/utils/permission.js` 内容：

```javascript
/**
 * 权限管理模块 (ES Module)
 * 提供权限检查、路由守卫等功能
 * 使用 auth-constants.js 统一常量
 */

import {
  STORAGE_KEYS,
  AUTH_CONSTANTS,
  getAccessToken,
  getUserInfo,
  isLoggedIn,
  saveAuthData,
  clearAuthData
} from './auth-constants';

// 角色对应的权限列表
const ROLE_PERMISSIONS = {
  admin: ['create', 'read', 'update', 'delete', 'manage_users', 'manage_config'],
  editor: ['create', 'read', 'update'],
  viewer: ['read']
};

// 角色显示名称
const ROLE_DISPLAY_NAMES = {
  admin: '管理员',
  editor: '编辑者',
  viewer: '查看者'
};

// 权限显示名称
const PERMISSION_DISPLAY_NAMES = {
  create: '创建',
  read: '读取',
  update: '更新',
  delete: '删除',
  manage_users: '用户管理',
  manage_config: '配置管理'
};

// ========== 认证相关（使用统一常量） ==========

// 直接导出 auth-constants 的函数
export { isLoggedIn, getAccessToken, getUserInfo, saveAuthData, clearAuthData };

export const getCurrentUser = getUserInfo;

export const setAuthData = saveAuthData;

export const clearAuthDataLocal = clearAuthData;

// ========== 角色与权限检查 ==========

export const hasRole = (role) => {
  const user = getUserInfo();
  if (!user) return false;
  const currentLevel = AUTH_CONSTANTS.ROLE_HIERARCHY[user.role] || 0;
  const requiredLevel = AUTH_CONSTANTS.ROLE_HIERARCHY[role] || 0;
  return currentLevel >= requiredLevel;
};

export const hasPermission = (permission) => {
  const user = getUserInfo();
  if (!user) return false;
  const permissions = ROLE_PERMISSIONS[user.role] || ROLE_PERMISSIONS.viewer;
  return permissions.includes(permission);
};

export const hasAnyPermission = (permissions) => {
  return permissions.some(p => hasPermission(p));
};

export const hasAllPermissions = (permissions) => {
  return permissions.every(p => hasPermission(p));
};

export const isAdmin = () => {
  return getUserInfo()?.role === 'admin';
};

export const isEditorOrAbove = () => {
  return hasRole('editor');
};

// ========== 显示名称 ==========

export const getRoleDisplayName = (role) => {
  return ROLE_DISPLAY_NAMES[role] || role;
};

export const getPermissionDisplayName = (permission) => {
  return PERMISSION_DISPLAY_NAMES[permission] || permission;
};

export const getRoleLevel = (role) => {
  return AUTH_CONSTANTS.ROLE_HIERARCHY[role] || 0;
};

export const getRolePermissions = (role) => {
  return ROLE_PERMISSIONS[role] || ROLE_PERMISSIONS.viewer;
};

// ========== 常量导出 ==========

export { STORAGE_KEYS, AUTH_CONSTANTS, ROLE_PERMISSIONS, ROLE_DISPLAY_NAMES, PERMISSION_DISPLAY_NAMES };
```

- [ ] **Step 2: 验证 permission.js 导入正确**

Run: `grep -n "from './auth-constants'" src/utils/permission.js`
Expected: 第 10-17 行有导入语句

- [ ] **Step 3: Commit permission.js 更新**

```bash
git add src/utils/permission.js
git commit -m "refactor: update permission.js to use unified auth constants"
```

---

### Task 5: 更新 src/services/auth.js 使用统一常量

**Files:**
- Modify: `src/services/auth.js`

**依赖:** Task 3 (auth-constants.js), Task 4 (permission.js)

**预计时间:** 25 分钟

- [ ] **Step 1: 重写 auth.js 使用统一常量**

完全替换 `src/services/auth.js` 内容：

```javascript
/**
 * JWT Token 认证管理模块
 * 使用 auth-constants.js 统一常量
 */

import {
  STORAGE_KEYS,
  AUTH_CONSTANTS,
  getAccessToken,
  getRefreshToken,
  getUserInfo,
  saveAuthData,
  clearAuthData,
  isLoggedIn,
  isTokenExpiringSoon
} from '../utils/auth-constants';

const API_BASE = '';

// 直接导出 auth-constants 的函数
export {
  getAccessToken,
  getRefreshToken,
  getUserInfo,
  saveUser as saveAuthData,
  clearAuth as clearAuthData,
  isAuthenticated as isLoggedIn,
  isTokenExpiringSoon
};

// 兼容旧 API 的别名
export function saveUser(user) {
  localStorage.setItem(STORAGE_KEYS.USER_INFO, JSON.stringify(user));
}

export function saveTokens(accessToken, refreshToken, expiresIn) {
  localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, accessToken);
  localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
  
  const expiresAt = Date.now() + expiresIn * 1000;
  localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRES, expiresAt.toString());
}

export function isAuthenticated() {
  return isLoggedIn();
}

export function clearAuth() {
  clearAuthData();
}

/**
 * 刷新 Token
 */
export async function refreshToken() {
  const refreshToken = getRefreshToken();
  
  if (!refreshToken) {
    clearAuthData();
    throw new Error('没有刷新 Token');
  }
  
  try {
    const response = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    
    const data = await response.json();
    
    if (data.success) {
      saveAuthData(data.access_token, data.refresh_token, data.expires_in, data.user);
      console.log('Token 刷新成功');
      return data;
    } else {
      clearAuthData();
      throw new Error(data.message || 'Token 刷新失败');
    }
  } catch (error) {
    console.error('Token 刷新失败:', error);
    clearAuthData();
    throw error;
  }
}

/**
 * 验证 Token
 */
export async function verifyToken() {
  const token = getAccessToken();
  
  if (!token) {
    throw new Error('没有访问 Token');
  }
  
  try {
    const response = await fetch(`${API_BASE}/api/auth/verify`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      return data;
    } else {
      if (data.error === 'INVALID_OR_EXPIRED_TOKEN') {
        console.log('Token 已过期，尝试刷新...');
        return await refreshToken();
      }
      throw new Error(data.message || 'Token 验证失败');
    }
  } catch (error) {
    console.error('Token 验证失败:', error);
    throw error;
  }
}

/**
 * 登录
 */
export async function login(username, password) {
  try {
    const response = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ username, password })
    });
    
    const data = await response.json();
    
    if (data.success) {
      saveAuthData(data.access_token, data.refresh_token, data.expires_in, data.user);
      console.log('登录成功:', data.user.username);
      return data;
    } else {
      throw new Error(data.message || '登录失败');
    }
  } catch (error) {
    console.error('登录失败:', error);
    throw error;
  }
}

/**
 * 登出
 */
export function logout() {
  clearAuthData();
  console.log('已登出');
}

/**
 * 初始化认证管理器
 */
export function initAuthManager() {
  checkAndRefreshToken();
  
  setInterval(() => {
    checkAndRefreshToken();
  }, 5 * 60 * 1000);
}

async function checkAndRefreshToken() {
  if (!isLoggedIn()) return;
  
  if (isTokenExpiringSoon()) {
    console.log('Token 即将过期，尝试刷新...');
    try {
      await refreshToken();
    } catch (e) {
      console.warn('Token 刷新失败:', e);
    }
  }
}
```

- [ ] **Step 2: 验证 auth.js 导入正确**

Run: `grep -n "from '../utils/auth-constants'" src/services/auth.js`
Expected: 第 10-19 行有导入语句

- [ ] **Step 3: Commit auth.js 更新**

```bash
git add src/services/auth.js
git commit -m "refactor: update auth.js to use unified auth constants"
```

---

### Task 6: 更新 src/services/http.js 使用统一常量

**Files:**
- Modify: `src/services/http.js:8`

**依赖:** Task 3 (auth-constants.js)

**预计时间:** 10 分钟

- [ ] **Step 1: 修改 http.js 的 Token 获取**

找到 `src/services/http.js` 第 8 行，修改为使用统一常量：

```javascript
// src/services/http.js
import { getAccessToken } from '../utils/auth-constants';

/**
 * HTTP 请求封装
 */
export async function fetchWithAuth(url, options = {}) {
  const token = getAccessToken();
  
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(url, {
    ...options,
    headers
  });
  
  if (response.status === 401) {
    throw new Error('请先登录');
  }
  
  if (response.status === 403) {
    throw new Error('权限不足');
  }
  
  return response;
}

export async function get(url) {
  return fetchWithAuth(url, { method: 'GET' });
}

export async function post(url, data) {
  return fetchWithAuth(url, {
    method: 'POST',
    body: JSON.stringify(data)
  });
}

export async function put(url, data) {
  return fetchWithAuth(url, {
    method: 'PUT',
    body: JSON.stringify(data)
  });
}

export async function deleteRequest(url) {
  return fetchWithAuth(url, { method: 'DELETE' });
}
```

- [ ] **Step 2: 验证 http.js 更新**

Run: `grep -n "getAccessToken" src/services/http.js`
Expected: 第 2 行导入，第 8 行使用

- [ ] **Step 3: Commit http.js 更新**

```bash
git add src/services/http.js
git commit -m "refactor: update http.js to use unified auth constants"
```

---

### Task 7: 更新 DetailView.vue 文件使用统一常量

**Files:**
- Modify: `src/views/ProjectDetailView.vue:339`
- Modify: `src/views/OrganizationDetailView.vue:331`
- Modify: `src/views/PlayerDetailView.vue:509`

**依赖:** Task 3 (auth-constants.js)

**预计时间:** 20 分钟

- [ ] **Step 1: 修改 ProjectDetailView.vue**

找到第 339 行左右的 `localStorage.getItem('token')`，替换为：

```javascript
// ProjectDetailView.vue - 在 script setup 顶部添加导入
import { getAccessToken } from '../utils/auth-constants';

// 替换原来的代码
// 旧代码: const token = localStorage.getItem('token')
// 新代码:
const token = getAccessToken();
```

- [ ] **Step 2: 修改 OrganizationDetailView.vue**

找到第 331 行左右的 `localStorage.getItem('token')`，替换为：

```javascript
// OrganizationDetailView.vue - 在 script setup 顶部添加导入
import { getAccessToken } from '../utils/auth-constants';

// 替换原来的代码
const token = getAccessToken();
```

- [ ] **Step 3: 修改 PlayerDetailView.vue**

找到第 509 行左右的 `localStorage.getItem('token')`，替换为：

```javascript
// PlayerDetailView.vue - 在 script setup 顶部添加导入
import { getAccessToken } from '../utils/auth-constants';

// 替换原来的代码
const token = getAccessToken();
```

- [ ] **Step 4: 验证所有 DetailView 文件已更新**

Run: `grep -n "localStorage.getItem('token')" src/views/*.vue`
Expected: 无输出（所有硬编码 'token' 已被替换）

Run: `grep -n "getAccessToken" src/views/*.vue`
Expected: 3 个文件各有导入和使用

- [ ] **Step 5: Commit DetailView 文件更新**

```bash
git add src/views/ProjectDetailView.vue src/views/OrganizationDetailView.vue src/views/PlayerDetailView.vue
git commit -m "refactor: update DetailView files to use unified auth constants"
```

---

### Task 8: 修复 server.py API 权限控制

**Files:**
- Modify: `server.py:400-437`

**依赖:** 无

**预计时间:** 30 分钟

- [ ] **Step 1: 修改 delete-folder API（server.py 约 400-409 行）**

找到 `server.py` 中处理 `/api/delete-folder` 的代码块，替换为：

```python
# server.py - delete-folder API（约第 400-409 行）
if self.path.startswith('/api/delete-folder'):
    # 删除文件夹 - 必须认证
    query = parse_qs(parsed.query)
    folder_path = query.get('path', [''])[0]
    if folder_path:
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            self.delete_folder_with_auth(folder_path)
        else:
            # 拒绝未认证请求
            self.send_error_response(401, '请先登录')
    return
```

- [ ] **Step 2: 修改 delete-file API（server.py 约 427-437 行）**

找到 `server.py` 中处理 `/api/delete-file` 的代码块，替换为：

```python
# server.py - delete-file API（约第 427-437 行）
if self.path.startswith('/api/delete-file'):
    # 删除文件 - 必须认证
    query = parse_qs(parsed.query)
    file_path = query.get('path', [''])[0]
    if file_path:
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            self.delete_file_with_auth(file_path)
        else:
            # 拒绝未认证请求
            self.send_error_response(401, '请先登录')
    return
```

- [ ] **Step 3: 添加 send_error_response 辅助方法**

在 `WorkbenchHandler` 类中添加（约第 310 行后）：

```python
# server.py - 添加 send_error_response 方法
def send_error_response(self, code, message):
    """发送 JSON 格式的错误响应"""
    self.send_response(code)
    self.send_header('Content-type', 'application/json; charset=utf-8')
    self.end_headers()
    error_msg = json.dumps({
        'success': False,
        'error': str(code),
        'message': str(message)
    }, ensure_ascii=False)
    self.wfile.write(error_msg.encode('utf-8'))
```

- [ ] **Step 4: 验证修改正确**

Run: `grep -n "self.delete_folder\|self.delete_file" server.py`
Expected: 只有 `delete_folder_with_auth` 和 `delete_file_with_auth` 被调用，没有未认证分支

- [ ] **Step 5: Commit API 权限修复**

```bash
git add server.py
git commit -m "security: require authentication for delete-folder and delete-file APIs"
```

---

### Task 9: 更新 router/index.js 使用统一常量

**Files:**
- Modify: `src/router/index.js:207-208`

**依赖:** Task 3 (auth-constants.js), Task 4 (permission.js)

**预计时间:** 10 分钟

- [ ] **Step 1: 修改 router/index.js 的权限守卫**

找到 `src/router/index.js` 第 186-236 行的 `router.beforeEach`，更新使用统一常量：

```javascript
// src/router/index.js - 第 186-236 行
import { isLoggedIn, hasPermission, hasAnyPermission, getUserInfo } from '../utils/auth-constants';

router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title || '媒体艺术智能工作台'}`;

  // 权限守卫：仅在路由 meta 中标记了 requiresAuth 时才检查
  if (to.meta.requiresAuth) {
    // 检查是否已登录（使用统一函数）
    if (!isLoggedIn()) {
      const loginRoute = routes.find(r => r.name === 'Login');
      if (loginRoute) {
        next({ name: 'Login', query: { redirect: to.fullPath } });
      } else {
        console.warn('[权限守卫] 访问需要登录的页面，但当前未登录且无登录页');
        next();
      }
      return;
    }

    // 检查角色权限（使用统一函数）
    if (to.meta.roles && to.meta.roles.length > 0) {
      const user = getUserInfo();
      const userRole = user?.role || null;
      if (!to.meta.roles.includes(userRole)) {
        console.warn('[权限守卫] 角色权限不足，跳转到首页');
        next({ path: '/' });
        return;
      }
    }

    // 检查具体权限（使用统一函数）
    if (to.meta.permission) {
      if (!hasPermission(to.meta.permission)) {
        console.warn('[权限守卫] 缺少权限:', to.meta.permission, '，跳转到首页');
        next({ path: '/' });
        return;
      }
    }

    if (to.meta.permissions && to.meta.permissions.length > 0) {
      if (!hasAnyPermission(to.meta.permissions)) {
        console.warn('[权限守卫] 缺少权限:', to.meta.permissions, '，跳转到首页');
        next({ path: '/' });
        return;
      }
    }
  }

  next();
});
```

- [ ] **Step 2: 验证 router 更新**

Run: `grep -n "localStorage.getItem" src/router/index.js`
Expected: 无输出（已使用统一函数）

- [ ] **Step 3: Commit router 更新**

```bash
git add src/router/index.js
git commit -m "refactor: update router to use unified auth functions"
```

---

### Task 10: 清理旧 js/ 目录中的认证代码（可选）

**Files:**
- Modify: `js/utils/auth.js`
- Modify: `js/api.js`
- Modify: `js/file-manager.js`

**依赖:** Task 3-9 完成

**预计时间:** 30 分钟

**注意:** 此任务为可选，因为 `js/` 目录最终会被删除。但为了过渡期的兼容性，建议更新。

- [ ] **Step 1: 更新 js/utils/auth.js 使用统一常量**

在文件顶部添加注释和兼容层：

```javascript
// js/utils/auth.js
// 注意：此文件已废弃，请使用 src/utils/auth-constants.js
// 此文件仅作为过渡兼容保留

// 导入统一常量（通过全局 window 对象，因为 js/ 不支持 ES Module）
// 在 Vue 应用启动后，window.authConstants 可用
const AUTH_KEYS = {
  ACCESS_TOKEN: 'workbench_access_token',
  REFRESH_TOKEN: 'workbench_refresh_token',
  USER_INFO: 'workbench_user',
  TOKEN_EXPIRES: 'workbench_token_expires'
};

// 兼容旧 API
function getAccessToken() {
  return localStorage.getItem(AUTH_KEYS.ACCESS_TOKEN);
}

function getRefreshToken() {
  return localStorage.getItem(AUTH_KEYS.REFRESH_TOKEN);
}

function getUserInfo() {
  const userStr = localStorage.getItem(AUTH_KEYS.USER_INFO);
  return userStr ? JSON.parse(userStr) : null;
}

// 导出兼容接口
window.AuthCompat = {
  getAccessToken,
  getRefreshToken,
  getUserInfo,
  AUTH_KEYS
};
```

- [ ] **Step 2: 更新 js/api.js 第 26 行**

```javascript
// js/api.js 第 26 行
const token = localStorage.getItem('workbench_access_token');  // 使用统一 key
```

- [ ] **Step 3: 更新 js/file-manager.js 第 7, 113 行**

```javascript
// js/file-manager.js 第 7 行
const token = localStorage.getItem('workbench_access_token');

// js/file-manager.js 第 113 行
const token = localStorage.getItem('workbench_access_token');
```

- [ ] **Step 4: 验证旧文件已更新**

Run: `grep -n "localStorage.getItem('access_token')" js/*.js`
Expected: 无输出（已替换为统一 key）

- [ ] **Step 5: Commit 旧文件兼容更新**

```bash
git add js/utils/auth.js js/api.js js/file-manager.js
git commit -m "compat: update legacy js files to use unified auth keys"
```

---

## P1 任务：代码架构改进（后续计划）

由于 P1 任务涉及大规模重构，建议在 P0 任务完成后单独制定计划。

### P1 任务概览

| 任务 | 预计时间 | 主要工作 |
|-----|---------|---------|
| Vue 3 迁移完成 | 2-4 周 | 删除 js/ 目录，迁移功能到 stores |
| 后端模块化 | 1-2 周 | 拆分 server.py 为 routers/, models/ |
| 添加单元测试 | 2 周 | 配置 pytest + Vitest，编写核心测试 |
| 添加 CI/CD | 1 周 | GitHub Actions 自动化测试 |

---

## 验证检查清单

完成所有 P0 任务后，运行以下验证：

- [ ] **验证 1: Electron 安全配置**

```bash
grep -E "nodeIntegration.*false|contextIsolation.*true|webSecurity.*true" electron/main.cjs
```
Expected: 3 处匹配（loadingWindow 和 mainWindow）

- [ ] **验证 2: 认证 localStorage 统一**

```bash
grep -rn "localStorage.getItem.*token" src/
```
Expected: 全部使用 `getAccessToken()` 或 `STORAGE_KEYS.ACCESS_TOKEN`

- [ ] **验证 3: API 权限控制**

```bash
grep -n "self.delete_folder\(" server.py
```
Expected: 无输出（只有 `delete_folder_with_auth` 被调用）

- [ ] **验证 4: preload.js 存在**

```bash
ls electron/preload.js
```
Expected: 文件存在

- [ ] **验证 5: 构建测试**

```bash
npm run build
```
Expected: 构建成功，无错误

---

## 总结

**P0 任务完成后的预期状态:**

1. Electron 安全配置修复 - 高危漏洞已解决
2. 认证系统统一 - localStorage key 一致
3. API 权限控制加强 - 删除操作必须认证
4. preload.js 创建 - 安全 IPC 暴露机制

**下一步:** 执行 P1 任务（Vue 3 迁移、后端模块化、单元测试）

---

*此计划由 superpowers:writing-plans 技能生成*