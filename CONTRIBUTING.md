# 贡献指南

感谢你对本项目的关注！欢迎提交 Issue 和 Pull Request。

## 开发环境搭建

1. Fork 并克隆仓库
2. 安装前端依赖：`npm install`
3. 安装 Python 依赖：`pip install -r requirements.txt`
4. 启动后端：`python server.py`
5. 启动前端开发服务器：`npm run dev`
6. 浏览器访问 http://localhost:3004

## 代码规范

### 前端（Vue 3）

- 使用 Composition API + `<script setup>`
- 组件命名：PascalCase（如 `PlayerDetail.vue`）
- 样式使用 `<style scoped>` + CSS 变量（`var(--xxx)`）
- 遵循项目已有的主题变量体系（亮色/深色模式）

### 后端（Python）

- 遵循 PEP 8
- 新 API 路由添加到 `server/` 模块目录下
- 使用 `BaseHandler` 中的 `send_json_response` / `send_error` 统一响应格式
- 需要认证的接口使用 `@require_auth` 装饰器
- 需要权限校验的接口使用 `_check_auth_and_permission` 方法

## 提交规范

提交信息使用中文或英文均可，建议格式：

```
<类型>: <描述>

# 类型：
# feat: 新功能
# fix: 修复 Bug
# docs: 文档更新
# style: 代码格式调整
# refactor: 重构
# perf: 性能优化
# test: 测试
# chore: 构建/工具变动
```

## PR 流程

1. 创建功能分支：`feat/xxx` 或 `fix/xxx`
2. 确保本地测试通过
3. 提交 PR 并描述变更内容
4. 等待 Review

## 安全问题

如发现安全漏洞，请勿公开提交 Issue，请通过邮件私下联系维护者。
