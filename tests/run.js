/**
 * 测试运行器
 * 简单的测试框架，用于运行单元测试和集成测试
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 测试统计
const stats = {
  total: 0,
  passed: 0,
  failed: 0,
  errors: []
};

// 简单的断言函数
function assert(condition, message) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`Expected ${expected}, got ${actual}${message ? ': ' + message : ''}`);
  }
}

function assertDeepEqual(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}${message ? ': ' + message : ''}`);
  }
}

function assertThrows(fn, message) {
  try {
    fn();
    throw new Error(`Expected function to throw, but it didn't${message ? ': ' + message : ''}`);
  } catch (e) {
    if (e.message.includes('Expected function to throw')) {
      throw e;
    }
  }
}

// 全局断言
global.assert = assert;
global.assertEqual = assertEqual;
global.assertDeepEqual = assertDeepEqual;
global.assertThrows = assertThrows;
global.describe = describe;
global.it = it;
global.beforeEach = beforeEach;
global.afterEach = afterEach;

/**
 * 描述测试套件
 */
function describe(name, fn) {
  console.log(`\n${name}`);
  fn();
}

/**
 * 定义测试用例
 */
function it(name, fn) {
  stats.total++;
  const startTime = Date.now();

  try {
    fn();
    const duration = Date.now() - startTime;
    stats.passed++;
    console.log(`  ✓ ${name} (${duration}ms)`);
  } catch (e) {
    stats.failed++;
    stats.errors.push({ name, error: e });
    console.log(`  ✗ ${name}`);
    console.log(`    Error: ${e.message}`);
  }
}

/**
 * beforeEach 钩子
 */
let currentBeforeEach = null;
function beforeEach(fn) {
  currentBeforeEach = fn;
}

/**
 * afterEach 钩子
 */
let currentAfterEach = null;
function afterEach(fn) {
  currentAfterEach = fn;
}

/**
 * 将 Windows 路径转换为 file:// URL
 */
function pathToFileURL(filepath) {
  return 'file:///' + filepath.replace(/\\/g, '/');
}

/**
 * 运行测试文件
 */
async function runTestFile(filePath) {
  console.log(`\n--- Running ${filePath} ---`);

  try {
    const fileUrl = pathToFileURL(path.resolve(filePath));
    const mod = await import(fileUrl);
    return mod;
  } catch (e) {
    console.error(`Failed to load ${filePath}: ${e.message}`);
    return null;
  }
}

/**
 * 收集所有测试文件
 */
function collectTestFiles(dir) {
  const files = [];

  try {
    const items = fs.readdirSync(dir, { withFileTypes: true });

    for (const item of items) {
      const fullPath = path.join(dir, item.name);

      if (item.isDirectory() && !item.name.startsWith('.')) {
        files.push(...collectTestFiles(fullPath));
      } else if (item.name.endsWith('.test.js')) {
        files.push(fullPath);
      }
    }
  } catch (e) {
    console.error(`Error reading directory ${dir}: ${e.message}`);
  }

  return files;
}

/**
 * 打印测试结果
 */
function printResults() {
  console.log('\n========================================');
  console.log('Test Results');
  console.log('========================================');
  console.log(`Total:  ${stats.total}`);
  console.log(`Passed: ${stats.passed}`);
  console.log(`Failed: ${stats.failed}`);
  console.log('========================================\n');

  if (stats.failed > 0) {
    console.log('Failed Tests:');
    stats.errors.forEach(({ name, error }) => {
      console.log(`  - ${name}`);
      console.log(`    ${error.message}`);
    });
    console.log('');
  }
}

/**
 * 主函数
 */
async function main() {
  const testDir = path.join(__dirname);
  const testFiles = collectTestFiles(testDir);

  console.log(`Found ${testFiles.length} test files`);

  for (const file of testFiles) {
    await runTestFile(file);
  }

  printResults();

  process.exit(stats.failed > 0 ? 1 : 0);
}

main().catch(e => {
  console.error('Test runner error:', e);
  process.exit(1);
});
