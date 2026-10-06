import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as dataService from '../services/dataService.js'

import { DEFAULT_CHECKLISTS, GLOBAL_KEY, DEFAULT_TAB_KEYS, buildInitialChecklists, normalizeProjectMap, normalizeChecklistItem } from './checklistModel.js'

export const useChecklistStore = defineStore('checklist', () => {
  // ========== 状态 ==========
  // 结构：{ [projectKey]: { [tabKey]: { label, cards: [{ id, title, items: [{text, checked, isCustom}] }] } } }
  // projectKey = 项目ID；未选中具体项目时用 GLOBAL_KEY（'__global__'）
  const checklists = ref({})
  const activeTab = ref('startup')
  const currentProject = ref('')
  const loading = ref(false)
  const error = ref(null)
  let revision = null
  let operationQueue = Promise.resolve()

  const enqueue = (operation) => {
    const result = operationQueue.then(operation)
    operationQueue = result.catch(() => {})
    return result
  }

  // ========== 计算属性 ==========

  /** 当前激活的项目键：未选中具体项目 → GLOBAL_KEY */
  const currentKey = computed(() => currentProject.value || GLOBAL_KEY)

  /** 当前项目（或全局）的清单结构；不存在时返回空对象（不在此处 mutate） */
  const currentMap = () => checklists.value[currentKey.value] || {}

  /** 当前激活 Tab 的清单数据 */
  const activeChecklist = computed(() => {
    const map = currentMap()
    return map[activeTab.value] || { label: '', cards: [] }
  })

  /** 所有 Tab 的 key 列表（当前项目维度） */
  const tabKeys = computed(() => Object.keys(currentMap()))

  /** Tab 选项列表（含 label，当前项目维度） */
  const tabOptions = computed(() => {
    return Object.entries(currentMap()).map(([key, val]) => ({
      key,
      label: val.label
    }))
  })

  // ========== 内部方法 ==========

  /**
   * 确保某个项目键存在：不存在则用默认清单 seeds 一份。
   * 必须在 action 内调用（会 mutate ref），不要在 computed 里调用。
   */
  const ensureProject = (key) => {
    if (!checklists.value[key]) {
      checklists.value[key] = buildInitialChecklists()
    }
    return checklists.value[key]
  }

  // ========== 对外方法 ==========

  /**
   * 从 dataService 加载清单数据（按项目组织）
   * 兼容旧版「按 tab 平铺」格式：识别到旧结构时整体迁移到 GLOBAL_KEY。
   */
  const readChecklists = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      let saved = dataService.getData('projectChecklists')
      revision = dataService.getRevision('projectChecklists')
      if (!revision) throw new Error('没有读取清单数据的权限')

      // 兼容迁移：旧版清单是 { tabKey: {...} } 的平铺结构（键为 startup/registration…）
      if ((!saved || typeof saved !== 'object' || Array.isArray(saved) || Object.keys(saved).length === 0)
          && dataService.getData('checklists')) {
        const legacy = dataService.getData('checklists')
        if (legacy && typeof legacy === 'object' && !Array.isArray(legacy)
            && Object.keys(legacy).some(k => DEFAULT_TAB_KEYS.includes(k))) {
          saved = { [GLOBAL_KEY]: legacy }
        }
      }

      if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
        // 规范化为对象 items（兼容旧数据里 items 是字符串的情况）
        checklists.value = normalizeProjectMap(saved)
      } else {
        checklists.value = {}
      }

      // 全局视图必须有数据
      ensureProject(GLOBAL_KEY)
      // 当前选中的项目也确保存在
      if (currentProject.value) ensureProject(currentProject.value)
    } catch (e) {
      revision = null
      console.error('加载清单数据失败:', e)
      error.value = e.message
      checklists.value = {}
      ensureProject(GLOBAL_KEY)
      throw e
    } finally {
      loading.value = false
    }
  }

  const loadChecklists = () => enqueue(readChecklists)

  /**
   * 持久化清单数据到 dataService（按项目组织的完整结构）
   */
  const writeChecklists = async () => {
    dataService.setData('projectChecklists', checklists.value, revision)
    const result = await dataService.save()
    revision = result._revisions.projectChecklists
  }

  // 连续点击在同一队列内完成“修改 + 保存”，下一次只使用上一次成功后的版本。
  const mutate = (change) => enqueue(async () => {
    if (!revision) await readChecklists()
    const before = JSON.parse(JSON.stringify(checklists.value))
    loading.value = true
    error.value = null
    try {
      const result = change()
      if (result === false) return false
      await writeChecklists()
      return result
    } catch (e) {
      checklists.value = before
      revision = null
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const persistChecklists = () => mutate(() => { ensureProject(currentKey.value) })

  /**
   * 切换某个检查项的勾选状态
   * @param {string} cardId - 卡片ID
   * @param {number} itemIndex - 项目索引
   */
  const toggleItem = async (cardId, itemIndex) => {
    const key = currentKey.value
    const tabKey = activeTab.value
    return mutate(() => {
      const card = ensureProject(key)[tabKey]?.cards.find(c => c.id === cardId)
      if (!card || card.items[itemIndex] === undefined) return false
      card.items[itemIndex].checked = !card.items[itemIndex].checked
      return true
    })
  }

  /**
   * 重置当前项目（或所有 Tab）的勾选状态
   * @param {string|null} tabKey - 指定 Tab 重置，null 则重置当前项目全部 Tab
   */
  const resetChecklist = async (tabKey = null) => {
    const key = currentKey.value
    return mutate(() => {
      const map = ensureProject(key)
      const tabs = tabKey ? { [tabKey]: map[tabKey] } : map
      for (const tabData of Object.values(tabs)) {
        if (!tabData || !tabData.cards) continue
        for (const card of tabData.cards) {
          for (const item of card.items) item.checked = false
        }
      }
    })
  }

  /**
   * 添加自定义检查项（作用域：当前项目当前 Tab）
   * @param {string} cardId - 卡片ID
   * @param {string} text - 检查项文本
   */
  const addItem = async (cardId, text) => {
    if (!text || !text.trim()) return false
    const key = currentKey.value
    const tabKey = activeTab.value
    return mutate(() => {
      const card = ensureProject(key)[tabKey]?.cards.find(c => c.id === cardId)
      if (!card) return false
      card.items.push({
        text: text.trim(),
        checked: false,
        isCustom: true
      })
      return true
    })
  }

  /**
   * 删除任意检查项（默认项与新加项均可删，作用域：当前项目当前 Tab）
   * @param {string} cardId - 卡片ID
   * @param {number} itemIndex - 项目索引
   * @returns {boolean} 是否删除成功
   */
  const removeItem = async (cardId, itemIndex) => {
    const key = currentKey.value
    const tabKey = activeTab.value
    return mutate(() => {
      const card = ensureProject(key)[tabKey]?.cards.find(c => c.id === cardId)
      if (!card || card.items[itemIndex] === undefined) return false
      card.items.splice(itemIndex, 1)
      return true
    })
  }

  /**
   * 获取某个卡片的完成进度（当前项目维度）
   * @param {string} cardId - 卡片ID
   */
  const getProgress = (cardId) => {
    const map = currentMap()
    const tab = map[activeTab.value]
    if (!tab) return { checked: 0, total: 0, percent: 0 }
    const card = tab.cards.find(c => c.id === cardId)
    if (card) {
      const total = card.items.length
      const checked = card.items.filter(i => i.checked).length
      const percent = total > 0 ? Math.round((checked / total) * 100) : 0
      return { checked, total, percent }
    }
    return { checked: 0, total: 0, percent: 0 }
  }

  /**
   * 获取某个 Tab 的总体完成进度（当前项目维度）
   * @param {string} tabKey
   */
  const getTabProgress = (tabKey) => {
    const map = currentMap()
    const tab = map[tabKey]
    if (!tab) return { checked: 0, total: 0, percent: 0 }
    let checked = 0
    let total = 0
    for (const card of tab.cards) {
      checked += card.items.filter(i => i.checked).length
      total += card.items.length
    }
    const percent = total > 0 ? Math.round((checked / total) * 100) : 0
    return { checked, total, percent }
  }

  /**
   * 切换当前激活的 Tab（在当前项目内校验）
   * @param {string} tab
   */
  const switchTab = (tab) => {
    if (currentMap()[tab]) {
      activeTab.value = tab
    }
  }

  /**
   * 设置当前项目筛选（自动 seeds 该项目清单，作用域切换）
   * @param {string} projectId
   */
  const setProject = (projectId) => {
    currentProject.value = projectId
    ensureProject(currentKey.value)
  }

  return {
    // 状态
    checklists,
    activeTab,
    currentProject,
    loading,
    error,
    // 计算属性
    activeChecklist,
    tabKeys,
    tabOptions,
    // 方法
    loadChecklists,
    toggleItem,
    resetChecklist,
    addItem,
    removeItem,
    getProgress,
    getTabProgress,
    switchTab,
    setProject,
    persistChecklists
  }
})
