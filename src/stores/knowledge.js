import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const knowledge = ref({ solutions: [], practices: [], training: [] })
  const currentKnowledge = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const loadItems = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      knowledge.value = dataService.getData('knowledge') || { solutions: [], practices: [], training: [] }
    } catch (e) {
      console.error('加载知识库失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const itemsByCategory = (category) => {
    return knowledge.value[category] || []
  }

  const getItemById = (id) => {
    for (const cat of Object.keys(knowledge.value)) {
      const item = knowledge.value[cat].find(k => k.id === id)
      if (item) return item
    }
    return null
  }

  const getKnowledgeByType = (type) => {
    return knowledge.value[type] || []
  }

  const setCurrentKnowledge = (item) => {
    currentKnowledge.value = item
  }

  const saveItem = async (knowledgeData) => {
    loading.value = true
    error.value = null
    try {
      const type = knowledgeData.type || 'solutions'
      const categoryItems = knowledge.value[type] || []
      const now = new Date().toISOString()

      if (!knowledgeData.id) {
        knowledgeData.id = `k${Date.now()}`
        knowledgeData.createdAt = now
        categoryItems.push(knowledgeData)
        knowledge.value[type] = categoryItems
      } else {
        const index = categoryItems.findIndex(k => k.id === knowledgeData.id)
        if (index !== -1) {
          categoryItems[index] = { ...categoryItems[index], ...knowledgeData }
        }
      }
      knowledgeData.updatedAt = now

      dataService.setData('knowledge', knowledge.value)
      await dataService.save()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: !knowledgeData.id ? 'create_knowledge' : 'update_knowledge',
          actionType: !knowledgeData.id ? 'create' : 'update',
          target: '知识库',
          description: `${!knowledgeData.id ? '创建' : '更新'}知识库文章"${knowledgeData.title || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return knowledgeData
    } catch (e) {
      console.error('保存知识失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const updateItem = async (id, knowledgeData) => {
    return saveItem({ ...knowledgeData, id })
  }

  const deleteItem = async (id) => {
    loading.value = true
    error.value = null
    try {
      let deletedItem = null
      for (const cat of Object.keys(knowledge.value)) {
        const found = knowledge.value[cat].find(k => k.id === id)
        if (found) deletedItem = found
        knowledge.value[cat] = knowledge.value[cat].filter(k => k.id !== id)
      }
      if (currentKnowledge.value?.id === id) currentKnowledge.value = null

      dataService.setData('knowledge', knowledge.value)
      await dataService.save()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'delete_knowledge',
          actionType: 'delete',
          target: '知识库',
          description: `删除知识库文章"${deletedItem?.title || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }
    } catch (e) {
      console.error('删除知识失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const getKnowledgeStats = () => {
    return {
      solutions: knowledge.value.solutions?.length || 0,
      practices: knowledge.value.practices?.length || 0,
      training: knowledge.value.training?.length || 0
    }
  }

  return {
    knowledge,
    currentKnowledge,
    loading,
    error,
    loadItems,
    itemsByCategory,
    getItemById,
    getKnowledgeByType,
    setCurrentKnowledge,
    saveItem,
    updateItem,
    deleteItem,
    getKnowledgeStats
  }
})
