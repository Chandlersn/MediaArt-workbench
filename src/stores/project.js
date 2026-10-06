import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

export const useProjectStore = defineStore('project', () => {
  const projects = ref([])
  const currentProject = ref(null)
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

  const readProjects = async () => {
    loaded.value = false
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      projects.value = dataService.getData('projects') || []
      revision = dataService.getRevision('projects')
      loaded.value = true
      return true
    } catch (e) {
      console.error('加载项目失败:', e)
      error.value = e.message
      return false
    } finally {
      loading.value = false
    }
  }

  const loadProjects = () => mutate(readProjects)

  const ensureLoaded = async () => {
    if (!loaded.value) await readProjects()
    if (!loaded.value) throw new Error(error.value || '数据加载失败，无法保存，请重试')
  }

  const persist = async candidate => {
    dataService.setData('projects', candidate, revision)
    const result = await dataService.save()
    revision = result._revisions?.projects ?? revision
    projects.value = candidate
    if (currentProject.value) {
      currentProject.value = projects.value.find(p => p.id === currentProject.value.id) || null
    }
  }

  const getProjectById = (id) => {
    if (!id) return null
    return projects.value.find(p => String(p.id) === String(id))
  }

  const setCurrentProject = (project) => {
    currentProject.value = project
  }

  const saveProject = projectData => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const now = new Date().toISOString()
      const isNew = !projectData.id
      const record = { ...projectData, updatedAt: now }
      const candidate = [...projects.value]
      if (isNew) {
        record.id = `p${Date.now()}`
        record.createdAt = now
        candidate.push(record)
      } else {
        const index = projects.value.findIndex(p => p.id === projectData.id)
        if (index === -1) throw new Error('项目不存在，请刷新后重试')
        candidate[index] = { ...projects.value[index], ...record }
      }

      await persist(candidate)

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: isNew ? 'create_project' : 'update_project',
          actionType: isNew ? 'create' : 'update',
          target: '项目',
          description: `${isNew ? '创建' : '更新'}项目"${projectData.name || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return candidate.find(p => p.id === record.id)
    } catch (e) {
      console.error('保存项目失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const deleteProject = id => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const project = projects.value.find(p => p.id === id)
      await persist(projects.value.filter(p => p.id !== id))

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'delete_project',
          actionType: 'delete',
          target: '项目',
          description: `删除项目"${project?.name || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }
    } catch (e) {
      console.error('删除项目失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const updateProject = async (id, projectData) => {
    return saveProject({ ...projectData, id })
  }

  const getActiveProjects = () => {
    return projects.value.filter(p => p.status === '进行中')
  }

  const getProjectStats = () => {
    const total = projects.value.length
    const preparing = projects.value.filter(p => p.status === '筹备中').length
    const active = projects.value.filter(p => p.status === '进行中').length
    const completed = projects.value.filter(p => p.status === '已结束').length
    const archived = projects.value.filter(p => p.status === '已归档').length
    return { total, preparing, active, completed, archived }
  }

  return {
    projects,
    currentProject,
    loading,
    loaded,
    error,
    loadProjects,
    getProjectById,
    setCurrentProject,
    saveProject,
    updateProject,
    deleteProject,
    getActiveProjects,
    getProjectStats
  }
})
