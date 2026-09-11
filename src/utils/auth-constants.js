// src/utils/auth-constants.js
/**
 * 认证系统统一常量
 * 所有模块必须使用这些常量，禁止硬编码 localStorage key
 */

// Token 存储 key
export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'workbench_access_token',
  REFRESH_TOKEN: 'workbench_refresh_token',
  USER_INFO: 'workbench_user',
  TOKEN_EXPIRES: 'workbench_token_expires',
  THEME: 'theme'
}

// 认证相关常量
export const AUTH_CONSTANTS = {
  // Token 刷新阈值（毫秒）
  REFRESH_THRESHOLD: 30 * 60 * 1000,  // 30 分钟

  // Token 默认有效期（秒）
  DEFAULT_EXPIRES_IN: 24 * 60 * 60,  // 24 小时

  // 角色等级
  ROLE_HIERARCHY: {
    admin: 100,
    editor: 50,
    viewer: 10
  }
}

// 获取 Token
export function getAccessToken() {
  return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
}

// 获取刷新 Token
export function getRefreshToken() {
  return localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN)
}

// 获取用户信息
export function getUserInfo() {
  const userStr = localStorage.getItem(STORAGE_KEYS.USER_INFO)
  if (!userStr) return null
  try {
    return JSON.parse(userStr)
  } catch {
    return null
  }
}

// 保存认证数据
export function saveAuthData(accessToken, refreshToken, expiresIn, user) {
  localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, accessToken)
  localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken)

  const expiresAt = Date.now() + expiresIn * 1000
  localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRES, expiresAt.toString())

  if (user) {
    localStorage.setItem(STORAGE_KEYS.USER_INFO, JSON.stringify(user))
  }
}

// 清除认证数据
export function clearAuthData() {
  localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN)
  localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN)
  localStorage.removeItem(STORAGE_KEYS.USER_INFO)
  localStorage.removeItem(STORAGE_KEYS.TOKEN_EXPIRES)
}

// 检查是否已登录
export function isLoggedIn() {
  return !!getAccessToken() && !!getUserInfo()
}

// 检查 Token 是否即将过期
export function isTokenExpiringSoon() {
  const expiresAt = parseInt(localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRES) || '0')
  if (!expiresAt) return true
  return expiresAt - Date.now() < AUTH_CONSTANTS.REFRESH_THRESHOLD
}

export function isAccessTokenExpired() {
  const expiresAt = parseInt(localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRES) || '0')
  if (!expiresAt) return true
  return Date.now() >= expiresAt - 60 * 1000
}