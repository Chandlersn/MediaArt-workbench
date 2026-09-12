/**
 * 数据服务层：封装后端全量 load/save 接口
 *
 * 替代 window.DataStore，提供响应式友好的数据访问接口。
 * 内部维护一份内存副本，Store 通过此服务读写数据并触发持久化。
 */
import { post, get } from './http.js'

const LOAD_URL = '/api/data/load'
const SAVE_URL = '/api/data/save'

// 内存中的完整数据快照
let _data = null
let _loadPromise = null

/**
 * 加载全量数据（每次都从后端拉取最新数据）
 */
export async function load() {
  if (_loadPromise) return _loadPromise

  _loadPromise = get(LOAD_URL).then(res => {
    _data = res.data || res
    _loadPromise = null
    return _data
  }).catch(err => {
    _loadPromise = null
    throw err
  })

  return _loadPromise
}

/**
 * 读取顶层字段的数据切片
 * @param {string} key - 如 'finances' | 'projects' | 'organizations' | 'players'
 * @returns {Array|Object}
 */
export function getData(key) {
  return _data?.[key] ?? []
}

/**
 * 更新内存中某个顶层字段
 * @param {string} key
 * @param {*} value
 */
export function setData(key, value) {
  if (!_data) _data = {}
  _data[key] = value
}

/**
 * 将当前内存数据全量持久化到后端
 *
 * 防抹库守卫：调用方必须确保数据已加载。若尚未加载，先尝试一次安全加载；
 * 加载失败则中止保存（绝不拿空/陈旧数据覆盖服务端全量数据）。
 */
export async function save() {
  if (!_data) {
    try {
      await load()
    } catch (e) {
      throw new Error('数据未加载，且重新加载失败，已中止保存以防覆盖服务端数据')
    }
  }
  if (!_data) throw new Error('数据未加载，无法保存')
  const result = await post(SAVE_URL, _data)
  if (!result.success) throw new Error(result.message || '保存失败')
  return result
}

/**
 * 判断数据是否已加载
 */
export function isLoaded() {
  return _data !== null
}

