/**
 * 前端静态检查：专治「构建期不报错、点击时才炸」的一类问题。
 *
 * ⚠️ 定位说明（重要）：本项目已接通 eslint（vue-eslint-parser + eslint-plugin-vue@9），
 *    请优先用 `npm run lint`。eslint 的 no-undef 是**作用域感知**的，比本脚本强——
 *    例如 App.vue 里定义在 onMounted 回调内、却在 onUnmounted 里引用的
 *    stopTimers / handleVisibilityChange，eslint 能抓出，本脚本会漏
 *    （本脚本把所有声明拍平成一个集合，不建模作用域）。
 *
 *    本脚本保留的价值在于 eslint 覆盖不到的一类：
 *      **模板 @事件 里引用了但 <script setup> 中不存在的处理器**
 *      （vue3-essential 不含 vue/no-undef-properties，实测 eslint 不报这类）。
 *
 * 三项检查：
 *   1. <script setup> 中被引用但从未声明的标识符（作用域不敏感，弱于 eslint）
 *   2. 调用了 services/http.js 的封装函数，但没从该模块 import
 *   3. 模板 @事件 里引用的处理器，在 <script setup> 中不存在（eslint 不覆盖）
 *
 * 用法：node scripts/check-static.mjs        （npm run check:static）
 */

import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const espree = require('espree')

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SRC = path.join(ROOT, 'src')

// ── 全局白名单：浏览器/JS 内置 + Vue 编译宏 + Vite 注入常量 ──────────────
const GLOBALS = new Set([
  'window', 'document', 'localStorage', 'sessionStorage', 'navigator', 'location',
  'console', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'fetch', 'URL', 'URLSearchParams', 'Blob', 'File', 'FileReader', 'FormData',
  'Image', 'Audio', 'Event', 'CustomEvent', 'MutationObserver', 'IntersectionObserver',
  'requestAnimationFrame', 'cancelAnimationFrame', 'alert', 'confirm', 'prompt',
  'Math', 'JSON', 'Object', 'Array', 'String', 'Number', 'Boolean', 'Date', 'RegExp',
  'Error', 'TypeError', 'RangeError', 'Promise', 'Map', 'Set', 'WeakMap', 'WeakSet',
  'Symbol', 'Proxy', 'Reflect', 'Intl', 'BigInt', 'ArrayBuffer', 'Uint8Array',
  'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'encodeURIComponent',
  'decodeURIComponent', 'encodeURI', 'decodeURI', 'structuredClone', 'queueMicrotask',
  'defineProps', 'defineEmits', 'defineExpose', 'defineOptions', 'defineSlots',
  'withDefaults', 'process', 'globalThis', 'performance', 'crypto', 'atob', 'btoa',
  'getComputedStyle', 'ResizeObserver', 'AbortController', 'TextEncoder', 'TextDecoder',
  'undefined', 'NaN', 'Infinity', 'arguments',
  '__APP_VERSION__'   // vite.config.js 里 define 注入
])

// services/http.js 的导出
const HTTP_FNS = ['get', 'post', 'put', 'del', 'getBlob', 'fetchWithAuth']

// ── 工具 ────────────────────────────────────────────────────────────────
function walkAst(node, visit, ancestors = []) {
  if (!node || typeof node !== 'object') return
  if (Array.isArray(node)) {
    node.forEach(n => walkAst(n, visit, ancestors))
    return
  }
  const isNode = typeof node.type === 'string'
  if (isNode) visit(node, ancestors)
  // 传递祖先链，便于判断 export { X } from '...' 这类"转发导出"
  const next = isNode ? [...ancestors, node] : ancestors
  for (const k of Object.keys(node)) {
    if (k === 'parent') continue
    const v = node[k]
    if (v && typeof v === 'object') walkAst(v, visit, next)
  }
}

function collectScriptFiles(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) collectScriptFiles(p, out)
    else if (/\.(vue|js)$/.test(e.name)) out.push(p)
  }
  return out
}

function parseOrNull(code, offset) {
  try {
    const ast = espree.parse(code, {
      ecmaVersion: 'latest', sourceType: 'module', loc: true
    })
    return { ast, offset }
  } catch (e) {
    return { error: e.message, offset }
  }
}

/** 收集"声明位置"上的标识符名 */
function collectDeclared(ast) {
  const declared = new Set()
  const addPattern = (p) => {
    if (!p) return
    if (p.type === 'Identifier') declared.add(p.name)
    else if (p.type === 'ObjectPattern') {
      p.properties.forEach(pr => addPattern(pr.value || pr.argument || pr))
    } else if (p.type === 'ArrayPattern') p.elements.forEach(addPattern)
    else if (p.type === 'AssignmentPattern') addPattern(p.left)
    else if (p.type === 'RestElement') addPattern(p.argument)
  }
  walkAst(ast, (node) => {
    switch (node.type) {
      case 'VariableDeclarator': addPattern(node.id); break
      case 'FunctionDeclaration':
      case 'FunctionExpression':
      case 'ArrowFunctionExpression':
        if (node.id) declared.add(node.id.name)
        node.params.forEach(addPattern)
        break
      case 'CatchClause': addPattern(node.param); break
      case 'ImportDefaultSpecifier':
      case 'ImportNamespaceSpecifier':
      case 'ImportSpecifier':
        declared.add(node.local.name)
        break
      case 'ClassDeclaration':
      case 'ClassExpression':
        if (node.id) declared.add(node.id.name)
        break
      default: break
    }
  })
  return declared
}

/** 收集所有被引用的标识符（排除属性名、对象字面量 key、转发导出） */
function collectReferenced(ast) {
  const refs = []
  walkAst(ast, (node, ancestors) => {
    if (node.type !== 'Identifier') return
    const parent = ancestors[ancestors.length - 1]
    const grandparent = ancestors[ancestors.length - 2]
    if (parent) {
      // obj.foo —— foo 是属性名，不是引用
      if (parent.type === 'MemberExpression' && parent.property === node && !parent.computed) return
      // { foo: 1 } —— key 不是引用（简写 { foo } 的 value 才是）
      if (parent.type === 'Property' && parent.key === node && !parent.computed) return
      if ((parent.type === 'LabeledStatement' || parent.type === 'BreakStatement'
        || parent.type === 'ContinueStatement') && parent.label === node) return
      // import { X } —— X 是声明，不是引用
      if (parent.type === 'ImportSpecifier' || parent.type === 'ImportDefaultSpecifier'
        || parent.type === 'ImportNamespaceSpecifier') return
      // export { X } from './y' —— 转发导出，X 指向别的模块的导出，不是本地引用
      if (parent.type === 'ExportSpecifier') {
        // `export { X as Y }` 里的 Y 只是"导出成什么名字"，永远不是引用
        if (parent.exported === node) return
        // 带 from 的转发导出，X 也指向别的模块
        if (grandparent && grandparent.type === 'ExportNamedDeclaration' && grandparent.source) return
      }
    }
    refs.push(node)
  })
  return refs
}

// ── 检查 1：未声明标识符 ────────────────────────────────────────────────
function checkUndefined(files, findings) {
  for (const full of files) {
    const text = fs.readFileSync(full, 'utf8')
    const rel = path.relative(SRC, full).replace(/\\/g, '/')

    let code, lineOffset
    const m = text.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)
    if (m) {
      code = m[1]
      lineOffset = text.slice(0, m.index + m[0].indexOf(m[1])).split('\n').length - 1
    } else if (full.endsWith('.js')) {
      code = text
      lineOffset = 0
    } else {
      continue
    }

    const parsed = parseOrNull(code)
    if (parsed.error) {
      findings.push({
        rule: 'parse',
        file: rel,
        line: parsed.offset + 1,
        message: `解析失败（可能是脚本里有语法错误）：${parsed.error}`
      })
      continue
    }

    const declared = collectDeclared(parsed.ast)
    const seen = new Set()
    for (const r of collectReferenced(parsed.ast)) {
      if (declared.has(r.name) || GLOBALS.has(r.name) || seen.has(r.name)) continue
      seen.add(r.name)
      findings.push({
        rule: 'undefined',
        file: rel,
        line: lineOffset + r.loc.start.line,
        message: `未声明的标识符：${r.name} —— 运行时点击到这条路径会抛 ReferenceError`
      })
    }
  }
}

// ── 检查 2：http 封装函数调用了但未导入 ─────────────────────────────────
function checkHttpImports(files, findings) {
  for (const full of files) {
    const text = fs.readFileSync(full, 'utf8')
    const rel = path.relative(SRC, full).replace(/\\/g, '/')

    const imported = new Set()
    let hasHttpImport = false
    for (const m of text.matchAll(
      /import\s*\{([^}]*)\}\s*from\s*['"][^'"]*services\/http\.js['"]/g)) {
      hasHttpImport = true
      for (const n of m[1].split(',')) {
        const name = n.trim().split(' as ')[0].trim()
        if (name) imported.add(name)
      }
    }
    if (!hasHttpImport) continue

    const lines = text.split('\n')
    for (const fn of HTTP_FNS) {
      if (imported.has(fn)) continue
      const re = new RegExp(`(?<![.\\w])${fn}\\s*\\(`, 'g')
      for (const m of text.matchAll(re)) {
        const line = lines[text.slice(0, m.index).split('\n').length - 1].trim()
        if (line.startsWith('//') || line.startsWith('*') || line.startsWith('import')) continue
        if (line.startsWith('export function') || line.startsWith('function')) continue
        findings.push({
          rule: 'missing-import',
          file: rel,
          line: text.slice(0, m.index).split('\n').length,
          message: `调用了 ${fn}() 但没有从 services/http.js 导入：${line.slice(0, 70)}`
        })
      }
    }
  }
}

// ── 检查 3：模板事件处理器未定义 ────────────────────────────────────────
function checkTemplateHandlers(files, findings) {
  for (const full of files) {
    if (!full.endsWith('.vue')) continue
    const text = fs.readFileSync(full, 'utf8')
    const rel = path.relative(SRC, full).replace(/\\/g, '/')

    const tplM = text.match(/<template>([\s\S]*)<\/template>/)
    const scrM = text.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)
    if (!tplM || !scrM) continue
    const tpl = tplM[1]
    const script = scrM[1]

    const defined = new Set()
    const push = (n) => { if (n) defined.add(n) }
    for (const m of script.matchAll(/(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) push(m[1])
    for (const m of script.matchAll(/function\s+([A-Za-z_$][\w$]*)/g)) push(m[1])
    for (const m of script.matchAll(/import\s*\{([^}]*)\}/g)) {
      for (const n of m[1].split(',')) {
        push(n.trim().split(' as ').pop().trim())
      }
    }
    for (const m of script.matchAll(/const\s*\{([^}]*)\}\s*=/g)) {
      for (const n of m[1].split(',')) push(n.trim().split(':').pop().trim())
    }
    // v-for 里的循环变量
    const loopVars = new Set()
    for (const m of tpl.matchAll(/v-for\s*=\s*"\(?\s*([A-Za-z_$][\w$]*)/g)) loopVars.add(m[1])
    // 模板插值里出现过的名字也视作已提供（避免误报）
    for (const m of tpl.matchAll(/\{\{\s*([A-Za-z_$][\w$]*)/g)) push(m[1])

    const seen = new Set()
    // 字面量与关键字不是标识符引用（内联表达式如 @click="show = true" 会命中正则）
    const LITERALS = new Set(['true', 'false', 'null', 'undefined', 'if', 'else',
      'in', 'of', 'delete', 'new', 'typeof', 'void', 'instanceof', 'return'])
    for (const m of tpl.matchAll(/@[\w:.]+(?:\.\w+)*\s*=\s*"([^"]+)"/g)) {
      const expr = m[1]
      for (const nm of (expr + ' ').matchAll(
        /(?<![.\w$])([A-Za-z_$][\w$]*)\s*(?:\(|$|\s*[?&|])/g)) {
        const name = nm[1]
        if (GLOBALS.has(name) || defined.has(name) || loopVars.has(name)) continue
        if (LITERALS.has(name)) continue
        if (seen.has(name)) continue
        seen.add(name)
        findings.push({
          rule: 'template-handler',
          file: rel,
          line: text.slice(0, tplM.index + m.index).split('\n').length,
          message: `模板里引用了未定义的 ${name}()：${expr.slice(0, 60)}`
        })
      }
    }
  }
}

// ── 主流程 ──────────────────────────────────────────────────────────────
const findings = []
const files = collectScriptFiles(SRC)

checkUndefined(files, findings)
checkHttpImports(files, findings)
checkTemplateHandlers(files, findings)

const RULE_NAME = {
  undefined: '未声明标识符',
  'missing-import': '缺少导入',
  'template-handler': '模板处理器未定义',
  parse: '解析失败'
}

const byRule = new Map()
for (const f of findings) {
  if (!byRule.has(f.rule)) byRule.set(f.rule, [])
  byRule.get(f.rule).push(f)
}

console.log(`检查了 ${files.length} 个文件\n`)

if (!findings.length) {
  console.log('未发现问题。')
  process.exit(0)
}

for (const [rule, list] of byRule) {
  console.log(`【${RULE_NAME[rule] || rule}】${list.length} 处`)
  for (const f of list) {
    console.log(`  ${f.file}:${f.line}`)
    console.log(`    ${f.message}`)
  }
  console.log('')
}

console.log(`共 ${findings.length} 处问题 —— 这些都不会在构建期报错，只会在用户点击时炸。`)
process.exit(1)
