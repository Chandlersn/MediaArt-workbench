/**
 * 跨文件死代码扫描：找出「导出了但全项目没人引用」的名字，以及「从未被导入」的模块。
 *
 * eslint 是单文件分析的，看不到这类；而这类正是"删了没影响"的死代码主体。
 *
 * 保守策略：只报告**在整个 src/ 里（含定义文件自身）除声明处外一次都没出现**的名字，
 * 这类才判定为可安全删除。仅在文件内使用、但加了 export 的，另列为"多余导出"（仅建议）。
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SRC = path.join(ROOT, 'src')

function collectFiles(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) collectFiles(p, out)
    else if (/\.(js|vue)$/.test(e.name)) out.push(p)
  }
  return out
}

const files = collectFiles(SRC)
const contents = new Map()
for (const f of files) contents.set(f, fs.readFileSync(f, 'utf8'))

const rel = (f) => path.relative(SRC, f).replace(/\\/g, '/')

// ── 1. 收集每个文件的导出名 ─────────────────────────────────────────────
const exportsByFile = new Map() // file -> [{name, line}]
for (const f of files) {
  const text = contents.get(f)
  const list = []
  const lines = text.split('\n')

  const push = (name, index) => {
    if (!name || name === 'default') return
    list.push({ name, line: text.slice(0, index).split('\n').length })
  }

  // export const/function/class/let/var NAME
  for (const m of text.matchAll(
    /export\s+(?:async\s+)?(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)/g)) {
    push(m[1], m.index)
  }
  // export { A, B as C }
  for (const m of text.matchAll(/export\s*\{([^}]*)\}/g)) {
    for (const piece of m[1].split(',')) {
      const name = piece.trim().split(/\s+as\s+/)[0].trim()
      push(name, m.index)
    }
  }
  // export default
  if (/export\s+default/.test(text)) {
    list.push({ name: '__default__', line: lines.findIndex(l => /export\s+default/.test(l)) + 1 })
  }
  exportsByFile.set(f, list)
}

// ── 2. 判断每个导出名是否在别处被引用 ───────────────────────────────────
const findings = { deadExports: [], extraExports: [], unusedFiles: [] }

for (const [f, list] of exportsByFile) {
  const text = contents.get(f)

  for (const { name, line } of list) {
    if (name === '__default__') continue

    // 在其它文件里出现过该名字（import 或直接使用）
    let usedElsewhere = false
    for (const [g, gtext] of contents) {
      if (g === f) continue
      if (new RegExp(`(?<![\\w$])${name}(?![\\w$])`).test(gtext)) { usedElsewhere = true; break }
    }

    // 在定义文件自身里，除声明处外是否还有出现
    const occurrences = [...text.matchAll(new RegExp(`(?<![\\w$])${name}(?![\\w$])`, 'g'))]
    const usedInFile = occurrences.length > 1

    if (!usedElsewhere && !usedInFile) {
      findings.deadExports.push({ file: rel(f), line, name })
    } else if (!usedElsewhere && usedInFile) {
      findings.extraExports.push({ file: rel(f), line, name })
    }
  }
}

// ── 3. 从未被导入的模块（.vue 走 import() 动态引入也要算）──────────────
for (const f of files) {
  const r = rel(f)
  if (r === 'main.js') continue  // 入口

  const stem = path.basename(f, path.extname(f))
  const dirName = path.basename(path.dirname(f))

  // 目录导入：`from '../stores'` / `from './router'` 会解析到该目录下的 index.js，
  // 此时引用的是**目录名**而不是文件名，必须把目录名也作为匹配目标，否则误报
  const candidates = stem === 'index' ? [dirName] : [stem, dirName]

  let referenced = false
  for (const [g, gtext] of contents) {
    if (g === f) continue
    for (const cand of candidates) {
      if (gtext.includes(`/${cand}.vue`) || gtext.includes(`/${cand}.js`)
        || gtext.includes(`./${cand}'`) || gtext.includes(`./${cand}"`)
        || gtext.includes(`'${cand}'`) || gtext.includes(`/${cand}'`)
        || gtext.includes(`/${cand}"`)) {
        referenced = true
        break
      }
    }
    if (referenced) break
  }
  if (!referenced) findings.unusedFiles.push({ file: r })
}

// ── 输出 ────────────────────────────────────────────────────────────────
console.log('=== 1. 完全无引用的导出（可安全删除）===')
if (!findings.deadExports.length) console.log('  (无)')
for (const d of findings.deadExports) console.log(`  ${d.file}:${d.line}  ${d.name}()`)

console.log('')
console.log('=== 2. 只在定义文件内使用（export 多余，可去掉 export 关键字）===')
if (!findings.extraExports.length) console.log('  (无)')
for (const d of findings.extraExports) console.log(`  ${d.file}:${d.line}  ${d.name}`)

console.log('')
console.log('=== 3. 从未被引用的模块文件 ===')
if (!findings.unusedFiles.length) console.log('  (无)')
for (const d of findings.unusedFiles) console.log(`  ${d.file}`)

console.log('')
console.log(`合计: 无引用导出 ${findings.deadExports.length} | 多余导出 ${findings.extraExports.length} | 未引用文件 ${findings.unusedFiles.length}`)
console.log('')

// 第 1、3 类是可安全删除的死代码 → 发现问题即失败；
// 第 2 类只是 export 关键字多余（名字在文件内仍有使用），不阻断。
const actionable = findings.deadExports.length + findings.unusedFiles.length
if (actionable) {
  console.log(`发现 ${actionable} 处可删除的死代码。`)
  process.exit(1)
}
console.log('无可删除的死代码。')
process.exit(0)
