# 插件开发指南

本文档介绍如何为媒体艺术展览工作台开发插件。

## 目录

1. [概述](#概述)
2. [快速开始](#快速开始)
3. [插件结构](#插件结构)
4. [生命周期](#生命周期)
5. [插件API](#插件api)
6. [扩展点](#扩展点)
7. [配置管理](#配置管理)
8. [权限系统](#权限系统)
9. [最佳实践](#最佳实践)
10. [示例插件](#示例插件)

---

## 概述

插件系统允许开发者扩展工作台的功能，而无需修改核心代码。插件可以：

- 添加新的功能模块
- 扩展现有功能
- 自定义主题和样式
- 处理和转换数据
- 集成第三方服务

### 插件类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `feature` | 功能扩展插件 | 新增报表功能 |
| `theme` | 主题插件 | 深色主题 |
| `data-processor` | 数据处理插件 | 数据导入导出 |
| `ui-extension` | UI扩展插件 | 自定义侧边栏 |
| `integration` | 集成插件 | 第三方服务集成 |
| `utility` | 工具插件 | 批量操作工具 |

---

## 快速开始

### 创建第一个插件

```javascript
// js/plugins/my-plugin.js
import { BasePlugin } from './plugin-interface.js';

export class MyPlugin extends BasePlugin {
    // 1. 定义插件元数据
    static meta = {
        id: 'vendor.my-plugin',
        name: '我的插件',
        version: '1.0.0',
        description: '这是一个示例插件',
        author: 'Your Name',
        engines: {
            workbench: '^2.0.0'
        }
    };

    // 2. 定义配置模式
    static configSchema = {
        enabled: {
            type: 'boolean',
            label: '启用功能',
            default: true
        }
    };

    // 3. 实现生命周期方法
    async install() {
        console.log('插件安装中...');
    }

    async enable() {
        console.log('插件启用中...');
        
        // 订阅事件
        this.subscribe('player:created', (player) => {
            console.log('新选手创建:', player.name);
        });
    }

    async disable() {
        console.log('插件禁用中...');
    }
}

export default MyPlugin;
```

### 注册和启用插件

```javascript
import { pluginManager } from './plugins/plugin-manager.js';
import { MyPlugin } from './plugins/my-plugin.js';

// 注册插件
await pluginManager.register('vendor.my-plugin', MyPlugin);

// 安装插件
await pluginManager.install('vendor.my-plugin');

// 启用插件
await pluginManager.enable('vendor.my-plugin');
```

---

## 插件结构

### 目录结构

```
js/plugins/
├── plugin-interface.js    # 插件接口定义
├── plugin-manager.js      # 插件管理器
├── index.js               # 主入口
└── examples/              # 示例插件
    ├── stats-plugin.js    # 统计插件
    ├── theme-plugin.js    # 主题插件
    └── index.js           # 示例索引
```

### 插件文件结构

```
my-plugin/
├── index.js           # 插件入口
├── plugin.js          # 插件主类
├── components/        # UI组件（可选）
│   └── Panel.js
├── styles/            # 样式文件（可选）
│   └── plugin.css
└── assets/            # 静态资源（可选）
    └── icon.svg
```

### 元数据定义

```javascript
static meta = {
    // 必填字段
    id: 'vendor.plugin-name',      // 插件ID（格式：vendor.plugin-name）
    name: '插件名称',               // 显示名称
    version: '1.0.0',              // 语义化版本
    description: '插件描述',        // 功能描述
    author: '作者名称',             // 作者

    // 可选字段
    homepage: 'https://...',       // 主页
    license: 'MIT',                // 许可证
    keywords: ['tag1', 'tag2'],    // 关键词
    categories: ['utility'],       // 分类
    icon: '📊',                    // 图标

    // 运行环境要求
    engines: {
        workbench: '^2.0.0'        // 工作台版本要求
    },

    // 插件依赖
    dependencies: {
        'vendor.other-plugin': '^1.0.0'
    },

    // 默认配置
    config: {
        enabled: true
    }
};
```

---

## 生命周期

插件生命周期包含以下阶段：

```
注册 -> 安装 -> 启用 <-> 禁用 -> 卸载
```

### 生命周期方法

```javascript
class MyPlugin extends BasePlugin {
    // 安装时调用（仅首次）
    async install() {
        // 初始化数据结构
        // 创建必要的存储
    }

    // 卸载时调用
    async uninstall() {
        // 清理所有数据
        // 移除UI元素
    }

    // 启用时调用
    async enable() {
        // 激活功能
        // 注册事件监听
        // 显示UI
    }

    // 禁用时调用
    async disable() {
        // 暂停功能
        // 移除事件监听
        // 隐藏UI
    }

    // 更新时调用
    async update(fromVersion, toVersion) {
        // 数据迁移
        // 配置升级
    }

    // 配置变更时调用
    async onConfigChange(newConfig, oldConfig) {
        // 响应配置变更
    }
}
```

### 状态流转

| 状态 | 说明 |
|------|------|
| `installed` | 已安装但未启用 |
| `enabled` | 已启用，功能可用 |
| `disabled` | 已禁用，功能暂停 |
| `error` | 发生错误 |

---

## 插件API

### 上下文对象

每个插件实例都有一个 `context` 对象，提供访问核心功能的接口：

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        // 事件总线
        this.context.eventBus.emit('custom:event', data);
        
        // 状态管理
        this.context.stateManager.setState('key', value);
        
        // 数据存储
        const data = this.context.dataStore.data;
        
        // API客户端
        const result = await this.context.api.fetch('/endpoint');
        
        // 路由
        this.context.router.navigate('/path');
        
        // 日志
        this.context.logger.info('消息');
    }
}
```

### 便捷方法

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        // 订阅事件（自动清理）
        this.subscribe('event:name', (data) => {
            console.log(data);
        });

        // 发布事件
        await this.publish('event:name', { foo: 'bar' });

        // 获取/设置状态
        const value = this.getState('key');
        this.setState('key', value);

        // 获取数据存储
        const store = this.getDataStore();

        // 显示通知
        this.showNotification('标题', '内容', 'success');

        // 日志
        this.log('info', '消息', { data });
    }
}
```

---

## 扩展点

扩展点允许插件在特定位置注入功能。

### 内置扩展点

```javascript
import { ExtensionPoints } from './plugin-interface.js';

// 数据处理
ExtensionPoints.DATA_BEFORE_SAVE    // 数据保存前
ExtensionPoints.DATA_AFTER_LOAD     // 数据加载后
ExtensionPoints.DATA_TRANSFORM      // 数据转换

// UI扩展
ExtensionPoints.UI_HEADER           // 页头
ExtensionPoints.UI_SIDEBAR          // 侧边栏
ExtensionPoints.UI_FOOTER           // 页脚
ExtensionPoints.UI_SETTINGS_PANEL   // 设置面板
ExtensionPoints.UI_CONTEXT_MENU     // 右键菜单

// 路由
ExtensionPoints.ROUTE_BEFORE_NAVIGATE  // 导航前
ExtensionPoints.ROUTE_AFTER_NAVIGATE   // 导航后

// 选手管理
ExtensionPoints.PLAYER_BEFORE_CREATE   // 创建选手前
ExtensionPoints.PLAYER_AFTER_CREATE    // 创建选手后
ExtensionPoints.PLAYER_BEFORE_UPDATE   // 更新选手前
ExtensionPoints.PLAYER_AFTER_UPDATE    // 更新选手后
ExtensionPoints.PLAYER_BEFORE_DELETE   // 删除选手前
ExtensionPoints.PLAYER_AFTER_DELETE    // 删除选手后

// 项目管理
ExtensionPoints.PROJECT_BEFORE_CREATE
ExtensionPoints.PROJECT_AFTER_CREATE
ExtensionPoints.PROJECT_BEFORE_UPDATE
ExtensionPoints.PROJECT_AFTER_UPDATE
ExtensionPoints.PROJECT_BEFORE_DELETE
ExtensionPoints.PROJECT_AFTER_DELETE

// 文件处理
ExtensionPoints.FILE_BEFORE_UPLOAD
ExtensionPoints.FILE_AFTER_UPLOAD
ExtensionPoints.FILE_BEFORE_DOWNLOAD
ExtensionPoints.FILE_AFTER_DOWNLOAD
```

### 注册扩展点

```javascript
class MyPlugin extends BasePlugin {
    static extensions = [
        {
            point: ExtensionPoints.PLAYER_AFTER_CREATE,
            handler: 'onPlayerCreated',
            priority: 10  // 数字越小优先级越高
        }
    ];

    onPlayerCreated(player) {
        console.log('选手创建:', player.name);
        return player;  // 可以修改返回值
    }
}
```

### 执行扩展点

```javascript
// 异步执行
const results = await pluginManager.executeExtension(
    ExtensionPoints.PLAYER_AFTER_CREATE,
    playerData
);

// 同步执行（用于拦截器）
const modifiedData = pluginManager.executeExtensionSync(
    ExtensionPoints.DATA_TRANSFORM,
    originalData
);
```

---

## 配置管理

### 定义配置模式

```javascript
static configSchema = {
    // 字符串类型
    name: {
        type: 'string',
        label: '名称',
        description: '插件显示名称',
        default: 'My Plugin',
        required: true,
        pattern: '^[a-zA-Z0-9]+$'  // 正则验证
    },

    // 数字类型
    timeout: {
        type: 'number',
        label: '超时时间',
        description: '请求超时时间（毫秒）',
        default: 5000,
        min: 1000,
        max: 60000
    },

    // 布尔类型
    enabled: {
        type: 'boolean',
        label: '启用',
        default: true
    },

    // 单选类型
    mode: {
        type: 'select',
        label: '模式',
        default: 'auto',
        options: [
            { value: 'auto', label: '自动' },
            { value: 'manual', label: '手动' }
        ]
    },

    // 多选类型
    features: {
        type: 'multiselect',
        label: '功能',
        default: ['feature1'],
        options: [
            { value: 'feature1', label: '功能1' },
            { value: 'feature2', label: '功能2' }
        ]
    }
};
```

### 访问配置

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        // 读取配置
        const timeout = this.config.timeout;
        const mode = this.config.mode;

        // 验证配置
        const validation = this.validateConfig(this.config);
        if (!validation.valid) {
            console.error('配置错误:', validation.errors);
        }
    }

    // 响应配置变更
    async onConfigChange(newConfig, oldConfig) {
        if (newConfig.timeout !== oldConfig.timeout) {
            this._updateTimeout(newConfig.timeout);
        }
    }
}
```

### 更新配置

```javascript
// 更新插件配置
await pluginManager.updateConfig('vendor.my-plugin', {
    timeout: 10000,
    mode: 'manual'
});
```

---

## 权限系统

### 定义权限需求

```javascript
static permissions = [
    {
        name: 'data:read',
        description: '读取项目数据',
        default: 'grant'  // grant | deny | ask
    },
    {
        name: 'data:write',
        description: '修改项目数据',
        default: 'ask'
    },
    {
        name: 'notification:create',
        description: '创建通知',
        default: 'grant'
    }
];
```

### 权限检查

```javascript
class MyPlugin extends BasePlugin {
    async saveData(data) {
        // 检查权限
        if (!this.context.permissionAPI?.check('data:write')) {
            throw new Error('没有写入权限');
        }

        // 执行操作
        await this.context.dataStore.save(data);
    }
}
```

---

## 最佳实践

### 1. 资源清理

始终在 `disable` 或 `uninstall` 中清理资源：

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        // 使用 subscribe 而不是 eventBus.on
        // subscribe 会在清理时自动取消订阅
        this.subscribe('event:name', this.handleEvent);
        
        // 保存定时器引用
        this._timer = setInterval(() => {}, 1000);
    }

    async disable() {
        // 清理定时器
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
        
        // 调用父类清理方法
        await this.cleanup();
    }
}
```

### 2. 错误处理

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        try {
            await this._initializeFeature();
        } catch (error) {
            this.log('error', '启用失败', error);
            this.status = PluginStatus.ERROR;
            this.error = error;
            throw error;
        }
    }
}
```

### 3. 懒加载

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        // 只在需要时加载大型依赖
        if (this.config.showCharts) {
            const { ChartLibrary } = await import('./chart-lib.js');
            this._chartLib = new ChartLibrary();
        }
    }
}
```

### 4. 配置验证

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        const validation = this.validateConfig(this.config);
        if (!validation.valid) {
            this.showNotification(
                '配置错误',
                validation.errors.join('\n'),
                'error'
            );
            return;
        }
    }
}
```

### 5. 版本兼容性

```javascript
static meta = {
    id: 'vendor.my-plugin',
    version: '1.0.0',
    engines: {
        workbench: '^2.0.0'  // 兼容 2.x 版本
    },
    dependencies: {
        'vendor.utils': '^1.0.0'
    }
};
```

---

## 示例插件

### 统计插件

查看 [stats-plugin.js](./js/plugins/examples/stats-plugin.js) 了解如何：

- 实现数据统计功能
- 创建统计面板UI
- 使用扩展点监听数据变更
- 实现自动刷新机制

### 主题插件

查看 [theme-plugin.js](./js/plugins/examples/theme-plugin.js) 了解如何：

- 实现主题切换功能
- 管理CSS变量
- 创建自定义主题
- 保存用户偏好

---

## 调试

### 启用调试模式

```javascript
// 全局调试
pluginManager.setDebug(true);

// 查看所有插件
console.log(pluginManager.getAllPlugins());

// 查看已启用的插件
console.log(pluginManager.getEnabledPlugins());

// 查看扩展点处理器
console.log(pluginManager.extensionHandlers);
```

### 日志

```javascript
class MyPlugin extends BasePlugin {
    async enable() {
        this.log('info', '信息日志');
        this.log('warn', '警告日志');
        this.log('error', '错误日志');
        this.log('debug', '调试日志');
    }
}
```

---

## 发布插件

### 检查清单

- [ ] 插件ID符合格式要求（vendor.plugin-name）
- [ ] 版本号符合语义化版本规范
- [ ] 元数据完整（name, version, description, author）
- [ ] 配置模式定义正确
- [ ] 权限需求声明完整
- [ ] 资源正确清理
- [ ] 错误处理完善
- [ ] 文档注释完整

### 打包

```bash
# 创建插件包
zip -r my-plugin.zip my-plugin/

# 包含的内容
my-plugin/
├── index.js
├── plugin.js
├── README.md
└── package.json  # 可选，用于 npm 发布
```

---

## 常见问题

### Q: 如何访问全局数据？

```javascript
const data = this.getDataStore().data;
const players = data.players;
```

### Q: 如何添加自定义路由？

```javascript
async enable() {
    this.context.router.register({
        path: '/my-plugin',
        component: MyComponent
    });
}
```

### Q: 如何与其他插件通信？

```javascript
// 发布事件
this.publish('my-plugin:event', data);

// 其他插件订阅
this.subscribe('my-plugin:event', (data) => {
    // 处理事件
});
```

### Q: 如何存储插件数据？

```javascript
// 使用 localStorage
localStorage.setItem('my-plugin-data', JSON.stringify(data));

// 或使用状态管理
this.setState('my-plugin.data', data);
```

---

## 更新日志

### v1.0.0 (2026-03-06)

- 初始版本
- 实现插件接口规范
- 实现插件管理器
- 添加统计插件示例
- 添加主题插件示例
