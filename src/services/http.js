/**
 * 底层 HTTP 封装，统一处理 token、JSON 序列化、错误响应
 * 支持 401 自动刷新 Token 并重试
 */

import { getAccessToken, clearAuthData } from '../utils/auth-constants'
import { refreshToken } from './auth'

const BASE_URL = ''

// 防止刷新 token 时并发请求导致多次刷新
let isRefreshing = false
let refreshSubscribers = []

function getHeaders(extra = {}) {
  const token = getAccessToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra
  }
}

async function parseResponse(res) {
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`服务器返回非 JSON 响应 (${res.status}): ${text.slice(0, 200)}`)
  }
}

/**
 * 处理响应，支持 401 自动刷新 Token
 */
async function handleResponse(res, retryFn) {
  const data = await parseResponse(res)

  if (res.ok) return data

  // 401 未授权，尝试刷新 Token
  if (res.status === 401) {
    const errorCode = data.error || data.message || ''

    if (errorCode.includes('REVOKED') || errorCode.includes('撤销')) {
      clearAuthData()
      window.dispatchEvent(new CustomEvent('auth:required'))
      throw new Error('Token 已被撤销，请重新登录')
    }

    if (errorCode.includes('TOKEN') || errorCode.includes('token') || errorCode.includes('认证')) {
      if (!isRefreshing) {
        isRefreshing = true
        try {
          await refreshToken()
          isRefreshing = false
          // 通知所有等待的请求重试
          refreshSubscribers.forEach(cb => cb())
          refreshSubscribers = []
          // 重试原请求
          return retryFn()
        } catch (refreshError) {
          isRefreshing = false
          refreshSubscribers = []
          clearAuthData()
          // 触发全局登录（通过路由守卫）
          window.dispatchEvent(new CustomEvent('auth:required'))
          throw new Error('登录已过期，请重新登录')
        }
      } else {
        // 等待刷新完成后再重试
        return new Promise((resolve) => {
          refreshSubscribers.push(() => {
            resolve(retryFn())
          })
        })
      }
    }
  }

  throw new Error(data.message || `请求失败 (${res.status})`)
}

export async function get(path) {
  const doRequest = async () => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'GET',
      headers: getHeaders()
    })
    return handleResponse(res, doRequest)
  }
  return doRequest()
}

export async function post(path, body) {
  const doRequest = async () => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(body)
    })
    return handleResponse(res, doRequest)
  }
  return doRequest()
}

export async function put(path, body) {
  const doRequest = async () => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(body)
    })
    return handleResponse(res, doRequest)
  }
  return doRequest()
}

export async function del(path) {
  const doRequest = async () => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'DELETE',
      headers: getHeaders()
    })
    return handleResponse(res, doRequest)
  }
  return doRequest()
}

/**
 * 以带鉴权头的方式获取二进制内容（图片 / PDF / 视频 / 音频预览用）
 *
 * 为什么不能直接把接口 URL 塞进 <img src> / <iframe src> / <video src>：
 * 元素级请求由浏览器发起，**不会附带 Authorization 头**，而下载类接口都要求 JWT，
 * 结果是拿到 401、什么都显示不出来。这里用 fetch 取回 Blob，再由调用方
 * createObjectURL 交给元素使用，凭证始终走请求头、不落到 URL 上。
 *
 * 错误响应（含 401）仍是 JSON，交给 handleResponse 复用 token 刷新与重试逻辑。
 */
export async function getBlob(path) {
  const doRequest = async () => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'GET',
      headers: getHeaders()
    })
    if (res.ok) return res.blob()
    return handleResponse(res, doRequest)
  }
  return doRequest()
}

/**
 * 获取带 token 的请求头（用于 FormData 等非 JSON 请求）
 */
export function getAuthHeaders(extra = {}) {
  const token = getAccessToken()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra
  }
}

/**
 * 通用 fetch 包装器，自动携带 token，支持 401 刷新
 * @param {string} url - 请求 URL
 * @param {object} options - fetch 选项
 * @returns {Promise<Response>}
 */
export async function fetchWithAuth(url, options = {}) {
  const doRequest = async () => {
    const headers = getAuthHeaders(options.headers || {})
    const res = await fetch(`${BASE_URL}${url}`, { ...options, headers })

    if (res.status === 401) {
      if (!isRefreshing) {
        isRefreshing = true
        try {
          await refreshToken()
          isRefreshing = false
          refreshSubscribers.forEach(cb => cb())
          refreshSubscribers = []
          return doRequest()
        } catch {
          isRefreshing = false
          refreshSubscribers = []
          clearAuthData()
          window.dispatchEvent(new CustomEvent('auth:required'))
          throw new Error('登录已过期，请重新登录')
        }
      } else {
        return new Promise((resolve) => {
          refreshSubscribers.push(() => resolve(doRequest()))
        })
      }
    }

    return res
  }
  return doRequest()
}
