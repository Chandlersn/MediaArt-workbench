/**
 * 临时文件清理 UI 模块
 */

import { get, post } from './http.js'

const API_BASE = ''

export const CleanupUI = {
  initialized: false,
  scanResult: null,

  /**
   * 加载清理配置
   */
  loadConfig() {
    const config = localStorage.getItem('cleanupConfig')
    if (config) {
      try {
        const data = JSON.parse(config)
        return data
      } catch (e) {
        console.error('解析清理配置失败:', e)
      }
    }
    return { period: 'never', lastCheck: null }
  },

  /**
   * 保存清理配置
   */
  saveConfig(period) {
    const config = {
      period: period,
      lastCheck: new Date().toISOString()
    }
    localStorage.setItem('cleanupConfig', JSON.stringify(config))
    return config
  },

  /**
   * 扫描临时文件
   */
  async scanTempFiles() {
    try {
      const result = await get(`${API_BASE}/api/cleanup/scan`)

      console.log('扫描结果:', result)
      this.scanResult = result

      if (result.success) {
        return {
          success: true,
          totalSize: result.total_size,
          fileCount: result.file_count,
          oldFilesCount: result.old_files?.length || 0,
          oldFilesSize: result.old_files?.reduce((sum, f) => sum + f.size, 0) || 0,
          oldFiles: result.old_files || []
        }
      } else {
        throw new Error(result.message || '扫描失败')
      }
    } catch (e) {
      console.error('扫描临时文件失败:', e)
      throw e
    }
  },

  /**
   * 清理临时文件
   */
  async executeCleanup(days = 30) {
    try {
      const result = await post(`${API_BASE}/api/cleanup/execute`, { days: days })

      if (result.success) {
        return {
          success: true,
          deletedCount: result.deleted_count || 0,
          deletedSize: result.deleted_size || 0,
          errors: result.errors || []
        }
      } else {
        throw new Error(result.message || '清理失败')
      }
    } catch (e) {
      console.error('清理临时文件失败:', e)
      throw e
    }
  },

  /**
   * 格式化文件大小
   */
  formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
  },

  /**
   * 检查是否需要自动清理
   */
  checkAutoCleanup() {
    const configStr = localStorage.getItem('cleanupConfig')
    if (!configStr) return

    const config = JSON.parse(configStr)
    if (config.period === 'never') return

    const lastCheck = config.lastCheck ? new Date(config.lastCheck) : null
    const now = new Date()

    // 超过 7 天未检查
    if (!lastCheck || now - lastCheck > 7 * 24 * 60 * 60 * 1000) {
      config.lastCheck = now.toISOString()
      localStorage.setItem('cleanupConfig', JSON.stringify(config))
      return true // 需要提醒清理
    }
    return false
  }
}

// 导出到全局（供 Vue 组件使用）
if (typeof window !== 'undefined') {
  window.CleanupUI = CleanupUI
}
