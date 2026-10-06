/** HTTP 请求统一携带凭证；并发 401 共享刷新结果，每个请求最多重试一次。 */
import { getAccessToken, clearAuthData } from '../utils/auth-constants'
import { refreshToken } from './auth'

const BASE_URL = ''
let refreshPromise = null

function requireLogin(message = '登录已过期，请重新登录') {
  clearAuthData()
  window.dispatchEvent(new CustomEvent('auth:required'))
  return new Error(message)
}

function refreshAuth() {
  if (!refreshPromise) {
    refreshPromise = Promise.resolve()
      .then(() => refreshToken())
      .catch(() => { throw requireLogin() })
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

async function parseResponse(res) {
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`服务器返回非 JSON 响应 (${res.status}): ${text.slice(0, 200)}`)
  }
}

export function getAuthHeaders(extra = {}) {
  const token = getAccessToken()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra
  }
}

/** 返回原始 Response，适用于 FormData、JSON 和二进制请求。 */
export async function fetchWithAuth(url, options = {}) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const requestToken = getAccessToken()
    const res = await fetch(`${BASE_URL}${url}`, {
      ...options,
      headers: getAuthHeaders(options.headers || {})
    })
    if (res.status !== 401) return res

    const data = await res.clone().json().catch(() => ({}))
    const errorText = `${data.error || ''} ${data.message || ''}`.toLowerCase()
    if (errorText.includes('revoked') || errorText.includes('撤销')) {
      throw requireLogin('Token 已被撤销，请重新登录')
    }
    if (attempt === 1) throw requireLogin()

    // 另一个请求可能已在本次 401 到达前完成刷新；直接用新凭证重试。
    if (!getAccessToken() || getAccessToken() === requestToken) await refreshAuth()
  }
}

async function requestJSON(path, method, body) {
  const res = await fetchWithAuth(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {})
  })
  const data = await parseResponse(res)
  if (!res.ok) throw new Error(data.message || `请求失败 (${res.status})`)
  return data
}

export const get = path => requestJSON(path, 'GET')
export const post = (path, body) => requestJSON(path, 'POST', body)
export const put = (path, body) => requestJSON(path, 'PUT', body)
export const del = path => requestJSON(path, 'DELETE')

/** 获取带鉴权的预览内容，由调用方创建和回收 Blob URL。 */
export async function getBlob(path) {
  const res = await fetchWithAuth(path, { method: 'GET' })
  if (res.ok) return res.blob()
  const data = await parseResponse(res)
  throw new Error(data.message || `请求失败 (${res.status})`)
}
