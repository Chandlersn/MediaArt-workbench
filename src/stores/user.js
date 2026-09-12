import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useAuditLogStore } from './auditLog'
import { get, post, put, del } from '../services/http.js'

export const useUserStore = defineStore('user', () => {
  const users = ref([])
  const currentUser = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const permissions = ref(null) // 当前登录用户的有效权限矩阵 { module: [actions] }
  const role = ref('')

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

  const loadPermissions = async () => {
    try {
      const result = await get('/api/permissions/me')
      if (result.success) {
        permissions.value = result.permissions || {}
        role.value = result.role || ''
      }
    } catch (e) {
      console.error('加载权限失败:', e)
    }
  }

  const can = (module, action) => {
    const acts = permissions.value?.[module] || []
    return acts.includes(action)
  }

  const savePermissions = async (matrix) => {
    const result = await put('/api/permissions/roles', { roles: matrix })
    if (result.success) {
      return result
    } else {
      throw new Error(result.message || '保存失败')
    }
  }

  const getUserById = (id) => {
    return users.value.find(u => u.id === id)
  }

  const addUser = async (userData) => {
    loading.value = true
    error.value = null
    try {
      // 后端 users 表字段：username / real_name / email / role / password
      const payload = {
        username: userData.username,
        real_name: userData.real_name ?? userData.realName ?? userData.name ?? '',
        password: userData.password || '',
        email: userData.email || '',
        role: userData.role || 'viewer'
      }
      const result = await post('/api/users', payload)
      if (result.success) {
        users.value.push(result.user)
        try {
          const auditStore = useAuditLogStore()
          await auditStore.addLog({
            action: 'create_user',
            actionType: 'create',
            target: '用户',
            description: `创建用户"${payload.real_name || payload.username}"`
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
      const payload = {}
      if (userData.real_name !== undefined || userData.realName !== undefined || userData.name !== undefined) {
        payload.real_name = userData.real_name ?? userData.realName ?? userData.name ?? ''
      }
      if (userData.email !== undefined) payload.email = userData.email
      if (userData.role !== undefined) payload.role = userData.role
      if (userData.is_active !== undefined || userData.isActive !== undefined) {
        payload.is_active = userData.is_active ?? userData.isActive
      }
      if (userData.password) payload.password = userData.password

      const result = await put(`/api/users/${id}`, payload)
      if (result.success) {
        const index = users.value.findIndex(u => u.id === id)
        if (index !== -1) {
          users.value[index] = result.user || { ...users.value[index], ...payload }
        }
        try {
          const auditStore = useAuditLogStore()
          await auditStore.addLog({
            action: 'update_user',
            actionType: 'update',
            target: '用户',
            description: `更新用户"${payload.real_name || users.value[index]?.username || ''}"`
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
            description: `删除用户"${user?.realName || user?.username || '未命名'}"`
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
          users.value[index].isActive = result.status
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
    const active = users.value.filter(u => u.isActive !== 0 && u.isActive !== false).length
    const inactive = users.value.filter(u => u.isActive === 0 || u.isActive === false).length
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
    permissions,
    role,
    loadUsers,
    loadPermissions,
    can,
    savePermissions,
    getUserById,
    addUser,
    updateUser,
    deleteUser,
    toggleUserStatus,
    getUserStats
  }
})
