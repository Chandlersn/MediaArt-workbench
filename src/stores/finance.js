import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

export const useFinanceStore = defineStore('finance', () => {
  const financeRecords = ref([])
  const currentFinance = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const loadRecords = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      financeRecords.value = dataService.getData('finances') || []
    } catch (e) {
      console.error('加载财务记录失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const getRecordById = (id) => {
    return financeRecords.value.find(f => f.id === id)
  }

  const setCurrentFinance = (finance) => {
    currentFinance.value = finance
  }

  const saveRecord = async (financeData) => {
    loading.value = true
    error.value = null
    try {
      const now = new Date().toISOString()
      if (!financeData.id) {
        financeData.id = `f${Date.now()}`
        financeData.createdAt = now
        financeRecords.value.push(financeData)
      } else {
        const index = financeRecords.value.findIndex(f => f.id === financeData.id)
        if (index !== -1) {
          financeRecords.value[index] = { ...financeRecords.value[index], ...financeData }
        }
      }
      financeData.updatedAt = now

      dataService.setData('finances', financeRecords.value)
      await dataService.save()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: !financeData.id ? 'create_finance' : 'update_finance',
          actionType: !financeData.id ? 'create' : 'update',
          target: '财务',
          description: `${!financeData.id ? '创建' : '更新'}财务记录"${financeData.title || financeData.category || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return financeData
    } catch (e) {
      console.error('保存财务记录失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const addRecord = async (financeData) => {
    return saveRecord(financeData)
  }

  const updateRecord = async (id, financeData) => {
    return saveRecord({ ...financeData, id })
  }

  const deleteRecord = async (id) => {
    loading.value = true
    error.value = null
    try {
      const record = financeRecords.value.find(f => f.id === id)
      financeRecords.value = financeRecords.value.filter(f => f.id !== id)
      if (currentFinance.value?.id === id) currentFinance.value = null

      dataService.setData('finances', financeRecords.value)
      await dataService.save()

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
  }

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
