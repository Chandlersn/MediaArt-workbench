import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'

// 资源中心默认分类（与旧版扩展名分类对齐，仅通用素材分类）。
// 注意：项目资料 / 选手资料 / 机构资料 不在此处 —— 它们由归档管理集中维护
// （MediaArt_Archives/01_项目资料、02_选手档案、03_合作机构），不应出现在资源中心。
const DEFAULT_CATEGORIES = [
  { id: 'image', name: '图片素材', folder: 'images', icon: '🖼' },
  { id: 'video', name: '视频素材', folder: 'videos', icon: '🎬' },
  { id: 'document', name: '文档资料', folder: 'documents', icon: '📄' },
  { id: 'audio', name: '音频素材', folder: 'audios', icon: '🎵' }
]

// 归档管理专属分类（资源中心不展示，避免与归档重复、且对应文件夹恒为空）
const ARCHIVE_RESERVED_CATEGORY_IDS = ['project', 'player', 'organization']

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
      // 1) 过滤归档管理专属分类（项目/选手/机构），它们不应出现在资源中心
      // 2) 修正历史遗留：音频分类 folder 曾写成单数 audio，磁盘目录为 audios
      let changed = false
      const cleaned = cats
        .filter(c => {
          const drop = ARCHIVE_RESERVED_CATEGORY_IDS.includes(c.id)
          if (drop) changed = true
          return !drop
        })
        .map(c => {
          if (c.id === 'audio' && c.folder === 'audio') {
            changed = true
            return { ...c, folder: 'audios' }
          }
          return c
        })
      if (changed) await persist(cleaned)
      categories.value = cleaned
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
