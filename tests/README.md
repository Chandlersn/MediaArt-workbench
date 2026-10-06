# 测试指南

## 运行测试

```bash
# 前端单元及回归测试
npm test

# 监听模式（开发时使用）
npm run test:watch

# 后端、权限、持久化、启动器和业务 API 回归
python -m pytest tests/python -q

# 静态检查
npm run lint:quiet
npm run check

# 构建后运行真实浏览器完整业务验收
npm run test:e2e
```

Python 依赖见根目录 `requirements.txt`。浏览器验收需要 Python 3.9 或以上、Node.js 20 或以上；Windows 默认使用已安装的 Microsoft Edge，其他平台需先执行 `npx playwright install chromium`。

## 浏览器验收

`npm run test:e2e` 会构建前端，再把 `server` 和 `dist` 复制到系统临时目录，使用空数据库与专用测试账号，在 `127.0.0.1:18080` 启动真实后端。不会复制或修改项目内的业务数据库、上传目录和账号文件，也不会复用已运行的服务。端口被占用时直接报错。

验收步骤包括登录、首次引导、新建项目和机构、添加选手、分阶段上传及删除资料、刷新后的缺料状态、证书重复同步、模板编辑、打印预览与归档重打、备份后的修改和恢复，以及退出登录。预览使用真实生成文档，但屏蔽浏览器 `window.print()`，不会向实体打印机发送作业。

证书打印专项验收覆盖按所选证书和模板检查、切换模板复检、定位作品名称补录、取消修改、保存失败保留输入、保存后复检，以及筛选结果变化后仍按原批次打印和归档。同号不同批次的数据分开验证。

界面专项还覆盖作品名称和指导老师的表格补录、Enter 保存后连续定位、Esc 取消、失败重试、导出和更多菜单，以及内嵌预览的逐份切换、缩放、失败重试和数据变化后的重新确认。预览使用真实打印排版，单独查看预览不会新增打印记录。

若 Python 不在 PATH 中，可在 PowerShell 指定已安装依赖的解释器：

```powershell
$env:WORKBENCH_TEST_PYTHON = 'C:\path\to\venv\Scripts\python.exe'
npm run test:e2e
```

可选环境变量：`WORKBENCH_E2E_PORT` 指定独立测试端口（禁止 8080），`WORKBENCH_TEST_BROWSER` 指定已安装的浏览器通道，如 `msedge` 或 `chrome`。默认无头运行；调试时先构建，再执行 `npx playwright test --headed`。

HTML 报告位于 `test-results/report/index.html`。失败时保存截图和 trace，可用 `npx playwright show-report test-results/report` 查看报告。测试完成后通过仅存在于验收服务器的令牌保护接口退出，并清理临时目录。

这些检查覆盖核心业务链路，不代表实体打印效果、安装包分发或所有页面都已经验收。

## 测试结构

```
tests/
├── run.js                    # 前端测试运行器（会等待异步测试）
├── unit/                     # Store、请求、表单、资料、证书及打印回归
├── python/                   # pytest 后端与启动器测试，使用隔离数据
└── e2e/                      # Playwright 界面与真实后端验收
```

## 编写测试

### 单元测试示例

```javascript
/**
 * 示例：模块单元测试
 */

describe('ModuleName', () => {

  beforeEach(() => {
    // 每个测试前执行
  });

  afterEach(() => {
    // 每个测试后执行
  });

  describe('methodName', () => {
    it('应该正确处理输入', () => {
      const result = methodName(input);
      assertEqual(result, expected);
    });

    it('应该抛出错误当输入无效', () => {
      assertThrows(() => {
        methodName(invalidInput);
      }, '应该抛出错误');
    });
  });

});
```

### 断言函数

| 函数 | 说明 |
|-----|-----|
| `assert(condition, message)` | 条件为真 |
| `assertEqual(actual, expected)` | 值相等 |
| `assertDeepEqual(actual, expected)` | 对象/数组相等 |
| `assertThrows(fn)` | 函数抛出错误 |

## 添加新测试

1. 在 `tests/unit/` 目录下创建 `*.test.js` 文件
2. 编写测试用例
3. 运行 `npm test` 验证

## 注意事项

- 测试应该在 Node.js 环境中可运行
- 涉及 DOM 的测试需要模拟 DOM 环境
- 浏览器验收会自行启动和关闭隔离服务器，无需先运行工作台
