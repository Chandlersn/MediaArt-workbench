import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

// 5 类语义化知识类型（重设计，不再使用旧的 solutions/practices/training）
// 每类配专属结构化字段模板；color 用于类型色徽与导航高亮，与仓库 CSS 主题变量体系一致。
export const KNOWLEDGE_TYPES = {
  guide: {
    id: 'guide', name: '指南', color: '#3b82f6', desc: '操作步骤 / SOP / 配置参数',
    fields: [
      { key: 'goal', label: '目标', placeholder: '这条指南要达成什么？', rows: 2 },
      { key: 'prerequisites', label: '前置条件', placeholder: '开始前需要准备什么？', rows: 2 },
      { key: 'steps', label: '步骤', placeholder: '逐步操作说明，一行一步或用序号列出', rows: 5 },
      { key: 'verification', label: '验证', placeholder: '如何确认已完成 / 正确？', rows: 2 }
    ]
  },
  troubleshoot: {
    id: 'troubleshoot', name: '排障', color: '#ef4444', desc: '现象 → 根因 → 对策 → 预防',
    fields: [
      { key: 'phenomenon', label: '现象', placeholder: '出现了什么异常 / 报错？', rows: 2 },
      { key: 'rootCause', label: '根因', placeholder: '根本原因是什么？', rows: 2 },
      { key: 'solution', label: '对策', placeholder: '如何修复 / 绕过？', rows: 3 },
      { key: 'prevention', label: '预防', placeholder: '如何避免再次发生？', rows: 2 }
    ]
  },
  case: {
    id: 'case', name: '案例', color: '#f59e0b', desc: '背景 → 过程 → 结果 → 复盘',
    fields: [
      { key: 'background', label: '背景', placeholder: '项目 / 展览背景与约束', rows: 2 },
      { key: 'process', label: '过程', placeholder: '关键做法与决策', rows: 4 },
      { key: 'result', label: '结果', placeholder: '最终成效 / 数据', rows: 2 },
      { key: 'retrospect', label: '复盘', placeholder: '经验得失与可复用点', rows: 3 }
    ]
  },
  tip: {
    id: 'tip', name: '经验', color: '#10b981', desc: '轻量经验心得 / 避坑提示',
    fields: [
      { key: 'point', label: '要点', placeholder: '一句话核心要点', rows: 2 },
      { key: 'note', label: '说明', placeholder: '补充说明（选填）', rows: 3 }
    ]
  },
  reference: {
    id: 'reference', name: '资料', color: '#8b5cf6', desc: '外部文档 / 规范 / 手册索引',
    fields: [
      { key: 'source', label: '来源', placeholder: '出处（作者 / 机构 / 链接名）', rows: 1 },
      { key: 'summary', label: '摘要', placeholder: '核心内容摘要', rows: 3 },
      { key: 'url', label: '链接', placeholder: '原文链接（选填）', rows: 1 }
    ]
  }
}

export const KNOWLEDGE_TYPE_ORDER = ['guide', 'troubleshoot', 'case', 'tip', 'reference']

// 旧类型 → 新类型的一次性持久化迁移映射
const LEGACY_TYPE_MAP = { solutions: 'guide', practices: 'tip', training: 'reference' }

export const useKnowledgeStore = defineStore('knowledge', () => {
  const knowledge = ref({ guide: [], troubleshoot: [], case: [], tip: [], reference: [] })
  const currentKnowledge = ref(null)
  const loading = ref(false)
  const error = ref(null)

  // 规整数据结构：补齐 5 类空桶，并把旧类型数据并入对应新类型
  const normalize = (data) => {
    const next = { guide: [], troubleshoot: [], case: [], tip: [], reference: [] }
    if (data && typeof data === 'object') {
      KNOWLEDGE_TYPE_ORDER.forEach(t => { if (Array.isArray(data[t])) next[t] = data[t] })
      Object.entries(LEGACY_TYPE_MAP).forEach(([old, neu]) => {
        (data[old] || []).forEach(it => {
          if (it && !next[neu].some(x => x.id === it.id)) next[neu].push({ ...it, type: neu })
        })
      })
    }
    return next
  }

  const loadItems = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      knowledge.value = normalize(dataService.getData('knowledge'))
    } catch (e) {
      console.error('加载知识库失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  // 扁平化：所有类型合并为带 kind 字段的数组，便于检索/推荐/统计
  const getAllFlat = () => {
    const out = []
    KNOWLEDGE_TYPE_ORDER.forEach(type => {
      (knowledge.value[type] || []).forEach(item => out.push({ ...item, kind: type }))
    })
    return out
  }

  const itemsByCategory = (category) => knowledge.value[category] || []

  const getKnowledgeByType = (type) => knowledge.value[type] || []

  const getItemById = (id) => {
    for (const t of KNOWLEDGE_TYPE_ORDER) {
      const item = (knowledge.value[t] || []).find(k => k.id === id)
      if (item) return { ...item, kind: t }
    }
    return null
  }

  const getTags = () => {
    const tags = new Set()
    getAllFlat().forEach(it => (it.tags || []).forEach(t => tags.add(t)))
    return Array.from(tags).sort()
  }

  // 检索：标题 +2 / 标签 +2 / 正文 +1 / 多词 +0.5 的加权评分，支持按类型与标签过滤
  const search = (query, opts = {}) => {
    const q = (query || '').trim().toLowerCase()
    const tag = opts.tag || ''
    const type = opts.type || 'all'
    let items = getAllFlat()
    if (type !== 'all') items = items.filter(it => it.kind === type)
    if (tag) items = items.filter(it => (it.tags || []).includes(tag))
    if (!q) return items
    const scored = []
    for (const it of items) {
      let score = 0
      const hayParts = []
      for (const [k, v] of Object.entries(it)) {
        if (typeof v === 'string' && v) hayParts.push(v)
        else if (Array.isArray(v)) hayParts.push(v.join(' '))
        else if (v && typeof v === 'object') {
          hayParts.push(Object.values(v).filter(x => typeof x === 'string').join(' '))
        }
      }
      const hay = hayParts.join('\n').toLowerCase()
      if (hay.includes(q)) score += 1
      if ((it.title || '').toLowerCase().includes(q)) score += 2
      if ((it.tags || []).some(t => t.toLowerCase().includes(q))) score += 2
      q.split(/\s+/).forEach(w => { if (w && hay.includes(w)) score += 0.5 })
      if (score > 0) scored.push({ it, score })
    }
    scored.sort((a, b) => b.score - a.score)
    return scored.map(s => s.it)
  }

  // 跨页关联推荐：按标签 / 关键词重叠给业务实体推荐相关知识
  const recommendFor = (entity) => {
    if (!entity) return []
    const seeds = []
    if (entity.name) seeds.push(entity.name.toLowerCase())
    if (Array.isArray(entity.tags)) entity.tags.forEach(t => seeds.push(t.toLowerCase()))
    if (entity.note) seeds.push(entity.note.toLowerCase())
    if (entity.category) seeds.push(entity.category.toLowerCase())
    const items = getAllFlat()
    const scored = []
    for (const it of items) {
      let score = 0
      const tags = (it.tags || []).map(t => t.toLowerCase())
      seeds.forEach(s => {
        if (tags.includes(s)) score += 3
        const hay = (`${it.title || ''} ${it.description || ''}`).toLowerCase()
        if (hay.includes(s)) score += 1
      })
      if (score > 0) scored.push({ it, score })
    }
    scored.sort((a, b) => b.score - a.score)
    return scored.slice(0, 6).map(s => s.it)
  }

  const getRecent = (n = 6) =>
    getAllFlat().slice().sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || '')).slice(0, n)

  const getKnowledgeStats = () => {
    const stats = {}
    KNOWLEDGE_TYPE_ORDER.forEach(t => { stats[t] = (knowledge.value[t] || []).length })
    return stats
  }

  const setCurrentKnowledge = (item) => { currentKnowledge.value = item }

  const saveItem = async (knowledgeData) => {
    loading.value = true
    error.value = null
    try {
      const type = knowledgeData.type || 'guide'
      const list = knowledge.value[type] || []
      const now = new Date().toISOString()
      const isNew = !knowledgeData.id
      if (isNew) {
        knowledgeData.id = `k${Date.now()}`
        knowledgeData.createdAt = now
        list.push(knowledgeData)
      } else {
        const index = list.findIndex(k => k.id === knowledgeData.id)
        if (index !== -1) list[index] = { ...list[index], ...knowledgeData }
      }
      knowledgeData.updatedAt = now
      knowledge.value[type] = list

      dataService.setData('knowledge', knowledge.value)
      await dataService.save()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: isNew ? 'create_knowledge' : 'update_knowledge',
          actionType: isNew ? 'create' : 'update',
          target: '知识库',
          description: `${isNew ? '创建' : '更新'}知识库文章"${knowledgeData.title || '未命名'}"`
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

  const updateItem = async (id, knowledgeData) => saveItem({ ...knowledgeData, id })

  const deleteItem = async (id) => {
    loading.value = true
    error.value = null
    try {
      let deletedItem = null
      for (const t of KNOWLEDGE_TYPE_ORDER) {
        const list = knowledge.value[t] || []
        const found = list.find(k => k.id === id)
        if (found) deletedItem = found
        knowledge.value[t] = list.filter(k => k.id !== id)
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

  return {
    knowledge,
    currentKnowledge,
    loading,
    error,
    loadItems,
    getAllFlat,
    itemsByCategory,
    getKnowledgeByType,
    getItemById,
    getTags,
    search,
    recommendFor,
    getRecent,
    getKnowledgeStats,
    setCurrentKnowledge,
    saveItem,
    updateItem,
    deleteItem
  }
})
