import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

export const useOrganizationStore = defineStore('organization', () => {
  const organizations = ref([])
  const currentOrganization = ref(null)
  const loading = ref(false)
  const loaded = ref(false)
  let revision = null
  const error = ref(null)
  let mutationQueue = Promise.resolve()
  const mutate = operation => {
    const result = mutationQueue.then(operation)
    mutationQueue = result.catch(() => {})
    return result
  }

  const readOrganizations = async () => {
    loaded.value = false
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      organizations.value = dataService.getData('organizations') || []
      revision = dataService.getRevision('organizations')
      loaded.value = true
      return true
    } catch (e) {
      console.error('加载机构失败:', e)
      error.value = e.message
      return false
    } finally {
      loading.value = false
    }
  }

  const loadOrganizations = () => mutate(readOrganizations)

  const ensureLoaded = async () => {
    if (!loaded.value) await readOrganizations()
    if (!loaded.value) throw new Error(error.value || '数据加载失败，无法保存，请重试')
  }

  const persist = async candidate => {
    dataService.setData('organizations', candidate, revision)
    const result = await dataService.save()
    revision = result._revisions?.organizations ?? revision
    organizations.value = candidate
    if (currentOrganization.value) {
      currentOrganization.value = organizations.value.find(o => o.id === currentOrganization.value.id) || null
    }
  }

  const getOrgById = (id) => {
    if (!id) return null
    return organizations.value.find(o => String(o.id) === String(id))
  }

  const setCurrentOrganization = (org) => {
    currentOrganization.value = org
  }

  const addOrganization = orgData => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const record = { ...orgData, id: `o${Date.now()}`, createdAt: new Date().toISOString() }
      await persist([...organizations.value, record])

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

      return record
    } catch (e) {
      console.error('添加机构失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const updateOrganization = (id, orgData) => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const index = organizations.value.findIndex(o => o.id == id)
      if (index === -1) throw new Error('机构不存在，请刷新后重试')
      const candidate = [...organizations.value]
      candidate[index] = {
        ...organizations.value[index],
        ...orgData,
        updatedAt: new Date().toISOString()
      }

      await persist(candidate)

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
  })

  const saveOrganization = async (orgData) => {
    if (orgData.id) {
      return updateOrganization(orgData.id, orgData)
    } else {
      return addOrganization(orgData)
    }
  }

  const deleteOrganization = id => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const org = organizations.value.find(o => o.id === id)
      await persist(organizations.value.filter(o => o.id !== id))

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
  })

  const getOrgStats = () => {
    return { total: organizations.value.length }
  }

  return {
    organizations,
    currentOrganization,
    loading,
    loaded,
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
