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
 *   2. 扫 server 下各模块的 routes.py，按缩进切分分发块，建立 路径 → 处理方法 的映射
 *      （分发块可能按 Content-Type 走不同处理函数，所以一个路径可能对应多个方法）
 *   3. 收集分发块与各处理函数里真正读取过的参数名
 *      （query.get('x') / data.get('x') / data['x'] / multipart 的 name="x"）
 *   4. 两者做差集，报出前端发了但后端从未读取的参数
 *
 * 输出是**线索不是结论**：有些参数（如 /api/count-files 的 recursive）前端传了、
 * 后端忽略也无害，需要人工判断。普通线索默认不阻断；解析错误或覆盖自检失败必须报错。
 *
 * 用法：node scripts/check-params.mjs      （npm run check:params）
 *      加 --strict 时发现线索即退出码 1，适合接入 CI。
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'
import nodeAssert from 'node:assert/strict'

const require = createRequire(import.meta.url)
const espree = require('espree')

// 注意：必须用 fileURLToPath，不能直接取 new URL(import.meta.url).pathname
// ——Windows 下 pathname 是 URL 编码的，中文路径会变成 %E4%B8%AA... 而解析不到。
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SRC = path.join(ROOT, 'src')
const SERVER = path.join(ROOT, 'server')
const HTTP_FNS = ['get', 'post', 'put', 'del', 'fetchWithAuth', 'getBlob']

// ---------- 1. 收集前端调用 ----------
const frontendCalls = new Map() // path -> Set(param)
const frontendParseFailures = []

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
function staticString(node, bindings = new Map(), seen = new Set()) {
  if (!node) return null
  if (node.type === 'Identifier' && bindings.get(node.name) && !seen.has(node.name)) {
    return staticString(bindings.get(node.name), bindings, new Set([...seen, node.name]))
  }
  if (node.type === 'Literal' && typeof node.value === 'string') return node.value
  if (node.type === 'TemplateLiteral') {
    let s = ''
    for (let i = 0; i < node.quasis.length; i++) {
      s += node.quasis[i].value.cooked || ''
      if (i < node.expressions.length) {
        const e = node.expressions[i]
        s += staticString(e, bindings, seen) ?? '${}'
      }
    }
    return s
  }
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    return (staticString(node.left, bindings, seen) || '') + (staticString(node.right, bindings, seen) || '')
  }
  if (node.type === 'ConditionalExpression') {
    return staticString(node.consequent, bindings, seen) || staticString(node.alternate, bindings, seen)
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
    } catch (error) {
      frontendParseFailures.push(`${file}: ${error.message}`)
      continue
    }

    const bindings = new Map()
    const declarations = new Set()
    const formFields = new Map()
    walk(ast, node => {
      if (node.type === 'VariableDeclarator' && node.id.type === 'Identifier') {
        const name = node.id.name
        bindings.set(name, declarations.has(name) ? null : node.init)
        declarations.add(name)
        if (node.init?.type === 'NewExpression' && node.init.callee.name === 'FormData') {
          formFields.set(name, new Set())
        }
      }
    })
    walk(ast, node => {
      if (node.type !== 'CallExpression' || node.callee.type !== 'MemberExpression') return
      const fields = formFields.get(node.callee.object.name)
      if (fields && node.callee.property.name === 'append' && node.arguments[0]?.type === 'Literal') {
        fields.add(String(node.arguments[0].value))
      }
    })

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
      const pathStr = staticString(node.arguments[0], bindings)
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
            } else if (val.type === 'Identifier' && formFields.has(val.name)) {
              for (const k of formFields.get(val.name)) params.add(k)
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
          const pre = staticString(dyn, bindings)
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

// ---------- 2. 按模块收集 Python 定义、路由和辅助函数调用 ----------
// 这是针对当前路由写法的保守静态扫描，不执行或导入 Python 业务代码。
// 定义按缩进取边界，支持返回类型注解、多行签名和嵌套 helper。
function indentation(line) {
  return line.match(/^[ \t]*/)[0].replace(/\t/g, '    ').length
}

function blockEnd(lines, start, headerEnd = start) {
  const indent = indentation(lines[start])
  for (let i = headerEnd + 1; i < lines.length; i++) {
    if (!lines[i].trim() || lines[i].trimStart().startsWith('#')) continue
    if (indentation(lines[i]) <= indent) return i
  }
  return lines.length
}

function pythonModule(moduleName, source) {
  const lines = source.split(/\r?\n/)
  const definitions = []
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(/^\s*(class|(?:async\s+)?def)\s+(\w+)\s*[( :]/)
    if (!match) continue
    let headerEnd = i
    while (headerEnd < lines.length && !/:\s*(?:#.*)?$/.test(lines[headerEnd])) headerEnd++
    const parents = definitions.filter(d => d.start < i && d.end > i && d.indent < indentation(lines[i]))
    const scope = parents.map(d => d.name).join('.')
    const classScope = parents.filter(d => d.kind === 'class').map(d => d.name).join('.')
    definitions.push({
      name: match[2], kind: match[1] === 'class' ? 'class' : 'def',
      qualname: scope ? `${scope}.${match[2]}` : match[2], classScope,
      start: i, headerEnd, end: blockEnd(lines, i, headerEnd), indent: indentation(lines[i]),
    })
  }
  const methods = new Map()
  for (const definition of definitions.filter(d => d.kind === 'def')) {
    definition.body = lines.slice(definition.headerEnd + 1, definition.end).join('\n')
    methods.set(definition.qualname, definition)
  }
  return { name: moduleName, lines, methods }
}

function readParams(body) {
  const params = new Set()
  for (const match of body.matchAll(/\.get\(\s*['"]([^'"]+)['"]/g)) params.add(match[1])
  for (const match of body.matchAll(/\[\s*['"]([A-Za-z_]\w*)['"]\s*\]/g)) params.add(match[1])
  for (const match of body.matchAll(/\b_qp\(\s*[^,\n]+,\s*['"]([^'"]+)['"]/g)) params.add(match[1])
  for (const match of body.matchAll(/name=["']([A-Za-z_]\w*)["']/g)) params.add(match[1])
  // for kind, field in (('project', 'projectName'), ...): fields.get(field)
  // 仅关联确实被 .get(variable) 读取的循环变量及其静态元组列。
  for (const loop of body.matchAll(/\bfor\s+([A-Za-z_][\w, \t]*)\s+in\s+\(([\s\S]*?)\)\s*:/g)) {
    const variables = loop[1].split(',').map(value => value.trim())
    const tuples = [...loop[2].matchAll(/\(([^()]*)\)/g)].map(match => match[1])
    const rows = tuples.length ? tuples : [loop[2]]
    variables.forEach((variable, index) => {
      if (!new RegExp(`\\.get\\(\\s*${variable}\\s*[,)]`).test(body)) return
      for (const row of rows) {
        const values = [...row.matchAll(/['"]([A-Za-z_]\w*)['"]/g)].map(match => match[1])
        if (variables.length === 1) for (const value of values) params.add(value)
        else if (values[index]) params.add(values[index])
      }
    })
  }
  return params
}

function resolveCall(module, owner, name, onSelf) {
  if (onSelf) return module.methods.get(`${owner.classScope}.${name}`)
  const scope = owner.qualname.split('.')
  while (scope.length) {
    const found = module.methods.get(`${scope.join('.')}.${name}`)
    if (found) return found
    scope.pop()
  }
  return module.methods.get(name)
}

function calledMethods(module, owner, body) {
  const calls = []
  for (const match of body.matchAll(/(?<![\w.])(?:(self)\.)?([A-Za-z_]\w*)\s*\(/g)) {
    const method = resolveCall(module, owner, match[2], Boolean(match[1]))
    if (method) calls.push({ method, offset: match.index + match[0].length })
  }
  return calls
}

function collectReads(module, owner, body = owner.body, seen = new Set()) {
  const params = readParams(body)
  const methodNames = new Set()
  for (const { method, offset } of calledMethods(module, owner, body)) {
    const key = `${module.name}:${method.qualname}`
    methodNames.add(key)
    if (!seen.has(key)) {
      seen.add(key)
      const nested = collectReads(module, method, method.body, seen)
      for (const value of nested.params) params.add(value)
      for (const value of nested.methodNames) methodNames.add(value)
    }
    // _first(data, 'realName', 'real_name') 动态读取 key，调用处的字符串也是字段名。
    // 只对确实动态取键的本模块 helper 应用，避免混入其他模块的同名方法。
    if (/\.get\(\s*[A-Za-z_]\w*\s*[,)]|\[\s*[A-Za-z_]\w*\s*\]/.test(method.body)) {
      const args = body.slice(offset, body.indexOf(')', offset))
      for (const match of args.matchAll(/['"]([A-Za-z_]\w*)['"]/g)) params.add(match[1])
    }
  }
  return { params, methodNames }
}

function collectRoutes(module) {
  const routes = []
  for (const owner of module.methods.values()) {
    if (owner.name !== 'handle_request') continue
    for (let i = owner.headerEnd + 1; i < owner.end; i++) {
      if (!/^\s*(?:if|elif)\b/.test(module.lines[i])) continue
      let headerEnd = i
      while (headerEnd < owner.end && !/:\s*(?:#.*)?$/.test(module.lines[headerEnd])) headerEnd++
      const guard = module.lines.slice(i, headerEnd + 1).join(' ')
      const paths = []
      for (const match of guard.matchAll(/\b(?:norm|path|parsed\.path|self\.path)\s*==\s*['"](\/api\/[^'"]*)['"]/g)) {
        paths.push({ path: match[1], prefix: false })
      }
      for (const match of guard.matchAll(/\b(?:norm|path|parsed\.path|self\.path)\.startswith\(\s*['"](\/api\/[^'"]*)['"]/g)) {
        paths.push({ path: match[1], prefix: true })
      }
      for (const match of guard.matchAll(/\b(?:norm|path|parsed\.path|self\.path)\s+in\s+\(([^)]*)\)/g)) {
        for (const entry of match[1].matchAll(/['"](\/api\/[^'"]*)['"]/g)) paths.push({ path: entry[1], prefix: false })
      }
      if (!paths.length) continue
      const end = Math.min(owner.end, blockEnd(module.lines, i, headerEnd))
      const body = module.lines.slice(headerEnd + 1, end).join('\n')
      const reads = collectReads(module, owner, body)
      for (const entry of paths) routes.push({ ...entry, ...reads, module: module.name })
    }
  }
  return routes
}

function routeFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const full = path.join(directory, entry.name)
    if (entry.isDirectory() && !entry.name.startsWith('.')) return routeFiles(full)
    return entry.isFile() && entry.name === 'routes.py' ? [full] : []
  }).sort()
}

// 固定源码样例防止语法变化造成扫描器零匹配后仍报告通过。
function verifyParser() {
  const source = `
class Router:
    def handle_request(self, request_context: dict) -> dict:
        if norm == '/api/one' and method == 'GET':
            return self.read(request_context)
        elif path in ('/api/two', '/api/three'):
            return self.read(request_context)
        elif path.startswith('/api/item/'):
            return self.read(request_context)
    def read(self,
             request_context: dict) -> dict:
        def first(data, *keys):
            return next(data[k] for k in keys)
        alias = first(data, 'camelName', 'snake_name')
        return self.locate(request_context)
    def locate(self, request_context: dict) -> str:
        for kind, field in (('project', 'projectName'), ('org', 'orgName')):
            value = fields.get(field)
        return _qp(request_context, 'fileName', '')
`
  const first = pythonModule('one/routes.py', source)
  const second = pythonModule('two/routes.py', source.replaceAll('fileName', 'otherName'))
  const a = collectRoutes(first)
  const b = collectRoutes(second)
  nodeAssert.equal(a.length, 4, '必须识别 norm/path、in 元组和 startswith 路由')
  nodeAssert.ok(a[0].params.has('fileName'), '必须递归识别 helper 的 _qp 参数')
  nodeAssert.ok(a[0].params.has('camelName'), '必须识别嵌套 helper 参数')
  nodeAssert.ok(a[0].params.has('snake_name'))
  nodeAssert.ok(a[0].params.has('projectName') && a[0].params.has('orgName'), '必须识别静态元组提供的动态字段名')
  nodeAssert.ok(!a[0].params.has('project') && !a[0].params.has('unknownField'), '不能把未读取的字段或元组列视为参数')
  nodeAssert.ok(!a[0].params.has('otherName') && b[0].params.has('otherName'), '同名方法必须按模块隔离')
  nodeAssert.ok(a.some(route => route.prefix && route.path === '/api/item/'))
}

verifyParser()
const modules = routeFiles(SERVER).map(file => pythonModule(
  path.relative(ROOT, file).replace(/\\/g, '/'), fs.readFileSync(file, 'utf8')))
const backendRoutes = modules.flatMap(collectRoutes)

function matchingRoutes(apiPath) {
  const exact = backendRoutes.filter(route => !route.prefix && route.path === apiPath)
  if (exact.length) return exact
  const prefixes = backendRoutes.filter(route => route.prefix && apiPath.startsWith(route.path))
  const longest = Math.max(0, ...prefixes.map(route => route.path.length))
  return prefixes.filter(route => route.path.length === longest)
}

// ---------- 3. 比对，并检查实际覆盖 ----------
console.log('=== 前端发了但后端对应处理函数从未读取的参数 ===\n')
const IGNORE = new Set(['success', 'message', 'error', 'data', 'items', 'file',
  'Content-Type', 'method', 'headers', 'body', 'token', 'id', 'name'])
walkDir(SRC)
const rows = [...frontendCalls.entries()].sort((a, b) => a[0].localeCompare(b[0]))
let findings = 0
let matched = 0
let matchedWithParams = 0
const unmatched = []
for (const [apiPath, info] of rows) {
  const routes = matchingRoutes(apiPath).filter(route => route.methodNames.size)
  if (!routes.length) { unmatched.push(apiPath); continue }
  matched++
  const read = new Set(routes.flatMap(route => [...route.params]))
  if (info.params.size && read.size) matchedWithParams++
  const missing = [...info.params].filter(param => !IGNORE.has(param) && !read.has(param))
  if (!missing.length) continue
  findings++
  console.log(`  ${apiPath}`)
  console.log(`     后端: ${[...new Set(routes.map(route => route.module))].join(', ')}`)
  console.log(`     前端发送但后端未读: ${missing.join(', ')}`)
  console.log(`     来源: ${[...info.files].join(', ')}\n`)
}
console.log(`共 ${findings} 处线索；字符串扫描不能证明参数一定未使用，需要人工确认。\n`)
console.log('=== 覆盖面自检 ===')
console.log('  解析器固定样例: 通过（路由形式、类型注解、嵌套 helper、模块隔离）')
console.log(`  实际后端路由模块: ${modules.length} 个`)
console.log(`  实际后端路由分支: ${backendRoutes.length} 个`)
console.log(`  后端函数定义: ${modules.reduce((sum, module) => sum + module.methods.size, 0)} 个`)
console.log(`  前端 /api 路径: ${rows.length} 个；匹配处理函数: ${matched} 个`)
console.log(`  同时提取到前端发送参数和后端读取参数的路径: ${matchedWithParams} 个`)
if (unmatched.length) {
  console.log(`  未匹配: ${unmatched.length} 个（动态拼接或尚不支持的路由写法）`)
  for (const entry of unmatched) console.log(`    - ${entry}`)
}
for (const error of frontendParseFailures) console.error(`前端解析失败: ${error}`)
const coverageFailed = !modules.length || !backendRoutes.length || !rows.length || !matched || !matchedWithParams
if (coverageFailed) console.error('覆盖自检失败：没有提取到有效的前后端契约，不能将零匹配视为通过。')
process.exitCode = coverageFailed || frontendParseFailures.length ||
  (process.argv.includes('--strict') && (findings || unmatched.length)) ? 1 : 0
