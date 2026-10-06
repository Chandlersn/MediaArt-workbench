import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

export const useFinanceStore = defineStore('finance', () => {
  const financeRecords = ref([])
  const currentFinance = ref(null)
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

  const readRecords = async () => {
    loaded.value = false
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      financeRecords.value = dataService.getData('finances') || []
      revision = dataService.getRevision('finances')
      loaded.value = true
      return true
    } catch (e) {
      console.error('加载财务记录失败:', e)
      error.value = e.message
      return false
    } finally {
      loading.value = false
    }
  }

  const loadRecords = () => mutate(readRecords)

  const ensureLoaded = async () => {
    if (!loaded.value) await readRecords()
    if (!loaded.value) throw new Error(error.value || '数据加载失败，无法保存，请重试')
  }

  const persist = async candidate => {
    dataService.setData('finances', candidate, revision)
    const result = await dataService.save()
    revision = result._revisions?.finances ?? revision
    financeRecords.value = candidate
    if (currentFinance.value) {
      currentFinance.value = financeRecords.value.find(f => f.id === currentFinance.value.id) || null
    }
  }

  const getRecordById = (id) => {
    return financeRecords.value.find(f => f.id === id)
  }

  const setCurrentFinance = (finance) => {
    currentFinance.value = finance
  }

  const saveRecord = financeData => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const now = new Date().toISOString()
      const isNew = !financeData.id
      const record = { ...financeData, updatedAt: now }
      const candidate = [...financeRecords.value]
      if (isNew) {
        record.id = `f${Date.now()}`
        record.createdAt = now
        candidate.push(record)
      } else {
        const index = financeRecords.value.findIndex(f => f.id === financeData.id)
        if (index === -1) throw new Error('财务记录不存在，请刷新后重试')
        candidate[index] = { ...financeRecords.value[index], ...record }
      }

      await persist(candidate)

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: isNew ? 'create_finance' : 'update_finance',
          actionType: isNew ? 'create' : 'update',
          target: '财务',
          description: `${isNew ? '创建' : '更新'}财务记录"${financeData.title || financeData.category || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return candidate.find(f => f.id === record.id)
    } catch (e) {
      console.error('保存财务记录失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const addRecord = async (financeData) => {
    return saveRecord(financeData)
  }

  const updateRecord = async (id, financeData) => {
    return saveRecord({ ...financeData, id })
  }

  const deleteRecord = id => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const record = financeRecords.value.find(f => f.id === id)
      await persist(financeRecords.value.filter(f => f.id !== id))

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'delete_finance',
          actionType: 'delete',
          target: '财务',
          description: `删除财务记录"${record?.title || record?.category || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }
    } catch (e) {
      console.error('删除财务记录失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const getFinanceStats = (filterType = 'all') => {
    const filtered = filterType === 'all'
      ? financeRecords.value
      : financeRecords.value.filter(f => f.type === filterType)

    const totalIncome = filtered
      .filter(f => f.type === '收入' || f.type === 'income')
      .reduce((sum, f) => sum + (parseFloat(f.amount) || 0), 0)

    const totalExpense = filtered
      .filter(f => f.type === '支出' || f.type === 'expense')
      .reduce((sum, f) => sum + (parseFloat(f.amount) || 0), 0)

    const incomeCount = filtered.filter(f => f.type === '收入' || f.type === 'income').length
    const expenseCount = filtered.filter(f => f.type === '支出' || f.type === 'expense').length

    return {
      totalIncome,
      totalExpense,
      netBalance: totalIncome - totalExpense,
      incomeCount,
      expenseCount
    }
  }

  return {
    financeRecords,
    currentFinance,
    loading,
    loaded,
    error,
    loadRecords,
    getRecordById,
    setCurrentFinance,
    addRecord,
    saveRecord,
    updateRecord,
    deleteRecord,
    getFinanceStats
  }
})
