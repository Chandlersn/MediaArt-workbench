import { defineStore } from 'pinia'
import { ref } from 'vue'
import { get, post } from '../services/http.js'

export const useAuditLogStore = defineStore('auditLog', () => {
  const logs = ref([])
  const loading = ref(false)
  const error = ref(null)

  const loadLogs = async () => {
    loading.value = true
    error.value = null
    try {
      const result = await get('/api/audit-logs')
      if (result.success) {
        logs.value = result.logs || []
      } else {
        error.value = result.message
      }
    } catch (e) {
      console.error('加载审计日志失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const addLog = async (logData) => {
    try {
      await post('/api/audit-logs', {
        action: logData.action || '',
        actionType: logData.actionType || 'update',
        target: logData.target || '',
        description: logData.description || '',
        userName: logData.userName || '系统'
      })
    } catch (e) {
      console.error('记录审计日志失败:', e)
    }
  }

  // 一键清除全部审计日志（需系统设置删除权限，后端校验）
  const clearLogs = async () => {
    const result = await post('/api/audit-logs/clear')
    if (result && result.success) {
      logs.value = []
      return result
    }
    throw new Error((result && result.message) || '清除失败')
  }

  const getLogsByType = (actionType) => {
    return logs.value.filter(l => l.actionType === actionType)
  }

  const getLogsByDateRange = (startDate, endDate) => {
    return logs.value.filter(l => {
      const date = new Date(l.createdAt)
      return date >= new Date(startDate) && date <= new Date(endDate)
    })
  }

  return {
    logs,
    loading,
    error,
    loadLogs,
    addLog,
    clearLogs,
    getLogsByType,
    getLogsByDateRange
  }
})
