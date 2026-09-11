# 前端架构重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将现有的单体前端架构重构为模块化架构，提升代码可维护性和可扩展性

**Architecture:** 采用 ES6 模块化设计，创建核心基础设施（事件总线、状态管理器、路由管理器），将现有 UI 组件重构为独立模块，通过事件驱动实现模块间通信

**Tech Stack:** ES6 Modules, Event-Driven Architecture, State Management Pattern, Module Loader

---

## 当前架构分析

### 现有文件结构
```
js/
├── api.js              # API 封装（约 200KB）
├── ui.js               # 主 UI 控制器（约 1500 行）
├── data-store.js       # 数据存储（约 1900 行）
├── archive-manager.js  # 归档管理
├── auth-ui.js          # 认证 UI
├── batch-operations.js # 批量操作
├── cleanup-ui.js       # 清理 UI
├── custom-select.js    # 自定义选择器
├── file-manager.js     # 文件管理
├── components/         # 组件目录
│   └── virtual-list.js
└── utils/              # 工具目录
    ├── auth.js
    ├── component-cache.js
    ├── crypto.js
    ├── dom-optimizer.js
    ├── form-validator.js
    ├── incremental-store.js
    ├── lazy-load.js
    ├── permission.js
    ├── preloader.js
    ├── validator.js
    └── xss.js
```

### 现有问题
1. **全局命名空间污染** - 所有模块都在全局作用域
2. **紧耦合** - UI、数据、业务逻辑混合在一起
3. **缺乏模块化** - 无法按需加载
4. **状态管理混乱** - 状态分散在各个模块中
5. **测试困难** - 模块间依赖关系不清晰

---

## Task 1: 创建核心目录结构

**Files:**
- Create: `js/core/` 目录
- Create: `js/modules/` 目录

**Step 1: 创建目录结构**

```bash
mkdir -p js/core
mkdir -p js/modules
mkdir -p js/modules/projects
mkdir -p js/modules/organizations
mkdir -p js/modules/players
mkdir -p js/modules/finance
mkdir -p js/modules/archive
mkdir -p js/modules/resources
mkdir -p js/modules/settings
mkdir -p js/modules/auth
mkdir -p js/modules/common
```

**Step 2: 验证目录创建**

Run: `ls -la js/`
Expected: 看到 core 和 modules 目录

**Step 3: Commit**

```bash
git add js/core js/modules
git commit -m "chore: create core and modules directory structure"
```

---

## Task 2: 创建事件总线 (Event Bus)

**Files:**
- Create: `js/core/event-bus.js`

**Step 1: 编写事件总线代码**

```javascript
/**
 * 事件总线 - 模块间通信的核心
 * 支持发布/订阅模式，实现模块间解耦
 */
export class EventBus {
    constructor() {
        this.events = new Map();
        this.onceEvents = new Map();
        this.eventHistory = [];
        this.maxHistorySize = 100;
    }

    /**
     * 订阅事件
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     * @param {Object} options - 配置选项
     * @returns {Function} 取消订阅函数
     */
    on(event, callback, options = {}) {
        if (!this.events.has(event)) {
            this.events.set(event, []);
        }

        const listener = {
            callback,
            priority: options.priority || 0,
            once: false,
            context: options.context || null
        };

        this.events.get(event).push(listener);

        // 按优先级排序
        this.events.get(event).sort((a, b) => b.priority - a.priority);

        // 返回取消订阅函数
        return () => this.off(event, callback);
    }

    /**
     * 订阅一次性事件
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     * @returns {Function} 取消订阅函数
     */
    once(event, callback) {
        if (!this.events.has(event)) {
            this.events.set(event, []);
        }

        const listener = {
            callback,
            priority: 0,
            once: true,
            context: null
        };

        this.events.get(event).push(listener);

        return () => this.off(event, callback);
    }

    /**
     * 取消订阅
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     */
    off(event, callback) {
        if (!this.events.has(event)) return;

        const listeners = this.events.get(event);
        const index = listeners.findIndex(l => l.callback === callback);

        if (index !== -1) {
            listeners.splice(index, 1);
        }

        if (listeners.length === 0) {
            this.events.delete(event);
        }
    }

    /**
     * 发布事件
     * @param {string} event - 事件名称
     * @param {*} data - 事件数据
     * @returns {Promise<Array>} 所有回调的返回值
     */
    async emit(event, data) {
        // 记录事件历史
        this.recordEvent(event, data);

        if (!this.events.has(event)) {
            return [];
        }

        const listeners = this.events.get(event);
        const results = [];
        const toRemove = [];

        for (const listener of listeners) {
            try {
                const result = await listener.callback(data);
                results.push(result);

                if (listener.once) {
                    toRemove.push(listener);
                }
            } catch (error) {
                console.error(`EventBus: Error in listener for "${event}"`, error);
            }
        }

        // 移除一次性监听器
        toRemove.forEach(listener => {
            this.off(event, listener.callback);
        });

        return results;
    }

    /**
     * 同步发布事件
     * @param {string} event - 事件名称
     * @param {*} data - 事件数据
     */
    emitSync(event, data) {
        this.recordEvent(event, data);

        if (!this.events.has(event)) return;

        const listeners = this.events.get(event);
        const toRemove = [];

        for (const listener of listeners) {
            try {
                listener.callback(data);

                if (listener.once) {
                    toRemove.push(listener);
                }
            } catch (error) {
                console.error(`EventBus: Error in listener for "${event}"`, error);
            }
        }

        toRemove.forEach(listener => {
            this.off(event, listener.callback);
        });
    }

    /**
     * 记录事件历史
     */
    recordEvent(event, data) {
        this.eventHistory.push({
            event,
            data,
            timestamp: Date.now()
        });

        if (this.eventHistory.length > this.maxHistorySize) {
            this.eventHistory.shift();
        }
    }

    /**
     * 获取事件历史
     * @param {string} event - 事件名称（可选）
     * @returns {Array} 事件历史
     */
    getHistory(event) {
        if (event) {
            return this.eventHistory.filter(e => e.event === event);
        }
        return [...this.eventHistory];
    }

    /**
     * 清除所有事件监听器
     */
    clear() {
        this.events.clear();
        this.eventHistory = [];
    }

    /**
     * 获取事件统计信息
     */
    getStats() {
        return {
            eventCount: this.events.size,
            totalListeners: Array.from(this.events.values())
                .reduce((sum, listeners) => sum + listeners.length, 0),
            historySize: this.eventHistory.length
        };
    }
}

// 预定义的事件类型
export const Events = {
    // 数据事件
    DATA_LOADED: 'data:loaded',
    DATA_SAVED: 'data:saved',
    DATA_CHANGED: 'data:changed',

    // 实体事件
    ENTITY_CREATED: 'entity:created',
    ENTITY_UPDATED: 'entity:updated',
    ENTITY_DELETED: 'entity:deleted',

    // UI 事件
    UI_PAGE_CHANGED: 'ui:pageChanged',
    UI_MODAL_OPEN: 'ui:modalOpen',
    UI_MODAL_CLOSE: 'ui:modalClose',
    UI_TOAST: 'ui:toast',

    // 认证事件
    AUTH_LOGIN: 'auth:login',
    AUTH_LOGOUT: 'auth:logout',
    AUTH_SESSION_EXPIRED: 'auth:sessionExpired',

    // 文件事件
    FILE_UPLOADED: 'file:uploaded',
    FILE_DELETED: 'file:deleted',

    // 归档事件
    ARCHIVE_CREATED: 'archive:created',
    ARCHIVE_DELETED: 'archive:deleted',

    // 通知事件
    NOTIFICATION_NEW: 'notification:new',
    NOTIFICATION_READ: 'notification:read',

    // 模块事件
    MODULE_LOADED: 'module:loaded',
    MODULE_UNLOADED: 'module:unloaded'
};

// 创建全局单例
export const eventBus = new EventBus();

// 兼容旧代码的全局访问
if (typeof window !== 'undefined') {
    window.EventBus = EventBus;
    window.eventBus = eventBus;
    window.Events = Events;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/core/`
Expected: 看到 event-bus.js 文件

**Step 3: Commit**

```bash
git add js/core/event-bus.js
git commit -m "feat(core): add EventBus for module communication"
```

---

## Task 3: 创建状态管理器 (State Manager)

**Files:**
- Create: `js/core/state-manager.js`

**Step 1: 编写状态管理器代码**

```javascript
/**
 * 状态管理器 - 集中管理应用状态
 * 支持状态订阅、历史记录、状态持久化
 */
import { eventBus, Events } from './event-bus.js';

export class StateManager {
    constructor(options = {}) {
        this.state = {};
        this.subscribers = new Map();
        this.history = [];
        this.maxHistorySize = options.maxHistorySize || 50;
        this.persistKey = options.persistKey || 'app_state';
        this.persistEnabled = options.persist !== false;

        // 初始化时加载持久化状态
        if (this.persistEnabled) {
            this.loadPersistedState();
        }
    }

    /**
     * 获取状态值
     * @param {string} path - 状态路径，如 'user.name' 或 'projects'
     * @param {*} defaultValue - 默认值
     * @returns {*} 状态值
     */
    get(path, defaultValue = undefined) {
        if (!path) return this.state;

        const keys = path.split('.');
        let value = this.state;

        for (const key of keys) {
            if (value === null || value === undefined) {
                return defaultValue;
            }
            value = value[key];
        }

        return value !== undefined ? value : defaultValue;
    }

    /**
     * 设置状态值
     * @param {string} path - 状态路径
     * @param {*} value - 新值
     * @param {Object} options - 配置选项
     */
    set(path, value, options = {}) {
        const keys = path.split('.');
        const lastKey = keys.pop();

        let target = this.state;

        // 创建中间对象
        for (const key of keys) {
            if (!(key in target)) {
                target[key] = {};
            }
            target = target[key];
        }

        const oldValue = target[lastKey];
        target[lastKey] = value;

        // 记录历史
        if (!options.silent) {
            this.recordChange(path, oldValue, value);
        }

        // 通知订阅者
        if (!options.silent) {
            this.notifySubscribers(path, value, oldValue);

            // 发布状态变更事件
            eventBus.emit(Events.DATA_CHANGED, {
                path,
                value,
                oldValue
            });
        }

        // 持久化
        if (this.persistEnabled && !options.noPersist) {
            this.persist();
        }
    }

    /**
     * 批量设置状态
     * @param {Object} updates - 状态更新对象
     * @param {Object} options - 配置选项
     */
    setMultiple(updates, options = {}) {
        const changes = [];

        for (const [path, value] of Object.entries(updates)) {
            const oldValue = this.get(path);
            this.set(path, value, { ...options, silent: true, noPersist: true });
            changes.push({ path, value, oldValue });
        }

        // 批量通知
        if (!options.silent) {
            changes.forEach(({ path, value, oldValue }) => {
                this.notifySubscribers(path, value, oldValue);
            });

            eventBus.emit(Events.DATA_CHANGED, { changes });
        }

        // 持久化
        if (this.persistEnabled && !options.noPersist) {
            this.persist();
        }
    }

    /**
     * 订阅状态变化
     * @param {string} path - 状态路径
     * @param {Function} callback - 回调函数
     * @returns {Function} 取消订阅函数
     */
    subscribe(path, callback) {
        if (!this.subscribers.has(path)) {
            this.subscribers.set(path, new Set());
        }

        this.subscribers.get(path).add(callback);

        // 立即调用一次，传递当前值
        const currentValue = this.get(path);
        callback(currentValue, undefined);

        return () => {
            this.subscribers.get(path).delete(callback);
        };
    }

    /**
     * 通知订阅者
     */
    notifySubscribers(path, newValue, oldValue) {
        // 通知精确匹配的订阅者
        if (this.subscribers.has(path)) {
            this.subscribers.get(path).forEach(callback => {
                try {
                    callback(newValue, oldValue);
                } catch (error) {
                    console.error(`StateManager: Error in subscriber for "${path}"`, error);
                }
            });
        }

        // 通知父路径的订阅者
        const parts = path.split('.');
        for (let i = parts.length - 1; i > 0; i--) {
            const parentPath = parts.slice(0, i).join('.');
            if (this.subscribers.has(parentPath)) {
                const parentValue = this.get(parentPath);
                this.subscribers.get(parentPath).forEach(callback => {
                    try {
                        callback(parentValue, undefined);
                    } catch (error) {
                        console.error(`StateManager: Error in subscriber for "${parentPath}"`, error);
                    }
                });
            }
        }
    }

    /**
     * 记录状态变更历史
     */
    recordChange(path, oldValue, newValue) {
        this.history.push({
            path,
            oldValue,
            newValue,
            timestamp: Date.now()
        });

        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
        }
    }

    /**
     * 撤销最后一次变更
     */
    undo() {
        if (this.history.length === 0) return false;

        const lastChange = this.history.pop();
        this.set(lastChange.path, lastChange.oldValue, { silent: false });

        return true;
    }

    /**
     * 持久化状态到 localStorage
     */
    persist() {
        try {
            const stateToSave = JSON.stringify(this.state);
            localStorage.setItem(this.persistKey, stateToSave);
        } catch (error) {
            console.error('StateManager: Failed to persist state', error);
        }
    }

    /**
     * 加载持久化的状态
     */
    loadPersistedState() {
        try {
            const saved = localStorage.getItem(this.persistKey);
            if (saved) {
                this.state = JSON.parse(saved);
            }
        } catch (error) {
            console.error('StateManager: Failed to load persisted state', error);
        }
    }

    /**
     * 清除状态
     * @param {string} path - 状态路径（可选，不传则清除全部）
     */
    clear(path) {
        if (!path) {
            this.state = {};
            this.history = [];
            localStorage.removeItem(this.persistKey);
            return;
        }

        this.set(path, undefined);
    }

    /**
     * 获取状态快照
     */
    getSnapshot() {
        return JSON.parse(JSON.stringify(this.state));
    }

    /**
     * 从快照恢复状态
     */
    restoreFromSnapshot(snapshot) {
        this.state = JSON.parse(JSON.stringify(snapshot));
        this.persist();
        eventBus.emit(Events.DATA_CHANGED, { type: 'restore' });
    }

    /**
     * 获取状态统计信息
     */
    getStats() {
        const countKeys = (obj, prefix = '') => {
            let count = 0;
            for (const key in obj) {
                if (typeof obj[key] === 'object' && obj[key] !== null) {
                    count += countKeys(obj[key], `${prefix}${key}.`);
                } else {
                    count++;
                }
            }
            return count;
        };

        return {
            totalKeys: countKeys(this.state),
            historySize: this.history.length,
            subscriberCount: Array.from(this.subscribers.values())
                .reduce((sum, set) => sum + set.size, 0)
        };
    }
}

// 创建全局单例
export const stateManager = new StateManager();

// 兼容旧代码的全局访问
if (typeof window !== 'undefined') {
    window.StateManager = StateManager;
    window.stateManager = stateManager;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/core/`
Expected: 看到 state-manager.js 文件

**Step 3: Commit**

```bash
git add js/core/state-manager.js
git commit -m "feat(core): add StateManager for centralized state management"
```

---

## Task 4: 创建路由管理器 (Router)

**Files:**
- Create: `js/core/router.js`

**Step 1: 编写路由管理器代码**

```javascript
/**
 * 路由管理器 - 管理页面导航和路由
 * 支持路由守卫、参数传递、历史记录
 */
import { eventBus, Events } from './event-bus.js';

export class Router {
    constructor(options = {}) {
        this.routes = new Map();
        this.currentRoute = null;
        this.history = [];
        this.maxHistorySize = options.maxHistorySize || 50;
        this.beforeGuards = [];
        this.afterGuards = [];
        this.params = {};

        // 初始化
        this.init();
    }

    /**
     * 初始化路由
     */
    init() {
        // 监听浏览器前进/后退
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.route) {
                this.navigate(e.state.route, { ...e.state.params, replace: true });
            }
        });
    }

    /**
     * 注册路由
     * @param {string} name - 路由名称
     * @param {Object} config - 路由配置
     */
    register(name, config) {
        this.routes.set(name, {
            name,
            path: config.path || name,
            component: config.component,
            title: config.title || name,
            meta: config.meta || {},
            beforeEnter: config.beforeEnter,
            afterEnter: config.afterEnter
        });
    }

    /**
     * 批量注册路由
     * @param {Object} routes - 路由配置对象
     */
    registerRoutes(routes) {
        for (const [name, config] of Object.entries(routes)) {
            this.register(name, config);
        }
    }

    /**
     * 导航到指定路由
     * @param {string} name - 路由名称
     * @param {Object} options - 导航选项
     */
    async navigate(name, options = {}) {
        const route = this.routes.get(name);

        if (!route) {
            console.warn(`Router: Route "${name}" not found`);
            return false;
        }

        const fromRoute = this.currentRoute;
        const toRoute = { ...route, params: options.params || {} };

        // 执行全局前置守卫
        for (const guard of this.beforeGuards) {
            const result = await guard(toRoute, fromRoute);
            if (result === false) {
                return false;
            }
        }

        // 执行路由独享前置守卫
        if (route.beforeEnter) {
            const result = await route.beforeEnter(toRoute, fromRoute);
            if (result === false) {
                return false;
            }
        }

        // 更新浏览器历史
        if (!options.replace) {
            const state = { route: name, params: toRoute.params };
            window.history.pushState(state, route.title, `#${name}`);
        }

        // 更新当前路由
        this.currentRoute = toRoute;
        this.params = toRoute.params;

        // 记录历史
        this.history.push({
            from: fromRoute?.name,
            to: name,
            params: toRoute.params,
            timestamp: Date.now()
        });

        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
        }

        // 更新页面标题
        document.title = route.title || '媒体艺术智能工作台';

        // 发布路由变更事件
        eventBus.emit(Events.UI_PAGE_CHANGED, {
            from: fromRoute,
            to: toRoute
        });

        // 执行路由独享后置守卫
        if (route.afterEnter) {
            await route.afterEnter(toRoute, fromRoute);
        }

        // 执行全局后置守卫
        for (const guard of this.afterGuards) {
            await guard(toRoute, fromRoute);
        }

        return true;
    }

    /**
     * 返回上一页
     */
    back() {
        if (this.history.length > 1) {
            this.history.pop();
            const last = this.history[this.history.length - 1];
            this.navigate(last.to, { params: last.params, replace: true });
        } else {
            this.navigate('dashboard');
        }
    }

    /**
     * 添加全局前置守卫
     * @param {Function} guard - 守卫函数
     */
    beforeEach(guard) {
        this.beforeGuards.push(guard);
    }

    /**
     * 添加全局后置守卫
     * @param {Function} guard - 守卫函数
     */
    afterEach(guard) {
        this.afterGuards.push(guard);
    }

    /**
     * 获取当前路由参数
     * @param {string} key - 参数名（可选）
     */
    getParams(key) {
        if (key) {
            return this.params[key];
        }
        return { ...this.params };
    }

    /**
     * 获取当前路由信息
     */
    getCurrentRoute() {
        return this.currentRoute ? { ...this.currentRoute } : null;
    }

    /**
     * 检查是否为当前路由
     * @param {string} name - 路由名称
     */
    isCurrent(name) {
        return this.currentRoute?.name === name;
    }

    /**
     * 获取路由历史
     */
    getHistory() {
        return [...this.history];
    }
}

// 创建全局单例
export const router = new Router();

// 兼容旧代码的全局访问
if (typeof window !== 'undefined') {
    window.Router = Router;
    window.router = router;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/core/`
Expected: 看到 router.js 文件

**Step 3: Commit**

```bash
git add js/core/router.js
git commit -m "feat(core): add Router for page navigation management"
```

---

## Task 5: 创建基础模块类 (Base Module)

**Files:**
- Create: `js/core/base-module.js`

**Step 1: 编写基础模块类代码**

```javascript
/**
 * 基础模块类 - 所有业务模块的基类
 * 提供统一的生命周期管理、事件订阅、状态管理
 */
import { eventBus, Events } from './event-bus.js';
import { stateManager } from './state-manager.js';

export class BaseModule {
    constructor(options = {}) {
        this.name = options.name || this.constructor.name;
        this.statePath = options.statePath || this.name.toLowerCase();
        this.initialized = false;
        this.eventSubscriptions = [];
        this.stateSubscriptions = [];
        this.timers = [];

        // 模块配置
        this.config = {
            autoInit: options.autoInit !== false,
            lazyInit: options.lazyInit || false,
            ...options.config
        };

        // 自动初始化
        if (this.config.autoInit && !this.config.lazyInit) {
            this.init();
        }
    }

    /**
     * 初始化模块
     */
    async init() {
        if (this.initialized) {
            console.warn(`Module ${this.name} already initialized`);
            return;
        }

        // 初始化状态
        this.initState();

        // 绑定事件
        this.bindEvents();

        // 初始化 UI
        await this.onInit();

        this.initialized = true;

        // 发布模块加载事件
        eventBus.emit(Events.MODULE_LOADED, { name: this.name });

        console.log(`Module ${this.name} initialized`);
    }

    /**
     * 销毁模块
     */
    destroy() {
        // 清理事件订阅
        this.eventSubscriptions.forEach(unsubscribe => unsubscribe());
        this.eventSubscriptions = [];

        // 清理状态订阅
        this.stateSubscriptions.forEach(unsubscribe => unsubscribe());
        this.stateSubscriptions = [];

        // 清理定时器
        this.timers.forEach(timer => clearTimeout(timer));
        this.timers = [];

        // 调用子类销毁方法
        this.onDestroy();

        this.initialized = false;

        // 发布模块卸载事件
        eventBus.emit(Events.MODULE_UNLOADED, { name: this.name });

        console.log(`Module ${this.name} destroyed`);
    }

    /**
     * 初始化状态
     */
    initState() {
        const defaultState = this.getDefaultState();
        const currentState = this.getState();

        // 合并默认状态和当前状态
        if (!currentState || Object.keys(currentState).length === 0) {
            this.setState(defaultState, { silent: true });
        }
    }

    /**
     * 获取默认状态（子类重写）
     */
    getDefaultState() {
        return {};
    }

    /**
     * 绑定事件（子类重写）
     */
    bindEvents() {
        // 子类实现
    }

    /**
     * 初始化回调（子类重写）
     */
    async onInit() {
        // 子类实现
    }

    /**
     * 销毁回调（子类重写）
     */
    onDestroy() {
        // 子类实现
    }

    /**
     * 获取模块状态
     * @param {string} key - 状态键（可选）
     */
    getState(key) {
        const path = key ? `${this.statePath}.${key}` : this.statePath;
        return stateManager.get(path);
    }

    /**
     * 设置模块状态
     * @param {string|Object} keyOrUpdates - 状态键或更新对象
     * @param {*} value - 状态值
     * @param {Object} options - 配置选项
     */
    setState(keyOrUpdates, value, options = {}) {
        if (typeof keyOrUpdates === 'string') {
            const path = `${this.statePath}.${keyOrUpdates}`;
            stateManager.set(path, value, options);
        } else {
            const updates = {};
            for (const [key, val] of Object.entries(keyOrUpdates)) {
                updates[`${this.statePath}.${key}`] = val;
            }
            stateManager.setMultiple(updates, options);
        }
    }

    /**
     * 订阅事件
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     */
    on(event, callback) {
        const unsubscribe = eventBus.on(event, callback);
        this.eventSubscriptions.push(unsubscribe);
        return unsubscribe;
    }

    /**
     * 订阅一次性事件
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     */
    once(event, callback) {
        const unsubscribe = eventBus.once(event, callback);
        this.eventSubscriptions.push(unsubscribe);
        return unsubscribe;
    }

    /**
     * 发布事件
     * @param {string} event - 事件名称
     * @param {*} data - 事件数据
     */
    emit(event, data) {
        return eventBus.emit(event, data);
    }

    /**
     * 订阅状态变化
     * @param {string} key - 状态键
     * @param {Function} callback - 回调函数
     */
    watchState(key, callback) {
        const path = `${this.statePath}.${key}`;
        const unsubscribe = stateManager.subscribe(path, callback);
        this.stateSubscriptions.push(unsubscribe);
        return unsubscribe;
    }

    /**
     * 设置定时器
     * @param {Function} callback - 回调函数
     * @param {number} delay - 延迟时间
     */
    setTimeout(callback, delay) {
        const timer = setTimeout(() => {
            callback();
            this.timers = this.timers.filter(t => t !== timer);
        }, delay);
        this.timers.push(timer);
        return timer;
    }

    /**
     * 显示 Toast 消息
     * @param {string} message - 消息内容
     * @param {string} type - 消息类型
     */
    showToast(message, type = 'info') {
        eventBus.emit(Events.UI_TOAST, { message, type });
    }

    /**
     * 显示确认对话框
     * @param {Object} options - 对话框选项
     */
    showConfirm(options) {
        return new Promise((resolve) => {
            eventBus.emit(Events.UI_MODAL_OPEN, {
                type: 'confirm',
                ...options,
                onConfirm: () => {
                    resolve(true);
                    eventBus.emit(Events.UI_MODAL_CLOSE);
                },
                onCancel: () => {
                    resolve(false);
                    eventBus.emit(Events.UI_MODAL_CLOSE);
                }
            });
        });
    }

    /**
     * 获取模块信息
     */
    getInfo() {
        return {
            name: this.name,
            statePath: this.statePath,
            initialized: this.initialized,
            state: this.getState()
        };
    }
}

// 兼容旧代码的全局访问
if (typeof window !== 'undefined') {
    window.BaseModule = BaseModule;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/core/`
Expected: 看到 base-module.js 文件

**Step 3: Commit**

```bash
git add js/core/base-module.js
git commit -m "feat(core): add BaseModule class for module inheritance"
```

---

## Task 6: 创建模块加载器 (Module Loader)

**Files:**
- Create: `js/core/module-loader.js`

**Step 1: 编写模块加载器代码**

```javascript
/**
 * 模块加载器 - 动态加载和管理模块
 * 支持懒加载、模块缓存、依赖管理
 */
import { eventBus, Events } from './event-bus.js';

export class ModuleLoader {
    constructor() {
        this.modules = new Map();
        this.loading = new Map();
        this.moduleConfigs = new Map();
    }

    /**
     * 注册模块
     * @param {string} name - 模块名称
     * @param {Object} config - 模块配置
     */
    register(name, config) {
        this.moduleConfigs.set(name, {
            name,
            path: config.path,
            dependencies: config.dependencies || [],
            lazy: config.lazy !== false,
            singleton: config.singleton !== false,
            ...config
        });
    }

    /**
     * 批量注册模块
     * @param {Object} modules - 模块配置对象
     */
    registerModules(modules) {
        for (const [name, config] of Object.entries(modules)) {
            this.register(name, config);
        }
    }

    /**
     * 加载模块
     * @param {string} name - 模块名称
     * @returns {Promise<Object>} 模块实例
     */
    async load(name) {
        // 检查是否已加载
        if (this.modules.has(name)) {
            return this.modules.get(name);
        }

        // 检查是否正在加载
        if (this.loading.has(name)) {
            return this.loading.get(name);
        }

        // 获取模块配置
        const config = this.moduleConfigs.get(name);
        if (!config) {
            throw new Error(`Module "${name}" not registered`);
        }

        // 创建加载 Promise
        const loadPromise = this._loadModule(config);
        this.loading.set(name, loadPromise);

        try {
            const module = await loadPromise;
            this.modules.set(name, module);
            this.loading.delete(name);
            return module;
        } catch (error) {
            this.loading.delete(name);
            throw error;
        }
    }

    /**
     * 内部加载模块
     */
    async _loadModule(config) {
        // 加载依赖
        if (config.dependencies.length > 0) {
            await Promise.all(config.dependencies.map(dep => this.load(dep)));
        }

        // 动态导入模块
        if (config.path) {
            const moduleExports = await import(config.path);
            const ModuleClass = moduleExports.default || moduleExports[config.exportName || 'default'];

            if (typeof ModuleClass === 'function') {
                const instance = new ModuleClass(config.options || {});

                if (config.singleton) {
                    this.modules.set(config.name, instance);
                }

                return instance;
            }

            return moduleExports;
        }

        // 使用工厂函数
        if (config.factory) {
            const instance = await config.factory();

            if (config.singleton) {
                this.modules.set(config.name, instance);
            }

            return instance;
        }

        throw new Error(`Module "${config.name}" has no path or factory`);
    }

    /**
     * 预加载模块
     * @param {string[]} names - 模块名称数组
     */
    async preload(names) {
        const configs = names
            .map(name => this.moduleConfigs.get(name))
            .filter(config => config && !config.lazy);

        await Promise.all(configs.map(config => this.load(config.name)));
    }

    /**
     * 卸载模块
     * @param {string} name - 模块名称
     */
    unload(name) {
        const module = this.modules.get(name);

        if (module && typeof module.destroy === 'function') {
            module.destroy();
        }

        this.modules.delete(name);

        eventBus.emit(Events.MODULE_UNLOADED, { name });
    }

    /**
     * 获取已加载的模块
     * @param {string} name - 模块名称
     */
    get(name) {
        return this.modules.get(name);
    }

    /**
     * 检查模块是否已加载
     * @param {string} name - 模块名称
     */
    isLoaded(name) {
        return this.modules.has(name);
    }

    /**
     * 获取所有已加载的模块
     */
    getAll() {
        return Object.fromEntries(this.modules);
    }

    /**
     * 获取模块统计信息
     */
    getStats() {
        return {
            registered: this.moduleConfigs.size,
            loaded: this.modules.size,
            loading: this.loading.size
        };
    }
}

// 创建全局单例
export const moduleLoader = new ModuleLoader();

// 兼容旧代码的全局访问
if (typeof window !== 'undefined') {
    window.ModuleLoader = ModuleLoader;
    window.moduleLoader = moduleLoader;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/core/`
Expected: 看到 module-loader.js 文件

**Step 3: Commit**

```bash
git add js/core/module-loader.js
git commit -m "feat(core): add ModuleLoader for dynamic module loading"
```

---

## Task 7: 创建核心模块索引文件

**Files:**
- Create: `js/core/index.js`

**Step 1: 编写索引文件**

```javascript
/**
 * 核心模块统一导出
 */
export { EventBus, eventBus, Events } from './event-bus.js';
export { StateManager, stateManager } from './state-manager.js';
export { Router, router } from './router.js';
export { BaseModule } from './base-module.js';
export { ModuleLoader, moduleLoader } from './module-loader.js';

/**
 * 初始化核心模块
 */
export async function initCore(options = {}) {
    const { routes = {}, modules = {} } = options;

    // 注册路由
    if (Object.keys(routes).length > 0) {
        router.registerRoutes(routes);
    }

    // 注册模块
    if (Object.keys(modules).length > 0) {
        moduleLoader.registerModules(modules);
    }

    // 预加载非懒加载模块
    await moduleLoader.preload(Object.keys(modules));

    console.log('Core modules initialized');
}

// 兼容旧代码的全局访问
if (typeof window !== 'undefined') {
    window.initCore = initCore;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/core/`
Expected: 看到 index.js 文件

**Step 3: Commit**

```bash
git add js/core/index.js
git commit -m "feat(core): add core module index file"
```

---

## Task 8: 创建项目模块 (Project Module)

**Files:**
- Create: `js/modules/projects/index.js`

**Step 1: 编写项目模块代码**

```javascript
/**
 * 项目管理模块
 */
import { BaseModule } from '../../core/base-module.js';
import { Events } from '../../core/event-bus.js';

export class ProjectModule extends BaseModule {
    constructor(options = {}) {
        super({
            name: 'ProjectModule',
            statePath: 'projects',
            ...options
        });
    }

    getDefaultState() {
        return {
            list: [],
            currentProject: null,
            filter: {
                status: 'all',
                search: ''
            },
            pagination: {
                page: 1,
                pageSize: 10
            }
        };
    }

    bindEvents() {
        // 监听项目创建事件
        this.on(Events.ENTITY_CREATED, (data) => {
            if (data.entity === 'project') {
                this.refreshList();
            }
        });

        // 监听项目更新事件
        this.on(Events.ENTITY_UPDATED, (data) => {
            if (data.entity === 'project') {
                this.refreshList();
            }
        });

        // 监听项目删除事件
        this.on(Events.ENTITY_DELETED, (data) => {
            if (data.entity === 'project') {
                this.refreshList();
            }
        });
    }

    async onInit() {
        // 加载项目列表
        await this.refreshList();
    }

    /**
     * 刷新项目列表
     */
    async refreshList() {
        // 调用 API 获取数据
        const projects = typeof ProjectAPI !== 'undefined'
            ? ProjectAPI.getAll()
            : [];

        this.setState('list', projects);
        this.renderList();
    }

    /**
     * 设置筛选条件
     */
    setFilter(filter) {
        this.setState('filter', { ...this.getState('filter'), ...filter });
        this.renderList();
    }

    /**
     * 设置分页
     */
    setPage(page) {
        this.setState('pagination', { ...this.getState('pagination'), page });
        this.renderList();
    }

    /**
     * 获取当前项目
     */
    getCurrentProject() {
        return this.getState('currentProject');
    }

    /**
     * 设置当前项目
     */
    setCurrentProject(project) {
        this.setState('currentProject', project);
    }

    /**
     * 创建项目
     */
    async create(data) {
        if (typeof ProjectAPI === 'undefined') {
            throw new Error('ProjectAPI not available');
        }

        const project = ProjectAPI.create(data);

        this.emit(Events.ENTITY_CREATED, {
            entity: 'project',
            data: project
        });

        await this.refreshList();

        return project;
    }

    /**
     * 更新项目
     */
    async update(id, data) {
        if (typeof ProjectAPI === 'undefined') {
            throw new Error('ProjectAPI not available');
        }

        const project = ProjectAPI.update(id, data);

        this.emit(Events.ENTITY_UPDATED, {
            entity: 'project',
            id,
            data: project
        });

        await this.refreshList();

        return project;
    }

    /**
     * 删除项目
     */
    async delete(id) {
        if (typeof ProjectAPI === 'undefined') {
            throw new Error('ProjectAPI not available');
        }

        ProjectAPI.delete(id);

        this.emit(Events.ENTITY_DELETED, {
            entity: 'project',
            id
        });

        await this.refreshList();
    }

    /**
     * 渲染项目列表
     */
    renderList() {
        const container = document.getElementById('projectList');
        if (!container) return;

        const { list, filter, pagination } = this.getState();

        // 应用筛选
        let filteredList = list;

        if (filter.status !== 'all') {
            filteredList = filteredList.filter(p => p.status === filter.status);
        }

        if (filter.search) {
            const search = filter.search.toLowerCase();
            filteredList = filteredList.filter(p =>
                p.name.toLowerCase().includes(search) ||
                (p.type && p.type.toLowerCase().includes(search))
            );
        }

        // 应用分页
        const { page, pageSize } = pagination;
        const start = (page - 1) * pageSize;
        const paginatedList = filteredList.slice(start, start + pageSize);

        // 渲染
        if (paginatedList.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无项目</div>';
            return;
        }

        container.innerHTML = paginatedList.map(p => `
            <div class="project-card" data-id="${p.id}">
                <div class="project-info">
                    <h4>${p.name}</h4>
                    <p>${p.type || '未分类'} · ${p.startDate || '未设置日期'} · ${p.manager || '未指定负责人'}</p>
                </div>
                <div class="project-actions">
                    <span class="status-badge ${p.status}">${p.status}</span>
                    <button class="icon-btn edit-btn" title="编辑">✎</button>
                    <button class="icon-btn danger delete-btn" title="删除">✕</button>
                </div>
            </div>
        `).join('');

        // 绑定事件
        container.querySelectorAll('.project-card').forEach(card => {
            const id = card.dataset.id;

            card.addEventListener('click', () => this.viewProject(id));

            card.querySelector('.edit-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.editProject(id);
            });

            card.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteProject(id);
            });
        });
    }

    /**
     * 查看项目详情
     */
    viewProject(id) {
        const project = typeof ProjectAPI !== 'undefined'
            ? ProjectAPI.getById(id)
            : null;

        if (project) {
            this.setCurrentProject(project);
            this.emit(Events.UI_PAGE_CHANGED, { page: 'project-detail', id });
        }
    }

    /**
     * 编辑项目
     */
    editProject(id) {
        this.emit(Events.UI_PAGE_CHANGED, { page: 'new-project', editId: id });
    }

    /**
     * 删除项目
     */
    async deleteProject(id) {
        const confirmed = await this.showConfirm({
            title: '删除项目',
            message: '确定要删除这个项目吗？关联的参赛选手也会被删除。',
            danger: true
        });

        if (confirmed) {
            await this.delete(id);
            this.showToast('项目已删除', 'success');
        }
    }
}

// 导出模块
export default ProjectModule;

// 兼容旧代码
if (typeof window !== 'undefined') {
    window.ProjectModule = ProjectModule;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/modules/projects/`
Expected: 看到 index.js 文件

**Step 3: Commit**

```bash
git add js/modules/projects/index.js
git commit -m "feat(modules): add ProjectModule with CRUD operations"
```

---

## Task 9: 创建选手模块 (Player Module)

**Files:**
- Create: `js/modules/players/index.js`

**Step 1: 编写选手模块代码**

```javascript
/**
 * 选手管理模块
 */
import { BaseModule } from '../../core/base-module.js';
import { Events } from '../../core/event-bus.js';

export class PlayerModule extends BaseModule {
    constructor(options = {}) {
        super({
            name: 'PlayerModule',
            statePath: 'players',
            ...options
        });
    }

    getDefaultState() {
        return {
            list: [],
            currentPlayer: null,
            filter: {
                category: 'all',
                search: ''
            },
            pagination: {
                page: 1,
                pageSize: 10
            },
            missingMaterials: []
        };
    }

    bindEvents() {
        // 监听实体变更事件
        this.on(Events.ENTITY_CREATED, (data) => {
            if (data.entity === 'player') {
                this.refreshList();
            }
        });

        this.on(Events.ENTITY_UPDATED, (data) => {
            if (data.entity === 'player') {
                this.refreshList();
            }
        });

        this.on(Events.ENTITY_DELETED, (data) => {
            if (data.entity === 'player') {
                this.refreshList();
            }
        });
    }

    async onInit() {
        await this.refreshList();
    }

    /**
     * 刷新选手列表
     */
    async refreshList() {
        const players = typeof PlayerAPI !== 'undefined'
            ? PlayerAPI.getAll()
            : [];

        this.setState('list', players);

        // 异步检查资料完整性
        this.checkMissingMaterials(players);

        this.renderList();
    }

    /**
     * 检查缺失资料
     */
    async checkMissingMaterials(players) {
        const missingMaterials = [];

        for (const player of players) {
            if (typeof PlayerAPI !== 'undefined' && PlayerAPI.checkMaterialsFromFileSystem) {
                const result = await PlayerAPI.checkMaterialsFromFileSystem(player.id);
                if (result && result.missing > 0) {
                    missingMaterials.push({
                        id: player.id,
                        name: player.name,
                        stage: player.stage,
                        missingCount: result.missing,
                        missingTypes: result.missingTypes
                    });
                }
            }
        }

        this.setState('missingMaterials', missingMaterials);
        this.renderMissingMaterialsAlert();
    }

    /**
     * 渲染缺失资料警示
     */
    renderMissingMaterialsAlert() {
        const alertEl = document.getElementById('playerMissingMaterialsAlert');
        const countEl = document.getElementById('missingMaterialsCount');

        if (!alertEl || !countEl) return;

        const { missingMaterials } = this.getState();

        if (missingMaterials.length > 0) {
            alertEl.style.display = 'block';
            countEl.textContent = missingMaterials.length;
        } else {
            alertEl.style.display = 'none';
        }
    }

    /**
     * 创建选手
     */
    async create(data) {
        if (typeof PlayerAPI === 'undefined') {
            throw new Error('PlayerAPI not available');
        }

        const player = PlayerAPI.create(data);

        this.emit(Events.ENTITY_CREATED, {
            entity: 'player',
            data: player
        });

        await this.refreshList();

        return player;
    }

    /**
     * 更新选手
     */
    async update(id, data) {
        if (typeof PlayerAPI === 'undefined') {
            throw new Error('PlayerAPI not available');
        }

        const player = PlayerAPI.update(id, data);

        this.emit(Events.ENTITY_UPDATED, {
            entity: 'player',
            id,
            data: player
        });

        await this.refreshList();

        return player;
    }

    /**
     * 删除选手
     */
    async delete(id) {
        if (typeof PlayerAPI === 'undefined') {
            throw new Error('PlayerAPI not available');
        }

        PlayerAPI.delete(id);

        this.emit(Events.ENTITY_DELETED, {
            entity: 'player',
            id
        });

        await this.refreshList();
    }

    /**
     * 晋级选手
     */
    async advanceStage(id, result, materials) {
        if (typeof PlayerAPI === 'undefined') {
            throw new Error('PlayerAPI not available');
        }

        const player = PlayerAPI.advanceStage(id, result, materials);

        this.emit(Events.ENTITY_UPDATED, {
            entity: 'player',
            id,
            data: player
        });

        await this.refreshList();

        return player;
    }

    /**
     * 上传资料
     */
    async uploadMaterial(id, stage, material) {
        if (typeof PlayerAPI === 'undefined') {
            throw new Error('PlayerAPI not available');
        }

        const player = PlayerAPI.addMaterial(id, stage, material);

        this.emit(Events.FILE_UPLOADED, {
            entity: 'player',
            id,
            stage,
            material
        });

        await this.refreshList();

        return player;
    }

    /**
     * 渲染选手列表
     */
    renderList() {
        const container = document.getElementById('playerList');
        if (!container) return;

        const { list, filter, pagination, missingMaterials } = this.getState();

        // 将缺资料的选手排在前面
        const missingIds = new Set(missingMaterials.map(m => m.id));
        let sortedList = [...list].sort((a, b) => {
            const aMissing = missingIds.has(a.id) ? 0 : 1;
            const bMissing = missingIds.has(b.id) ? 0 : 1;
            return aMissing - bMissing;
        });

        // 应用筛选
        if (filter.category !== 'all') {
            sortedList = sortedList.filter(p => p.category === filter.category);
        }

        if (filter.search) {
            const search = filter.search.toLowerCase();
            sortedList = sortedList.filter(p =>
                p.name.toLowerCase().includes(search) ||
                (p.org && p.org.toLowerCase().includes(search))
            );
        }

        // 应用分页
        const { page, pageSize } = pagination;
        const start = (page - 1) * pageSize;
        const paginatedList = sortedList.slice(start, start + pageSize);

        // 渲染
        if (paginatedList.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无选手</div>';
            return;
        }

        container.innerHTML = paginatedList.map(p => {
            const missing = missingMaterials.find(m => m.id === p.id);
            const missingBadge = missing
                ? `<span class="player-missing-badge">缺${missing.missingCount}项</span>`
                : '';

            return `
                <div class="talent-card" data-id="${p.id}">
                    <div class="talent-info">
                        <h4>${p.name} ${missingBadge}</h4>
                        <p>${p.category || '未分类'} · ${p.stage || '未定级'} · ${p.phone || '未设置电话'}</p>
                    </div>
                    <div class="talent-actions">
                        <button class="icon-btn edit-btn" title="编辑">✎</button>
                        <button class="icon-btn danger delete-btn" title="删除">✕</button>
                    </div>
                </div>
            `;
        }).join('');

        // 绑定事件
        container.querySelectorAll('.talent-card').forEach(card => {
            const id = card.dataset.id;

            card.addEventListener('click', () => this.viewPlayer(id));

            card.querySelector('.edit-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.editPlayer(id);
            });

            card.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.deletePlayer(id);
            });
        });
    }

    viewPlayer(id) {
        this.emit(Events.UI_PAGE_CHANGED, { page: 'player-detail', id });
    }

    editPlayer(id) {
        this.emit(Events.UI_PAGE_CHANGED, { page: 'new-player', editId: id });
    }

    async deletePlayer(id) {
        const confirmed = await this.showConfirm({
            title: '删除选手',
            message: '确定要删除这个选手吗？',
            danger: true
        });

        if (confirmed) {
            await this.delete(id);
            this.showToast('选手已删除', 'success');
        }
    }
}

export default PlayerModule;

if (typeof window !== 'undefined') {
    window.PlayerModule = PlayerModule;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/modules/players/`
Expected: 看到 index.js 文件

**Step 3: Commit**

```bash
git add js/modules/players/index.js
git commit -m "feat(modules): add PlayerModule with material tracking"
```

---

## Task 10: 创建机构模块 (Organization Module)

**Files:**
- Create: `js/modules/organizations/index.js`

**Step 1: 编写机构模块代码**

```javascript
/**
 * 机构管理模块
 */
import { BaseModule } from '../../core/base-module.js';
import { Events } from '../../core/event-bus.js';

export class OrganizationModule extends BaseModule {
    constructor(options = {}) {
        super({
            name: 'OrganizationModule',
            statePath: 'organizations',
            ...options
        });
    }

    getDefaultState() {
        return {
            list: [],
            currentOrg: null,
            filter: {
                type: 'all',
                search: ''
            },
            pagination: {
                page: 1,
                pageSize: 10
            }
        };
    }

    bindEvents() {
        this.on(Events.ENTITY_CREATED, (data) => {
            if (data.entity === 'organization') {
                this.refreshList();
            }
        });

        this.on(Events.ENTITY_UPDATED, (data) => {
            if (data.entity === 'organization') {
                this.refreshList();
            }
        });

        this.on(Events.ENTITY_DELETED, (data) => {
            if (data.entity === 'organization') {
                this.refreshList();
            }
        });
    }

    async onInit() {
        await this.refreshList();
    }

    async refreshList() {
        const orgs = typeof OrgAPI !== 'undefined'
            ? OrgAPI.getAll()
            : [];

        this.setState('list', orgs);
        this.renderList();
    }

    async create(data) {
        if (typeof OrgAPI === 'undefined') {
            throw new Error('OrgAPI not available');
        }

        const org = OrgAPI.create(data);

        this.emit(Events.ENTITY_CREATED, {
            entity: 'organization',
            data: org
        });

        await this.refreshList();

        return org;
    }

    async update(id, data) {
        if (typeof OrgAPI === 'undefined') {
            throw new Error('OrgAPI not available');
        }

        const org = OrgAPI.update(id, data);

        this.emit(Events.ENTITY_UPDATED, {
            entity: 'organization',
            id,
            data: org
        });

        await this.refreshList();

        return org;
    }

    async delete(id) {
        if (typeof OrgAPI === 'undefined') {
            throw new Error('OrgAPI not available');
        }

        OrgAPI.delete(id);

        this.emit(Events.ENTITY_DELETED, {
            entity: 'organization',
            id
        });

        await this.refreshList();
    }

    renderList() {
        const container = document.getElementById('orgList');
        if (!container) return;

        const { list, filter, pagination } = this.getState();

        let filteredList = list;

        if (filter.type !== 'all') {
            filteredList = filteredList.filter(o => o.type === filter.type);
        }

        if (filter.search) {
            const search = filter.search.toLowerCase();
            filteredList = filteredList.filter(o =>
                o.name.toLowerCase().includes(search) ||
                (o.contact && o.contact.toLowerCase().includes(search))
            );
        }

        const { page, pageSize } = pagination;
        const start = (page - 1) * pageSize;
        const paginatedList = filteredList.slice(start, start + pageSize);

        if (paginatedList.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无机构</div>';
            return;
        }

        container.innerHTML = paginatedList.map(o => `
            <div class="org-card" data-id="${o.id}">
                <div class="org-card-header">
                    <div class="org-name">${o.name}</div>
                    <div class="org-type">${o.type}</div>
                </div>
                <div class="org-contact">联系人: ${o.contact || '未设置'}</div>
                <div class="org-contact">电话: ${o.phone || '未设置'}</div>
                <div class="org-stats">
                    <div class="org-stat">
                        <div class="org-stat-value">${o.coopCount || 0}</div>
                        <div class="org-stat-label">合作次数</div>
                    </div>
                    <div class="org-stat">
                        <div class="org-stat-value">${o.level || '待评估'}</div>
                        <div class="org-stat-label">合作等级</div>
                    </div>
                </div>
                <div class="org-actions">
                    <button class="icon-btn edit-btn" title="编辑">✎</button>
                    <button class="icon-btn danger delete-btn" title="删除">✕</button>
                </div>
            </div>
        `).join('');

        container.querySelectorAll('.org-card').forEach(card => {
            const id = card.dataset.id;

            card.addEventListener('click', () => this.viewOrg(id));

            card.querySelector('.edit-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.editOrg(id);
            });

            card.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteOrg(id);
            });
        });
    }

    viewOrg(id) {
        this.emit(Events.UI_PAGE_CHANGED, { page: 'org-detail', id });
    }

    editOrg(id) {
        this.emit(Events.UI_PAGE_CHANGED, { page: 'new-org', editId: id });
    }

    async deleteOrg(id) {
        const confirmed = await this.showConfirm({
            title: '删除机构',
            message: '确定要删除这个机构吗？',
            danger: true
        });

        if (confirmed) {
            await this.delete(id);
            this.showToast('机构已删除', 'success');
        }
    }
}

export default OrganizationModule;

if (typeof window !== 'undefined') {
    window.OrganizationModule = OrganizationModule;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/modules/organizations/`
Expected: 看到 index.js 文件

**Step 3: Commit**

```bash
git add js/modules/organizations/index.js
git commit -m "feat(modules): add OrganizationModule"
```

---

## Task 11: 创建财务模块 (Finance Module)

**Files:**
- Create: `js/modules/finance/index.js`

**Step 1: 编写财务模块代码**

```javascript
/**
 * 财务管理模块
 */
import { BaseModule } from '../../core/base-module.js';
import { Events } from '../../core/event-bus.js';

export class FinanceModule extends BaseModule {
    constructor(options = {}) {
        super({
            name: 'FinanceModule',
            statePath: 'finance',
            ...options
        });
    }

    getDefaultState() {
        return {
            list: [],
            stats: {
                income: 0,
                expense: 0,
                profit: 0,
                monthlyProfit: 0
            },
            filter: {
                type: 'all',
                org: 'all',
                project: 'all',
                month: 'all',
                search: ''
            },
            pagination: {
                page: 1,
                pageSize: 10
            }
        };
    }

    bindEvents() {
        this.on(Events.ENTITY_CREATED, (data) => {
            if (data.entity === 'finance') {
                this.refreshList();
            }
        });

        this.on(Events.ENTITY_UPDATED, (data) => {
            if (data.entity === 'finance') {
                this.refreshList();
            }
        });

        this.on(Events.ENTITY_DELETED, (data) => {
            if (data.entity === 'finance') {
                this.refreshList();
            }
        });
    }

    async onInit() {
        await this.refreshList();
    }

    async refreshList() {
        const finances = typeof FinanceAPI !== 'undefined'
            ? FinanceAPI.getAll()
            : [];

        const stats = typeof FinanceAPI !== 'undefined'
            ? FinanceAPI.getStats()
            : this.getDefaultState().stats;

        this.setState('list', finances);
        this.setState('stats', stats);

        this.renderList();
        this.renderStats();
        this.renderCharts();
    }

    async create(data) {
        if (typeof FinanceAPI === 'undefined') {
            throw new Error('FinanceAPI not available');
        }

        const finance = FinanceAPI.create(data);

        this.emit(Events.ENTITY_CREATED, {
            entity: 'finance',
            data: finance
        });

        await this.refreshList();

        return finance;
    }

    async update(id, data) {
        if (typeof FinanceAPI === 'undefined') {
            throw new Error('FinanceAPI not available');
        }

        const finance = FinanceAPI.update(id, data);

        this.emit(Events.ENTITY_UPDATED, {
            entity: 'finance',
            id,
            data: finance
        });

        await this.refreshList();

        return finance;
    }

    async delete(id) {
        if (typeof FinanceAPI === 'undefined') {
            throw new Error('FinanceAPI not available');
        }

        FinanceAPI.delete(id);

        this.emit(Events.ENTITY_DELETED, {
            entity: 'finance',
            id
        });

        await this.refreshList();
    }

    renderStats() {
        const { stats } = this.getState();

        const totalIncome = document.getElementById('totalIncome');
        const totalExpense = document.getElementById('totalExpense');
        const totalProfit = document.getElementById('totalProfit');
        const monthlyProfit = document.getElementById('monthlyProfit');

        if (totalIncome) totalIncome.textContent = '¥' + stats.income.toLocaleString();
        if (totalExpense) totalExpense.textContent = '¥' + stats.expense.toLocaleString();
        if (totalProfit) totalProfit.textContent = '¥' + stats.profit.toLocaleString();
        if (monthlyProfit) monthlyProfit.textContent = '¥' + stats.monthlyProfit.toLocaleString();
    }

    renderCharts() {
        // 图表渲染逻辑（使用 Chart.js）
        // 这里可以调用现有的 FinanceUI.renderCharts()
        if (typeof FinanceUI !== 'undefined' && FinanceUI.renderCharts) {
            FinanceUI.renderCharts();
        }
    }

    renderList() {
        const container = document.getElementById('financeList');
        if (!container) return;

        const { list, filter, pagination } = this.getState();

        let filteredList = list;

        if (filter.type !== 'all') {
            filteredList = filteredList.filter(f => f.type === filter.type);
        }

        if (filter.org !== 'all') {
            filteredList = filteredList.filter(f => f.orgId === filter.org);
        }

        if (filter.project !== 'all') {
            filteredList = filteredList.filter(f => f.projectId === filter.project);
        }

        if (filter.month !== 'all') {
            filteredList = filteredList.filter(f => f.date.startsWith(filter.month));
        }

        if (filter.search) {
            const search = filter.search.toLowerCase();
            filteredList = filteredList.filter(f =>
                f.title.toLowerCase().includes(search) ||
                (f.note && f.note.toLowerCase().includes(search))
            );
        }

        // 按日期排序
        filteredList.sort((a, b) => new Date(b.date) - new Date(a.date));

        const { page, pageSize } = pagination;
        const start = (page - 1) * pageSize;
        const paginatedList = filteredList.slice(start, start + pageSize);

        if (paginatedList.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无财务记录</div>';
            return;
        }

        // 按月份分组
        const grouped = {};
        paginatedList.forEach(f => {
            const month = f.date.substring(0, 7);
            if (!grouped[month]) grouped[month] = [];
            grouped[month].push(f);
        });

        let html = '';
        const monthNames = ['一月', '二月', '三月', '四月', '五月', '六月',
                           '七月', '八月', '九月', '十月', '十一月', '十二月'];

        Object.keys(grouped).sort().reverse().forEach(month => {
            const [year, m] = month.split('-');
            const monthName = `${year}年${monthNames[parseInt(m) - 1]}`;
            const monthFinances = grouped[month];

            const monthIncome = monthFinances
                .filter(f => f.type === '收入')
                .reduce((sum, f) => sum + f.amount, 0);
            const monthExpense = monthFinances
                .filter(f => f.type === '支出')
                .reduce((sum, f) => sum + f.amount, 0);
            const monthProfit = monthIncome - monthExpense;

            html += `
                <div class="finance-month-group">
                    <div class="finance-month-header">
                        <div class="month-title">${monthName}</div>
                        <div class="month-stats">
                            <span class="month-income">收入: ¥${monthIncome.toLocaleString()}</span>
                            <span class="month-expense">支出: ¥${monthExpense.toLocaleString()}</span>
                            <span class="month-profit ${monthProfit >= 0 ? 'positive' : 'negative'}">
                                盈亏: ${monthProfit >= 0 ? '+' : ''}¥${monthProfit.toLocaleString()}
                            </span>
                        </div>
                    </div>
                    <table class="finance-table">
                        <thead>
                            <tr>
                                <th>日期</th>
                                <th>类型</th>
                                <th>分类</th>
                                <th>摘要</th>
                                <th>金额</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${monthFinances.map(f => `
                                <tr class="finance-row ${f.type === '收入' ? 'income' : 'expense'}">
                                    <td>${f.date}</td>
                                    <td><span class="finance-type-badge">${f.type}</span></td>
                                    <td>${f.category}</td>
                                    <td>${f.title}</td>
                                    <td class="finance-amount">
                                        ${f.type === '收入' ? '+' : '-'}¥${f.amount.toLocaleString()}
                                    </td>
                                    <td class="finance-actions">
                                        <button class="icon-btn edit-btn" data-id="${f.id}">✎</button>
                                        <button class="icon-btn danger delete-btn" data-id="${f.id}">✕</button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        });

        container.innerHTML = html;

        // 绑定事件
        container.querySelectorAll('.edit-btn').forEach(btn => {
            btn.addEventListener('click', () => this.editFinance(btn.dataset.id));
        });

        container.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', () => this.deleteFinance(btn.dataset.id));
        });
    }

    editFinance(id) {
        this.emit(Events.UI_PAGE_CHANGED, { page: 'new-finance', editId: id });
    }

    async deleteFinance(id) {
        const confirmed = await this.showConfirm({
            title: '删除财务记录',
            message: '确定要删除这条财务记录吗？',
            danger: true
        });

        if (confirmed) {
            await this.delete(id);
            this.showToast('财务记录已删除', 'success');
        }
    }

    async exportReport() {
        // 导出报表逻辑
        this.showToast('导出功能开发中', 'info');
    }
}

export default FinanceModule;

if (typeof window !== 'undefined') {
    window.FinanceModule = FinanceModule;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/modules/finance/`
Expected: 看到 index.js 文件

**Step 3: Commit**

```bash
git add js/modules/finance/index.js
git commit -m "feat(modules): add FinanceModule with stats and charts"
```

---

## Task 12: 创建认证模块 (Auth Module)

**Files:**
- Create: `js/modules/auth/index.js`

**Step 1: 编写认证模块代码**

```javascript
/**
 * 认证模块
 */
import { BaseModule } from '../../core/base-module.js';
import { Events } from '../../core/event-bus.js';

export class AuthModule extends BaseModule {
    constructor(options = {}) {
        super({
            name: 'AuthModule',
            statePath: 'auth',
            ...options
        });
    }

    getDefaultState() {
        return {
            currentUser: null,
            isAuthenticated: false,
            loading: false
        };
    }

    bindEvents() {
        // 监听会话过期事件
        this.on(Events.AUTH_SESSION_EXPIRED, () => {
            this.logout();
            this.showToast('会话已过期，请重新登录', 'warning');
        });
    }

    async onInit() {
        // 检查登录状态
        await this.checkAuth();
    }

    /**
     * 检查认证状态
     */
    async checkAuth() {
        const currentUser = typeof UserAPI !== 'undefined'
            ? UserAPI.getCurrentUser()
            : null;

        if (currentUser) {
            this.setState('currentUser', currentUser);
            this.setState('isAuthenticated', true);
            this.updateUserUI(currentUser);
        }
    }

    /**
     * 登录
     */
    async login(username, password) {
        this.setState('loading', true);

        try {
            const user = typeof UserAPI !== 'undefined'
                ? await UserAPI.login(username, password)
                : null;

            if (user) {
                this.setState('currentUser', user);
                this.setState('isAuthenticated', true);

                this.emit(Events.AUTH_LOGIN, { user });

                if (typeof AuditLogAPI !== 'undefined') {
                    AuditLogAPI.create('用户登录', `用户 ${username} 登录成功`);
                }

                this.updateUserUI(user);

                return { success: true, user };
            }

            return { success: false, message: '用户名或密码错误' };
        } catch (error) {
            console.error('Login error:', error);
            return { success: false, message: '登录失败，请稍后重试' };
        } finally {
            this.setState('loading', false);
        }
    }

    /**
     * 登出
     */
    logout() {
        const currentUser = this.getState('currentUser');

        if (typeof UserAPI !== 'undefined') {
            UserAPI.logout();
        }

        this.setState('currentUser', null);
        this.setState('isAuthenticated', false);

        this.emit(Events.AUTH_LOGOUT, { user: currentUser });

        if (typeof AuditLogAPI !== 'undefined' && currentUser) {
            AuditLogAPI.create('用户登出', `用户 ${currentUser.username} 登出`);
        }

        this.updateUserUI(null);
    }

    /**
     * 更新用户 UI
     */
    updateUserUI(user) {
        const usernameEl = document.getElementById('currentUsername');
        const loginBtn = document.getElementById('loginBtn');

        if (usernameEl) {
            usernameEl.textContent = user ? (user.realName || user.username) : '未登录';
        }

        if (loginBtn) {
            if (user) {
                loginBtn.textContent = '登出';
                loginBtn.onclick = () => this.logout();
            } else {
                loginBtn.textContent = '登录';
                loginBtn.onclick = () => this.showLoginModal();
            }
        }
    }

    /**
     * 显示登录模态框
     */
    showLoginModal() {
        const modal = document.getElementById('loginModal');
        if (modal) {
            modal.style.display = 'flex';
            modal.classList.add('active');
        }
    }

    /**
     * 隐藏登录模态框
     */
    hideLoginModal() {
        const modal = document.getElementById('loginModal');
        const form = document.getElementById('loginForm');

        if (modal) {
            modal.style.display = 'none';
            modal.classList.remove('active');
        }

        if (form) {
            form.reset();
        }
    }

    /**
     * 检查权限
     */
    hasPermission(permission) {
        const user = this.getState('currentUser');

        if (!user) return false;

        const permissions = {
            'admin': ['*'],
            'editor': ['create', 'read', 'update'],
            'viewer': ['read']
        };

        if (user.role === 'admin') return true;

        return permissions[user.role]?.includes(permission) || false;
    }

    /**
     * 获取当前用户
     */
    getCurrentUser() {
        return this.getState('currentUser');
    }

    /**
     * 是否已认证
     */
    isAuthenticated() {
        return this.getState('isAuthenticated');
    }
}

export default AuthModule;

if (typeof window !== 'undefined') {
    window.AuthModule = AuthModule;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/modules/auth/`
Expected: 看到 index.js 文件

**Step 3: Commit**

```bash
git add js/modules/auth/index.js
git commit -m "feat(modules): add AuthModule for authentication"
```

---

## Task 13: 创建应用入口文件

**Files:**
- Create: `js/app.js`

**Step 1: 编写应用入口代码**

```javascript
/**
 * 应用入口文件
 * 初始化核心模块和业务模块
 */
import { initCore, router, eventBus, Events } from './core/index.js';
import { ProjectModule } from './modules/projects/index.js';
import { PlayerModule } from './modules/players/index.js';
import { OrganizationModule } from './modules/organizations/index.js';
import { FinanceModule } from './modules/finance/index.js';
import { AuthModule } from './modules/auth/index.js';

/**
 * 应用类
 */
class App {
    constructor() {
        this.modules = {};
        this.initialized = false;
    }

    /**
     * 初始化应用
     */
    async init() {
        if (this.initialized) {
            console.warn('App already initialized');
            return;
        }

        console.log('Initializing application...');

        // 初始化核心模块
        await this.initCore();

        // 初始化业务模块
        await this.initModules();

        // 初始化路由
        this.initRouter();

        // 初始化事件监听
        this.initEventListeners();

        // 兼容旧代码
        this.initLegacyCompatibility();

        this.initialized = true;

        console.log('Application initialized');
    }

    /**
     * 初始化核心模块
     */
    async initCore() {
        await initCore({
            routes: {
                'dashboard': { path: '/', title: '概览' },
                'projects': { path: '/projects', title: '项目' },
                'organizations': { path: '/organizations', title: '机构' },
                'players': { path: '/players', title: '选手' },
                'finance': { path: '/finance', title: '运营' },
                'archive': { path: '/archive', title: '归档管理' },
                'settings': { path: '/settings', title: '设置' }
            }
        });
    }

    /**
     * 初始化业务模块
     */
    async initModules() {
        // 创建模块实例
        this.modules.auth = new AuthModule();
        this.modules.projects = new ProjectModule();
        this.modules.players = new PlayerModule();
        this.modules.organizations = new OrganizationModule();
        this.modules.finance = new FinanceModule();

        // 初始化模块
        await Promise.all([
            this.modules.auth.init(),
            this.modules.projects.init(),
            this.modules.players.init(),
            this.modules.organizations.init(),
            this.modules.finance.init()
        ]);
    }

    /**
     * 初始化路由
     */
    initRouter() {
        // 监听路由变化
        router.beforeEach((to, from) => {
            // 可以在这里添加权限检查
            return true;
        });

        router.afterEach((to, from) => {
            // 更新导航状态
            this.updateNavigation(to.name);
        });

        // 绑定导航点击事件
        document.querySelectorAll('.nav-item[data-page]').forEach(item => {
            item.addEventListener('click', () => {
                const page = item.dataset.page;
                this.navigateTo(page);
            });
        });
    }

    /**
     * 初始化事件监听
     */
    initEventListeners() {
        // 监听 Toast 事件
        eventBus.on(Events.UI_TOAST, ({ message, type }) => {
            this.showToast(message, type);
        });

        // 监听页面变更事件
        eventBus.on(Events.UI_PAGE_CHANGED, ({ page, id, editId }) => {
            this.handlePageChange(page, id, editId);
        });
    }

    /**
     * 兼容旧代码
     */
    initLegacyCompatibility() {
        // 将模块挂载到全局
        window.App = this;
        window.app = this;

        // 兼容旧的 UI 对象
        if (typeof UI !== 'undefined') {
            // 保留必要的兼容方法
            window.UI = {
                ...UI,
                navigateTo: (page, params) => this.navigateTo(page, params),
                showToast: (message, type) => this.showToast(message, type),
                renderAll: () => this.renderAll()
            };
        }

        // 兼容旧的导航函数
        window.navigateTo = (page, params) => this.navigateTo(page, params);
    }

    /**
     * 导航到指定页面
     */
    navigateTo(page, params = {}) {
        // 更新导航状态
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === page);
        });

        // 更新页面显示
        document.querySelectorAll('.page').forEach(p => {
            p.classList.toggle('active', p.id === `page-${page}`);
        });

        // 发布路由变更事件
        eventBus.emit(Events.UI_PAGE_CHANGED, { page, ...params });
    }

    /**
     * 处理页面变更
     */
    handlePageChange(page, id, editId) {
        // 根据页面类型执行相应操作
        switch (page) {
            case 'projects':
                this.modules.projects?.refreshList();
                break;
            case 'players':
                this.modules.players?.refreshList();
                break;
            case 'organizations':
                this.modules.organizations?.refreshList();
                break;
            case 'finance':
                this.modules.finance?.refreshList();
                break;
        }
    }

    /**
     * 更新导航状态
     */
    updateNavigation(page) {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === page);
        });
    }

    /**
     * 显示 Toast 消息
     */
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => toast.remove(), 3000);
    }

    /**
     * 渲染所有模块
     */
    renderAll() {
        this.modules.projects?.renderList();
        this.modules.players?.renderList();
        this.modules.organizations?.renderList();
        this.modules.finance?.renderList();
    }

    /**
     * 获取模块
     */
    getModule(name) {
        return this.modules[name];
    }
}

// 创建应用实例
const app = new App();

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', async () => {
    // 先初始化数据存储
    if (typeof DataStore !== 'undefined') {
        await DataStore.init();
    }

    // 初始化应用
    await app.init();

    // 初始化其他旧模块
    if (typeof initPerformanceOptimizations === 'function') {
        initPerformanceOptimizations();
    }

    if (typeof ArchiveManager !== 'undefined') {
        ArchiveManager.init();
    }
});

// 导出
export { App, app };
export default app;

// 兼容旧代码
if (typeof window !== 'undefined') {
    window.App = App;
    window.app = app;
}
```

**Step 2: 验证文件创建**

Run: `ls -la js/`
Expected: 看到 app.js 文件

**Step 3: Commit**

```bash
git add js/app.js
git commit -m "feat: add application entry file with module initialization"
```

---

## Task 14: 更新 HTML 入口文件

**Files:**
- Modify: `index.html`

**Step 1: 添加模块脚本标签**

在 `index.html` 的 `<head>` 部分添加：

```html
<!-- 核心模块（ES6 模块） -->
<script type="module" src="js/app.js"></script>
```

**Step 2: 添加向后兼容脚本**

在现有脚本之前添加：

```html
<!-- 向后兼容层 -->
<script>
    // 确保全局对象存在
    window.EventBus = window.EventBus || class EventBus {
        constructor() { this.events = new Map(); }
        on(event, callback) {
            if (!this.events.has(event)) this.events.set(event, []);
            this.events.get(event).push(callback);
            return () => this.off(event, callback);
        }
        emit(event, data) {
            if (!this.events.has(event)) return;
            this.events.get(event).forEach(cb => cb(data));
        }
        off(event, callback) {
            if (!this.events.has(event)) return;
            const listeners = this.events.get(event);
            const index = listeners.indexOf(callback);
            if (index !== -1) listeners.splice(index, 1);
        }
    };

    window.eventBus = window.eventBus || new window.EventBus();
</script>
```

**Step 3: Commit**

```bash
git add index.html
git commit -m "feat: update HTML entry to support ES6 modules"
```

---

## Task 15: 创建迁移指南文档

**Files:**
- Create: `docs/MIGRATION_GUIDE.md`

**Step 1: 编写迁移指南**

```markdown
# 前端架构迁移指南

## 概述

本次重构将现有的单体前端架构迁移到模块化架构，采用 ES6 模块、事件总线和状态管理模式。

## 架构变化

### 旧架构
- 全局变量和函数
- 紧耦合的 UI 和数据
- 难以测试和维护

### 新架构
- ES6 模块化
- 事件驱动通信
- 集中式状态管理
- 清晰的模块边界

## 迁移步骤

### 1. 渐进式迁移

新架构支持渐进式迁移，可以逐步将旧代码迁移到新模块：

```javascript
// 旧代码
function saveProject() {
    const data = { ... };
    ProjectAPI.create(data);
    UI.renderAll();
}

// 新代码
import { eventBus, Events } from './core/event-bus.js';

async function saveProject() {
    const data = { ... };
    await projectModule.create(data);
    // 事件会自动触发，无需手动调用 renderAll
}
```

### 2. 兼容层

新架构提供了兼容层，确保旧代码继续工作：

```javascript
// 全局对象保持可用
window.UI.navigateTo('projects');
window.eventBus.emit('custom:event', data);

// 旧的 API 对象保持可用
ProjectAPI.create(data);
PlayerAPI.update(id, data);
```

### 3. 模块迁移

将现有的 UI 代码迁移到模块：

1. 创建模块类继承 BaseModule
2. 实现 getDefaultState() 返回初始状态
3. 实现 bindEvents() 绑定事件
4. 实现 renderList() 等渲染方法
5. 将业务逻辑移入模块方法

## 使用新架构

### 事件总线

```javascript
import { eventBus, Events } from './core/event-bus.js';

// 订阅事件
eventBus.on(Events.ENTITY_CREATED, (data) => {
    console.log('Entity created:', data);
});

// 发布事件
eventBus.emit(Events.ENTITY_CREATED, {
    entity: 'project',
    data: project
});
```

### 状态管理

```javascript
import { stateManager } from './core/state-manager.js';

// 获取状态
const projects = stateManager.get('projects.list');

// 设置状态
stateManager.set('projects.filter', { status: '进行中' });

// 订阅状态变化
stateManager.subscribe('projects.list', (newValue, oldValue) => {
    console.log('Projects changed:', newValue);
});
```

### 路由

```javascript
import { router } from './core/router.js';

// 导航
router.navigate('projects');

// 添加路由守卫
router.beforeEach((to, from) => {
    // 权限检查
    return true;
});
```

### 创建新模块

```javascript
import { BaseModule } from '../../core/base-module.js';
import { Events } from '../../core/event-bus.js';

export class MyModule extends BaseModule {
    constructor(options = {}) {
        super({
            name: 'MyModule',
            statePath: 'myModule',
            ...options
        });
    }

    getDefaultState() {
        return {
            data: [],
            loading: false
        };
    }

    bindEvents() {
        this.on(Events.DATA_LOADED, () => {
            this.refreshData();
        });
    }

    async onInit() {
        await this.refreshData();
    }

    async refreshData() {
        this.setState('loading', true);
        // 加载数据...
        this.setState('loading', false);
    }
}
```

## 注意事项

1. **不要破坏现有功能** - 保持向后兼容
2. **渐进式迁移** - 逐步迁移，不要一次性重写
3. **测试覆盖** - 确保迁移后功能正常
4. **文档更新** - 及时更新相关文档

## 回滚方案

如果新架构出现问题，可以：

1. 移除 `<script type="module" src="js/app.js"></script>`
2. 保留旧的脚本标签
3. 应用会使用旧的架构运行

## 支持

如有问题，请联系开发团队。
```

**Step 2: Commit**

```bash
git add docs/MIGRATION_GUIDE.md
git commit -m "docs: add migration guide for frontend architecture"
```

---

## 完成后的文件结构

```
js/
├── core/                      # 核心模块
│   ├── index.js              # 核心模块导出
│   ├── event-bus.js          # 事件总线
│   ├── state-manager.js      # 状态管理器
│   ├── router.js             # 路由管理器
│   ├── base-module.js        # 基础模块类
│   └── module-loader.js      # 模块加载器
├── modules/                   # 业务模块
│   ├── projects/
│   │   └── index.js          # 项目模块
│   ├── players/
│   │   └── index.js          # 选手模块
│   ├── organizations/
│   │   └── index.js          # 机构模块
│   ├── finance/
│   │   └── index.js          # 财务模块
│   └── auth/
│       └── index.js          # 认证模块
├── app.js                     # 应用入口
├── api.js                     # API 封装（保留）
├── ui.js                      # UI 控制器（保留，兼容层）
├── data-store.js              # 数据存储（保留）
└── ...                        # 其他文件（保留）
```

---

## 验证清单

- [ ] 所有核心模块文件已创建
- [ ] 所有业务模块文件已创建
- [ ] 应用入口文件已创建
- [ ] HTML 文件已更新
- [ ] 迁移指南已创建
- [ ] 所有文件已提交到 Git
- [ ] 应用可以正常启动
- [ ] 旧功能正常工作
- [ ] 新模块可以正常加载

---

## 后续工作

1. **完善模块** - 为其他页面创建模块
2. **测试覆盖** - 编写单元测试
3. **性能优化** - 实现懒加载
4. **文档完善** - 更新 API 文档
5. **代码清理** - 移除废弃代码
