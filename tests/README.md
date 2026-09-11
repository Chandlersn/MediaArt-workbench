# 测试指南

## 运行测试

```bash
# 运行所有测试
npm test

# 监听模式（开发时使用）
npm run test:watch
```

## 测试结构

```
tests/
├── run.js                    # 测试运行器
├── unit/                     # 单元测试
│   └── virtual-list.test.js  # 虚拟列表组件测试
└── integration/              # 集成测试（待添加）
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
- 集成测试需要启动服务器
