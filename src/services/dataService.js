/** 业务数据快照：只提交明确修改的部分，并校验其加载时的版本。 */
import { post, get } from './http.js'

let _data = null
let _loadPromise = null
let _queue = Promise.resolve()
const _pending = new Map()
const clone = value => JSON.parse(JSON.stringify(value))

function enqueue(operation) {
  const result = _queue.then(operation)
  _queue = result.catch(() => {})
  return result
}

export async function load() {
  if (_loadPromise) return _loadPromise
  _loadPromise = enqueue(async () => {
    const result = await get('/api/data/load')
    if (result.success === false) throw new Error(result.message || '加载数据失败')
    const data = result.data || result
    if (!data || Array.isArray(data) || typeof data !== 'object' || !data._revisions) {
      throw new Error('服务器未返回有效的数据版本，请重新启动服务后重试')
    }
    _data = data
    return clone(_data)
  }).finally(() => { _loadPromise = null })
  return _loadPromise
}

export function getData(key) {
  if (key === undefined) return clone(_data ?? {})
  return clone(_data?.[key] ?? [])
}

/** Store 应在加载数据时保存此版本，不能在保存前取别的页面刷新后的版本。 */
export function getRevision(key) {
  return _data?._revisions?.[key]
}

export function setData(key, value, revision = getRevision(key)) {
  if (!_data || typeof revision !== 'string' || !revision) {
    throw new Error('数据尚未成功加载，请刷新后重试；本次修改尚未保存')
  }
  if (!Object.hasOwn(_data._revisions, key)) throw new Error(`不支持保存的数据类型：${key}`)
  const entry = { value: clone(value), revision }
  _pending.set(key, entry)
}

export async function save() {
  if (!_data) throw new Error('数据尚未成功加载，已中止保存')
  // 在调用时冻结这次修改，避免排队过程中被其他页面的修改或加载替换。
  const batch = new Map(_pending)
  for (const [key, entry] of batch) {
    if (_pending.get(key) === entry) _pending.delete(key)
  }
  if (!batch.size) return { success: true, _revisions: { ..._data._revisions } }
  return enqueue(async () => {
    const payload = { _snapshot: true, _revisions: {} }
    for (const [key, entry] of batch) {
      payload[key] = entry.value
      payload._revisions[key] = entry.revision
    }
    const result = await post('/api/data/save', payload)
    if (!result.success) throw new Error(result.message || '保存失败，未修改服务端数据')
    // 缓存只记录已提交的数据；值和版本一起更新，避免在途加载留下旧值配新版本。
    for (const [key, entry] of batch) {
      _data[key] = clone(entry.value)
      if (result._revisions?.[key]) _data._revisions[key] = result._revisions[key]
    }
    return result
  })
}

export function isLoaded() {
  return _data !== null
}
