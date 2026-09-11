/**
 * 参数契约扫描：找出「前端发了、后端没读」的请求参数。
 *
 * 为什么需要它：targetPath 就是这么被发现的——前端三个页面上传时都带了它，
 * 后端一个字没读，导致文件全部落错目录。这类问题不报错、不抛异常，只是
 * 功能静默失效，靠点页面很难发现。
 *
 * 做法：
 *   1. 扫 src/ 里对 http 封装（get/post/put/del/fetchWithAuth/getBlob）的调用，
 *      提取请求路径 + 发送的参数名（query 串 key、JSON body 的对象字面量 key）
 *   2. 扫 server.py 的路由守卫，按相邻边界切分分发块，建立 路径 → 处理方法 的映射
 *      （分发块可能按 Content-Type 走不同处理函数，所以一个路径可能对应多个方法）
 *   3. 收集分发块与各处理函数里真正读取过的参数名
 *      （query.get('x') / data.get('x') / data['x'] / multipart 的 name="x"）
 *   4. 两者做差集，报出前端发了但后端从未读取的参数
 *
 * 输出是**线索不是结论**：有些参数（如 /api/count-files 的 recursive）前端传了、
 * 后端忽略也无害，需要人工判断。因此本脚本始终以退出码 0 结束，不阻断流程。
 *
 * 用法：node scripts/check-params.mjs      （npm run check:params）
 *      加 --strict 时发现线索即退出码 1，适合接入 CI。
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const espree = require('espree')

// 注意：必须用 fileURLToPath，不能直接取 new URL(import.meta.url).pathname
// ——Windows 下 pathname 是 URL 编码的，中文路径会变成 %E4%B8%AA... 而解析不到。
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SRC = path.join(ROOT, 'src')
const SERVER = path.join(ROOT, 'server.py')
const HTTP_FNS = ['get', 'post', 'put', 'del', 'fetchWithAuth', 'getBlob']

// ---------- 1. 收集前端调用 ----------
const frontendCalls = new Map() // path -> Set(param)

function addCall(file, p, params) {
  if (!p || !p.startsWith('/api/')) return
  const clean = p.split('?')[0]
  if (!frontendCalls.has(clean)) frontendCalls.set(clean, { params: new Set(), files: new Set() })
  const e = frontendCalls.get(clean)
  for (const x of params) e.params.add(x)
  e.files.add(file)
}

// 从模板字符串/字符串里抠出 query 参数名
function queryKeysFromString(s) {
  const out = []
  for (const m of s.matchAll(/[?&]([A-Za-z_][\w]*)=/g)) out.push(m[1])
  return out
}

function objectLiteralKeys(node) {
  const out = []
  if (!node || node.type !== 'ObjectExpression') return out
  for (const prop of node.properties) {
    if (prop.type === 'Property' && prop.key) {
      if (prop.key.type === 'Identifier') out.push(prop.key.name)
      else if (prop.key.type === 'Literal') out.push(String(prop.key.value))
    }
  }
  return out
}

// 尝试把表达式还原成静态字符串（模板字符串的静态部分也算）
function staticString(node) {
  if (!node) return null
  if (node.type === 'Literal' && typeof node.value === 'string') return node.value
  if (node.type === 'TemplateLiteral') {
    let s = ''
    for (let i = 0; i < node.quasis.length; i++) {
      s += node.quasis[i].value.cooked || ''
      if (i < node.expressions.length) {
        const e = node.expressions[i]
        // 三元表达式两侧都是字符串时取其中出现的 query key
        if (e.type === 'ConditionalExpression') {
          s += staticString(e.consequent) || ''
          continue
        }
        s += '${}'
      }
    }
    return s
  }
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    return (staticString(node.left) || '') + (staticString(node.right) || '')
  }
  if (node.type === 'ConditionalExpression') {
    return staticString(node.consequent) || staticString(node.alternate)
  }
  return null
}

function walk(node, visit) {
  if (!node || typeof node !== 'object') return
  if (Array.isArray(node)) { node.forEach(n => walk(n, visit)); return }
  if (typeof node.type === 'string') visit(node)
  for (const k of Object.keys(node)) {
    if (k === 'parent') continue
    const v = node[k]
    if (v && typeof v === 'object') walk(v, visit)
  }
}

function scanFrontendFile(file) {
  const full = path.join(SRC, file)
  const text = fs.readFileSync(full, 'utf8')
  const blocks = []
  const m = text.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)
  if (m) blocks.push({ code: m[1], offset: text.slice(0, m.index).split('\n').length })
  else {
    // 纯 js 文件
    if (file.endsWith('.js')) blocks.push({ code: text, offset: 0 })
  }

  for (const b of blocks) {
    let ast
    try {
      ast = espree.parse(b.code, { ecmaVersion: 'latest', sourceType: 'module', loc: true })
    } catch { continue }

    walk(ast, (node) => {
      if (node.type !== 'CallExpression') return
      const callee = node.callee
      let name = null
      if (callee.type === 'Identifier') name = callee.name
      else if (callee.type === 'MemberExpression' && !callee.computed
        && callee.property.type === 'Identifier') name = callee.property.name
      if (!HTTP_FNS.includes(name)) return

      const params = new Set()
      // 第 1 参：路径
      const pathStr = staticString(node.arguments[0])
      if (pathStr) for (const k of queryKeysFromString(pathStr)) params.add(k)

      // 第 2 参：可能含 body / query / headers
      const second = node.arguments[1]
      if (second && second.type === 'ObjectExpression') {
        for (const prop of second.properties) {
          if (prop.type !== 'Property' || !prop.key) continue
          const key = prop.key.name || prop.key.value
          if (key === 'body') {
            const val = prop.value
            if (val.type === 'ObjectExpression') {
              for (const k of objectLiteralKeys(val)) params.add(k)
            } else if (val.type === 'CallExpression'
              && val.callee.type === 'MemberExpression'
              && val.callee.property.name === 'stringify') {
              for (const k of objectLiteralKeys(val.arguments[0])) params.add(k)
            }
          }
        }
      }
      // 第 2 参也可能直接就是 body 对象（post(path, {...})）
      if (name === 'post' || name === 'put') {
        if (second && second.type === 'ObjectExpression'
          && !second.properties.some(p => p.type === 'Property'
            && ['body', 'method', 'headers'].includes(p.key?.name))) {
          for (const k of objectLiteralKeys(second)) params.add(k)
        }
      }

      if (pathStr) addCall(file, pathStr, [...params])
      else {
        // 路径是动态拼接的：退一步，按前缀归到最接近的静态前缀
        const dyn = node.arguments[0]
        if (dyn) {
          const pre = staticString(dyn)
          if (pre && pre.startsWith('/api/')) addCall(file, pre.split('?')[0], [...params])
        }
      }
    })
  }
}

function walkDir(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) walkDir(p)
    else if (/\.(vue|js)$/.test(e.name)) scanFrontendFile(path.relative(SRC, p).replace(/\\/g, '/'))
  }
}

// ---------- 2. 收集后端路由 → 方法映射 ----------
const serverText = fs.readFileSync(SERVER, 'utf8')

const routeToMethod = new Map()   // path -> Set(method)
const routeToSnippet = new Map()  // path -> 分发块源码

// 先定位所有路由守卫的位置，再按相邻边界切分分发块。
// 注意：不能用固定 N 行窗口——前面的分发块会把后面路由的 if 行"吃掉"，
// 导致 matchAll 非重叠跳过它们（这是 scan_params 第一版的真实 bug）。
const routeMatches = []
for (const m of serverText.matchAll(
  /if\s+(?:parsed\.path|self\.path)\s*(?:==\s*'(\/api\/[^']+)'|\.startswith\('(\/api\/[^']+)'\))\s*:/g)) {
  routeMatches.push({ apiPath: m[1] || m[2], start: m.index, end: m.index + m[0].length })
}
for (let i = 0; i < routeMatches.length; i++) {
  const cur = routeMatches[i]
  const next = routeMatches[i + 1]
  const snippet = serverText.slice(cur.end, next ? next.start : cur.end + 1200)
  routeToSnippet.set(cur.apiPath, (routeToSnippet.get(cur.apiPath) || '') + snippet)
  // 分发块可能按 Content-Type 走不同处理函数（如 import-players），必须全收
  const calls = [...snippet.matchAll(/self\.([a-z_][\w]*)\(/g)].map(x => x[1])
  if (calls.length) {
    if (!routeToMethod.has(cur.apiPath)) routeToMethod.set(cur.apiPath, new Set())
    for (const c of calls) routeToMethod.get(cur.apiPath).add(c)
  }
}

// ---------- 3. 收集每个方法读取过的参数名 ----------
const methodParams = new Map()
const methodRe = /^    def ([a-z_][\w]*)\(self[^)]*\):([\s\S]*?)(?=^    def |^class |\Z)/gm
for (const m of serverText.matchAll(methodRe)) {
  const name = m[1]
  const body = m[2]
  const params = new Set()
  for (const p of body.matchAll(/\.get\(\s*'([^']+)'/g)) params.add(p[1])
  for (const p of body.matchAll(/\[\s*'([A-Za-z_][\w]*)'\s*\]/g)) params.add(p[1])
  for (const p of body.matchAll(/b?'name="([^"]+)"'/g)) params.add(p[1])  // multipart 字段
  methodParams.set(name, { params, len: body.length })
}

// ---------- 4. 比对 ----------
console.log('=== 前端发了但后端对应处理函数从未读取的参数 ===')
console.log('')

const IGNORE = new Set(['success', 'message', 'error', 'data', 'items', 'file',
  'Content-Type', 'method', 'headers', 'body', 'token', 'id', 'name'])

let findings = 0
walkDir(SRC)

const rows = [...frontendCalls.entries()].sort((a, b) => a[0].localeCompare(b[0]))
for (const [apiPath, info] of rows) {
  // 找后端方法：精确匹配，否则找 startswith 前缀
  let methods = routeToMethod.get(apiPath) ? [...routeToMethod.get(apiPath)] : null
  let matchedBy = 'exact'
  if (!methods) {
    for (const [p, set] of routeToMethod) {
      if (apiPath.startsWith(p)) { methods = [...set]; matchedBy = `prefix:${p}`; break }
    }
  }
  if (!methods || !methods.length) continue

  const readInDispatch = new Set()
  const snippet = routeToSnippet.get(apiPath) || ''
  for (const p of snippet.matchAll(/\.get\(\s*'([^']+)'/g)) readInDispatch.add(p[1])

  const readInMethod = new Set()
  for (const mn of methods) {
    const rec = methodParams.get(mn)
    if (rec) for (const p of rec.params) readInMethod.add(p)
  }

  const missing = [...info.params].filter(p =>
    !IGNORE.has(p) && !readInMethod.has(p) && !readInDispatch.has(p))
  if (!missing.length) continue

  findings++
  console.log(`  ${apiPath}   →  server.${methods.join(' / ')}()  [${matchedBy}]`)
  console.log(`     前端发送但后端未读: ${missing.join(', ')}`)
  console.log(`     来源: ${[...info.files].join(', ')}`)
  console.log('')
}

console.log(`共 ${findings} 处线索 —— 需要人工确认：有些参数后端忽略也无害`)
console.log('（如 /api/count-files 的 recursive，后端本来就是递归统计）')
console.log('')
console.log('')
console.log('=== 覆盖面自检（避免"0 命中"其实是因为没匹配上）===')
let matched = 0
const unmatched = []
for (const [apiPath] of rows) {
  if (routeToMethod.has(apiPath)) { matched++; continue }
  let found = false
  for (const [p] of routeToMethod) {
    if (apiPath.startsWith(p)) { found = true; break }
  }
  if (found) matched++
  else unmatched.push(apiPath)
}
console.log(`  前端出现的 /api 路径: ${rows.length} 个`)
console.log(`  在后端找到对应处理函数: ${matched} 个`)
if (unmatched.length) {
  console.log(`  未匹配（可能是 GET 只读、或路径动态拼接）: ${unmatched.length} 个`)
  for (const u of unmatched.slice(0, 12)) console.log(`     - ${u}`)
}
console.log('')
console.log('  后端路由表条目数:', routeToMethod.size)
console.log('  后端处理函数参数表条目数:', methodParams.size)
console.log('')

// 默认不阻断流程（线索需人工判断）；--strict 供 CI 使用
process.exit(process.argv.includes('--strict') && findings ? 1 : 0)
