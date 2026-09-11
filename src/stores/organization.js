import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

export const useOrganizationStore = defineStore('organization', () => {
  const organizations = ref([])
  const currentOrganization = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const loadOrganizations = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      organizations.value = dataService.getData('organizations') || []
    } catch (e) {
      console.error('加载机构失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const getOrgById = (id) => {
    if (!id) return null
    return organizations.value.find(o => String(o.id) === String(id))
  }

  const setCurrentOrganization = (org) => {
    currentOrganization.value = org
  }

  const addOrganization = async (orgData) => {
    loading.value = true
    error.value = null
    try {
      orgData.id = `o${Date.now()}`
      orgData.createdAt = new Date().toISOString()
      organizations.value.push(orgData)

      dataService.setData('organizations', organizations.value)
      await dataService.save()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'create_organization',
          actionType: 'create',
          target: '机构',
          description: `创建机构"${orgData.name || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return orgData
    } catch (e) {
      console.error('添加机构失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const updateOrganization = async (id, orgData) => {
    loading.value = true
    error.value = null
    try {
      const index = organizations.value.findIndex(o => o.id == id)
      if (index !== -1) {
        organizations.value[index] = {
          ...organizations.value[index],
          ...orgData,
          updatedAt: new Date().toISOString()
        }
      }

      dataService.setData('organizations', organizations.value)
      await dataService.save()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'update_organization',
          actionType: 'update',
          target: '机构',
          description: `更新机构"${orgData.name || organizations.value[index]?.name || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return organizations.value[index]
    } catch (e) {
      console.error('更新机构失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const saveOrganization = async (orgData) => {
    if (orgData.id) {
      return updateOrganization(orgData.id, orgData)
    } else {
      return addOrganization(orgData)
    }
  }

  const deleteOrganization = async (id) => {
    loading.value = true
    error.value = null
    try {
      const org = organizations.value.find(o => o.id === id)
      organizations.value = organizations.value.filter(o => o.id !== id)
      if (currentOrganization.value?.id === id) currentOrganization.value = null

      dataService.setData('organizations', organizations.value)
      await dataService.save()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'delete_organization',
          actionType: 'delete',
          target: '机构',
          description: `删除机构"${org?.name || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }
    } catch (e) {
      console.error('删除机构失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const getOrgStats = () => {
    return { total: organizations.value.length }
  }

  return {
    organizations,
    currentOrganization,
    loading,
    error,
    loadOrganizations,
    getOrgById,
    setCurrentOrganization,
    addOrganization,
    updateOrganization,
    saveOrganization,
    deleteOrganization,
    getOrgStats
  }
})
