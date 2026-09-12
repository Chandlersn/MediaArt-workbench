import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'

// 资源中心默认分类（与旧版扩展名分类对齐，并补充业务资料分类）
const DEFAULT_CATEGORIES = [
  { id: 'image', name: '图片素材', folder: 'images', icon: '🖼' },
  { id: 'video', name: '视频素材', folder: 'videos', icon: '🎬' },
  { id: 'document', name: '文档资料', folder: 'documents', icon: '📄' },
  { id: 'audio', name: '音频素材', folder: 'audio', icon: '🎵' },
  { id: 'project', name: '项目资料', folder: 'projects', icon: '📋' },
  { id: 'player', name: '选手资料', folder: 'players', icon: '👥' },
  { id: 'organization', name: '机构资料', folder: 'organizations', icon: '🏢' }
]

export const useResourceStore = defineStore('resource', () => {
  const categories = ref([])
  const loading = ref(false)

  const load = async () => {
    loading.value = true
    try {
      await dataService.load()
      const config = dataService.getData('config') || {}
      let cats = config.resourceCategories
      if (!Array.isArray(cats) || !cats.length) {
        cats = DEFAULT_CATEGORIES.map(c => ({ ...c }))
        await persist(cats)
      }
      categories.value = cats
    } catch (e) {
      console.error('加载资源分类失败:', e)
      categories.value = DEFAULT_CATEGORIES.map(c => ({ ...c }))
    } finally {
      loading.value = false
    }
  }

  const persist = async (cats) => {
    const config = dataService.getData('config') || {}
    config.resourceCategories = cats
    dataService.setData('config', config)
    try {
      await dataService.save()
    } catch (e) {
      console.warn('保存资源分类失败:', e)
    }
  }

  const addCategory = async (cat) => {
    const folder = (cat.folder || '').trim()
    const name = (cat.name || '').trim()
    if (!name || !folder) return false
    const id = folder.toLowerCase().replace(/[^a-z0-9]/g, '_')
    if (categories.value.some(c => c.id === id || c.folder === folder)) return false
    const next = [...categories.value, { id, name, folder, icon: cat.icon || '📁' }]
    categories.value = next
    await persist(next)
    return true
  }

  const updateCategory = async (id, patch) => {
    const next = categories.value.map(c => (c.id === id ? { ...c, ...patch } : c))
    categories.value = next
    await persist(next)
  }

  const deleteCategory = async (id) => {
    // 仅移除分类定义，不删除文件夹中已有文件
    const next = categories.value.filter(c => c.id !== id)
    categories.value = next
    await persist(next)
  }

  return { categories, loading, load, addCategory, updateCategory, deleteCategory }
})
