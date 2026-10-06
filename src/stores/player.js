import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'
import { get } from '../services/http.js'

/** 扫描成功（包括空数组）以磁盘为准，失败时才使用当前阶段的历史资料。 */
export const resolvePlayerMaterialStatus = (player, stageMaterials = {}, materialTypes = [], scanResult = null) => {
  const requiredTypes = (stageMaterials[player.stage] || []).filter(typeName => {
    const type = materialTypes.find(item => item.name === typeName)
    return !type?.orgId || type.orgId === player.orgId
  })
  const scanned = scanResult?.success === true && Array.isArray(scanResult.materials)
  const history = Array.isArray(player.stageHistory) ? player.stageHistory : (Array.isArray(player.history) ? player.history : [])
  const current = history.find(item => item.stage === player.stage)
  const fallback = Array.isArray(current?.materials)
    ? current.materials.map(item => ({ ...item, stage: item.stage || current.stage }))
    : (Array.isArray(player.materials) ? player.materials : [])
  const materials = (scanned ? scanResult.materials : fallback).filter(Boolean).map(item => ({
    ...item,
    type: item.type || item.materialType || '',
    name: item.file_name || item.name || '',
    uploadDate: item.upload_date || item.uploadDate || '',
    stage: item.stage || ''
  }))
  const uploadedTypes = new Set(materials
    .filter(item => !item.stage || item.stage === player.stage)
    .map(item => item.type))
  const missingTypes = requiredTypes.filter(type => !uploadedTypes.has(type))
  return { materials, requiredTypes, missingTypes, missingCount: missingTypes.length, missingMaterials: missingTypes.length > 0, scanned }
}

export const usePlayerStore = defineStore('player', () => {
  const players = ref([])
  const currentPlayer = ref(null)
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

  const readPlayers = async () => {
    loaded.value = false
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      players.value = dataService.getData('players') || []
      invalidateMissingMaterialsCache()
      revision = dataService.getRevision('players')
      loaded.value = true
      return true
    } catch (e) {
      console.error('加载选手失败:', e)
      error.value = e.message
      return false
    } finally {
      loading.value = false
    }
  }

  const loadPlayers = () => mutate(readPlayers)

  const ensureLoaded = async () => {
    if (!loaded.value) await readPlayers()
    if (!loaded.value) throw new Error(error.value || '数据加载失败，无法保存，请重试')
  }

  const persist = async candidate => {
    dataService.setData('players', candidate, revision)
    const result = await dataService.save()
    revision = result._revisions?.players ?? revision
    players.value = candidate
    if (currentPlayer.value) {
      currentPlayer.value = players.value.find(p => p.id === currentPlayer.value.id) || null
    }
  }

  const getPlayerById = (id) => {
    if (!id) return null
    return players.value.find(p => String(p.id) === String(id))
  }

  const setCurrentPlayer = (player) => {
    currentPlayer.value = player
  }

  const savePlayer = playerData => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const now = new Date().toISOString()
      const isNew = !playerData.id
      const record = { ...playerData, updatedAt: now }
      const candidate = [...players.value]
      if (isNew) {
        record.id = `pl${Date.now()}`
        record.createdAt = now
        candidate.push(record)
      } else {
        const index = players.value.findIndex(p => p.id === playerData.id)
        if (index === -1) throw new Error('选手不存在，请刷新后重试')
        candidate[index] = { ...players.value[index], ...record }
      }

      await persist(candidate)

      invalidateMissingMaterialsCache()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: isNew ? 'create_player' : 'update_player',
          actionType: isNew ? 'create' : 'update',
          target: '选手',
          description: `${isNew ? '创建' : '更新'}选手"${playerData.name || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return candidate.find(p => p.id === record.id)
    } catch (e) {
      console.error('保存选手失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const updatePlayer = async (id, playerData) => {
    return savePlayer({ ...playerData, id })
  }

  const deletePlayer = id => mutate(async () => {
    await ensureLoaded()
    loading.value = true
    error.value = null
    try {
      const player = players.value.find(p => p.id === id)
      await persist(players.value.filter(p => p.id !== id))

      invalidateMissingMaterialsCache()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'delete_player',
          actionType: 'delete',
          target: '选手',
          description: `删除选手"${player?.name || '未命名'}"`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }
    } catch (e) {
      console.error('删除选手失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  })

  const getPlayersByOrg = (orgId) => {
    return players.value.filter(p => p.orgId === orgId)
  }

  const getPlayersByProject = (projectId) => {
    return players.value.filter(p => p.projectId === projectId)
  }

  const getPlayerStats = () => {
    return { total: players.value.length }
  }

  // 计算缺失资料的选手（带缓存，5 秒内不重复计算）
  let missingMaterialsCache = null
  let missingMaterialsCacheTime = 0

  const getPlayerMaterialStatus = (player, scanResult = null) => {
    const config = dataService.getData('config') || {}
    return resolvePlayerMaterialStatus(player, config.stageMaterials || {}, dataService.getData('materialTypes') || [], scanResult)
  }

  const applyMaterialStatus = (player, status) => {
    player.missingMaterials = status.missingMaterials
    player.missingCount = status.missingCount
    player.missingTypes = status.missingTypes
  }

  const refreshPlayerMaterials = async (player) => {
    if (!dataService.isLoaded()) await dataService.load()
    let scanResult = null
    try {
      scanResult = await get(`/api/scan-player-files?name=${encodeURIComponent(player.name)}`)
    } catch (e) {
      console.warn('扫描选手文件失败，降级到数据检查:', player.name, e)
    }
    const status = getPlayerMaterialStatus(player, scanResult)
    player.materials = status.materials
    applyMaterialStatus(player, status)
    invalidateMissingMaterialsCache()
    return status
  }

  const calculateMissingMaterials = async () => {
    await ensureLoaded()
    if (missingMaterialsCache && Date.now() - missingMaterialsCacheTime < 5000) {
      return missingMaterialsCache
    }

    const missingPlayers = []
    for (const player of players.value) {
      let status = getPlayerMaterialStatus(player)
      if (status.requiredTypes.length) status = await refreshPlayerMaterials(player)
      else applyMaterialStatus(player, status)
      if (status.missingCount) {
        missingPlayers.push({
          id: player.id, name: player.name, stage: player.stage, category: player.category,
          missingCount: status.missingCount, missingTypes: status.missingTypes
        })
      }
    }
    missingMaterialsCache = { total: missingPlayers.length, players: missingPlayers }
    missingMaterialsCacheTime = Date.now()
    return missingMaterialsCache
  }

  const invalidateMissingMaterialsCache = () => {
    missingMaterialsCache = null
    missingMaterialsCacheTime = 0
  }

  const getMissingMaterialsCount = async () => {
    const result = await calculateMissingMaterials()
    return result.total
  }

  const getMissingMaterialsPlayers = async () => {
    const result = await calculateMissingMaterials()
    return result.players
  }

  return {
    players,
    currentPlayer,
    loading,
    loaded,
    error,
    loadPlayers,
    getPlayerById,
    setCurrentPlayer,
    savePlayer,
    updatePlayer,
    deletePlayer,
    getPlayersByOrg,
    getPlayersByProject,
    getPlayerStats,
    calculateMissingMaterials,
    getPlayerMaterialStatus,
    refreshPlayerMaterials,
    invalidateMissingMaterialsCache,
    getMissingMaterialsCount,
    getMissingMaterialsPlayers
  }
})
