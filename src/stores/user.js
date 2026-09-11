import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useAuditLogStore } from './auditLog'
import { get, post, put, del } from '../services/http.js'

export const useUserStore = defineStore('user', () => {
  const users = ref([])
  const currentUser = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const loadUsers = async () => {
    loading.value = true
    error.value = null
    try {
      const result = await get('/api/users')
      if (result.success) {
        users.value = result.users || []
      } else {
        error.value = result.message
      }
    } catch (e) {
      console.error('加载用户失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const getUserById = (id) => {
    return users.value.find(u => u.id === id)
  }

  const addUser = async (userData) => {
    loading.value = true
    error.value = null
    try {
      const result = await post('/api/users', userData)
      if (result.success) {
        users.value.push(result.user)
        try {
          const auditStore = useAuditLogStore()
          await auditStore.addLog({
            action: 'create_user',
            actionType: 'create',
            target: '用户',
            description: `创建用户"${userData.name || '未命名'}"`
          })
        } catch (e) {
          console.warn('记录审计日志失败:', e)
        }
        // initialPassword 仅在未指定密码、由后端随机生成时存在，需回传给调用方展示一次
        return { ...result.user, initialPassword: result.initialPassword }
      } else {
        error.value = result.message
        throw new Error(result.message)
      }
    } catch (e) {
      console.error('添加用户失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const updateUser = async (id, userData) => {
    loading.value = true
    error.value = null
    try {
      const result = await put(`/api/users/${id}`, userData)
      if (result.success) {
        const index = users.value.findIndex(u => u.id === id)
        if (index !== -1) {
          users.value[index] = { ...users.value[index], ...userData }
        }
        try {
          const auditStore = useAuditLogStore()
          await auditStore.addLog({
            action: 'update_user',
            actionType: 'update',
            target: '用户',
            description: `更新用户"${userData.name || '未命名'}"`
          })
        } catch (e) {
          console.warn('记录审计日志失败:', e)
        }
        return users.value[index]
      } else {
        error.value = result.message
        throw new Error(result.message)
      }
    } catch (e) {
      console.error('更新用户失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const deleteUser = async (id) => {
    loading.value = true
    error.value = null
    try {
      const user = users.value.find(u => u.id === id)
      const result = await del(`/api/users/${id}`)
      if (result.success) {
        users.value = users.value.filter(u => u.id !== id)
        try {
          const auditStore = useAuditLogStore()
          await auditStore.addLog({
            action: 'delete_user',
            actionType: 'delete',
            target: '用户',
            description: `删除用户"${user?.name || '未命名'}"`
          })
        } catch (e) {
          console.warn('记录审计日志失败:', e)
        }
      } else {
        error.value = result.message
        throw new Error(result.message)
      }
    } catch (e) {
      console.error('删除用户失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const toggleUserStatus = async (id) => {
    loading.value = true
    error.value = null
    try {
      const result = await post(`/api/users/${id}/toggle-status`)
      if (result.success) {
        const index = users.value.findIndex(u => u.id === id)
        if (index !== -1) {
          users.value[index].status = result.status
        }
        return result.status
      } else {
        error.value = result.message
        throw new Error(result.message)
      }
    } catch (e) {
      console.error('切换用户状态失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const getUserStats = () => {
    const total = users.value.length
    const active = users.value.filter(u => u.status === 'active').length
    const inactive = users.value.filter(u => u.status !== 'active').length
    const byRole = {}
    for (const u of users.value) {
      byRole[u.role] = (byRole[u.role] || 0) + 1
    }
    return { total, active, inactive, byRole }
  }

  return {
    users,
    currentUser,
    loading,
    error,
    loadUsers,
    getUserById,
    addUser,
    updateUser,
    deleteUser,
    toggleUserStatus,
    getUserStats
  }
})
