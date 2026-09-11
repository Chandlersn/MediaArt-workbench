/**
 * JWT Token 认证管理模块
 * 使用 auth-constants.js 统一常量
 */

import {
  getAccessToken,
  getRefreshToken,
  getUserInfo,
  saveAuthData,
  clearAuthData,
  isLoggedIn,
  isTokenExpiringSoon,
  isAccessTokenExpired
} from '../utils/auth-constants'

const API_BASE = ''

// 直接导出 auth-constants 的函数
export {
  getAccessToken,
  getRefreshToken,
  getUserInfo,
  getUserInfo as getCurrentUser,
  isLoggedIn as isAuthenticated,
  isTokenExpiringSoon,
  isAccessTokenExpired
}

/**
 * 刷新 Token
 */
export async function refreshToken() {
  const refreshToken = getRefreshToken()

  if (!refreshToken) {
    clearAuthData()
    throw new Error('没有刷新 Token')
  }

  try {
    const response = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ refresh_token: refreshToken })
    })

    const data = await response.json()

    if (data.success) {
      saveAuthData(data.access_token, data.refresh_token, data.expires_in, data.user)
      console.log('Token 刷新成功')
      return data
    } else {
      clearAuthData()
      throw new Error(data.message || 'Token 刷新失败')
    }
  } catch (error) {
    console.error('Token 刷新失败:', error)
    clearAuthData()
    throw error
  }
}

/**
 * 登录
 */
export async function login(username, password) {
  try {
    const response = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ username, password })
    })

    const data = await response.json()

    if (data.success) {
      saveAuthData(data.access_token, data.refresh_token, data.expires_in, data.user)
      console.log('登录成功:', data.user.username)
      return data
    } else {
      throw new Error(data.message || '登录失败')
    }
  } catch (error) {
    console.error('登录失败:', error)
    throw error
  }
}

/**
 * 登出
 */
export async function logout() {
  try {
    const token = getAccessToken()
    if (token) {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
    }
  } catch (e) {
    console.warn('通知服务端注销失败:', e)
  }
  clearAuthData()
  console.log('已登出')
}