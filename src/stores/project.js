import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

export const useProjectStore = defineStore('project', () => {
  const projects = ref([])
  const currentProject = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const loadProjects = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      projects.value = dataService.getData('projects') || []
    } catch (e) {
      console.error('加载项目失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const getProjectById = (id) => {
    if (!id) return null
    return projects.value.find(p => String(p.id) === String(id))
  }

  const setCurrentProject = (project) => {
    currentProject.value = project
  }

  const saveProject = async (projectData) => {
    loading.value = true
    error.value = null
    try {
      const now = new Date().toISOString()
      const isNew = !projectData.id
      if (isNew) {
        projectData.id = `p${Date.now()}`
        projectData.createdAt = now
        projects.value.push(projectData)
      } else {
        const index = projects.value.findIndex(p => p.id === projectData.id)
        if (index !== -1) {
          projects.value[index] = { ...projects.value[index], ...projectData }
        }
      }
      projectData.updatedAt = now

      dataService.setData('projects', projects.value)
      await dataService.save()

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

      return projectData
    } catch (e) {
      console.error('保存项目失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const deleteProject = async (id) => {
    loading.value = true
    error.value = null
    try {
      const project = projects.value.find(p => p.id === id)
      projects.value = projects.value.filter(p => p.id !== id)
      if (currentProject.value?.id === id) currentProject.value = null

      dataService.setData('projects', projects.value)
      await dataService.save()

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
  }

  const updateProject = async (id, projectData) => {
    loading.value = true
    error.value = null
    try {
      const index = projects.value.findIndex(p => p.id === id)
      if (index !== -1) {
        projects.value[index] = { ...projects.value[index], ...projectData }
        dataService.setData('projects', projects.value)
        await dataService.save()
      }
    } catch (e) {
      console.error('更新项目失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
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
