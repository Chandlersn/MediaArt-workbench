/** 顺序执行测试，支持异步用例、嵌套钩子，并将加载失败计入结果。 */
import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { fileURLToPath, pathToFileURL } from 'node:url'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const root = { name: '', parent: null, before: [], after: [], entries: [] }
let currentSuite = root
const stats = { total: 0, passed: 0, failed: 0 }

Object.assign(globalThis, {
  assert,
  assertEqual: assert.strictEqual,
  assertDeepEqual: assert.deepStrictEqual,
  assertThrows: assert.throws,
  describe(name, fn) {
    const suite = { name, parent: currentSuite, before: [], after: [], entries: [] }
    currentSuite.entries.push(suite)
    currentSuite = suite
    try { fn() } finally { currentSuite = suite.parent }
  },
  it(name, fn) { currentSuite.entries.push({ name, fn }) },
  beforeEach(fn) { currentSuite.before.push(fn) },
  afterEach(fn) { currentSuite.after.push(fn) }
})

function collect(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory() && !entry.name.startsWith('.')) return collect(full)
    return entry.isFile() && entry.name.endsWith('.test.js') ? [full] : []
  }).sort()
}

async function invoke(fn) {
  let timer
  try {
    await Promise.race([
      Promise.resolve().then(fn),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('测试执行超过 15 秒')), 15000) })
    ])
  } finally { clearTimeout(timer) }
}

async function runSuite(suite, parents = []) {
  const chain = [...parents, suite]
  for (const item of suite.entries) {
    if (!item.fn) { await runSuite(item, chain); continue }
    stats.total++
    const name = [...chain.map(s => s.name).filter(Boolean), item.name].join(' > ')
    let failure
    try {
      for (const s of chain) for (const hook of s.before) await invoke(hook)
      await invoke(item.fn)
    } catch (error) { failure = error }
    finally {
      for (const s of [...chain].reverse()) {
        for (const hook of s.after) {
          try { await invoke(hook) } catch (error) { failure ||= error }
        }
      }
    }
    if (failure) {
      stats.failed++
      console.error(`✗ ${name}\n  ${failure.stack || failure}`)
    } else {
      stats.passed++
      console.log(`✓ ${name}`)
    }
  }
}

const args = process.argv.slice(2).filter(arg => !arg.startsWith('--'))
const files = args.length ? args.map(file => path.resolve(file)) : collect(testDir)
for (const file of files) {
  const suite = { name: path.relative(testDir, file), parent: root, before: [], after: [], entries: [] }
  root.entries.push(suite)
  currentSuite = suite
  try { await import(pathToFileURL(file).href) }
  catch (error) {
    stats.total++
    stats.failed++
    console.error(`无法加载 ${file}: ${error.stack || error}`)
  } finally { currentSuite = root }
}
await runSuite(root)
console.log(`Total: ${stats.total}  Passed: ${stats.passed}  Failed: ${stats.failed}`)
if (!files.length) { console.error('没有找到测试文件'); process.exitCode = 1 }
else process.exitCode = stats.failed ? 1 : 0
