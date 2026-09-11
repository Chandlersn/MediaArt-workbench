import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'
import { get } from '../services/http.js'

export const usePlayerStore = defineStore('player', () => {
  const players = ref([])
  const currentPlayer = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const loadPlayers = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      players.value = dataService.getData('players') || []
    } catch (e) {
      console.error('加载选手失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const getPlayerById = (id) => {
    if (!id) return null
    return players.value.find(p => String(p.id) === String(id))
  }

  const setCurrentPlayer = (player) => {
    currentPlayer.value = player
  }

  const savePlayer = async (playerData) => {
    loading.value = true
    error.value = null
    try {
      const now = new Date().toISOString()
      const isNew = !playerData.id
      if (isNew) {
        playerData.id = `pl${Date.now()}`
        playerData.createdAt = now
        players.value.push(playerData)
      } else {
        const index = players.value.findIndex(p => p.id === playerData.id)
        if (index !== -1) {
          players.value[index] = { ...players.value[index], ...playerData }
        }
      }
      playerData.updatedAt = now

      dataService.setData('players', players.value)
      await dataService.save()

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

      return playerData
    } catch (e) {
      console.error('保存选手失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const updatePlayer = async (id, playerData) => {
    return savePlayer({ ...playerData, id })
  }

  const deletePlayer = async (id) => {
    loading.value = true
    error.value = null
    try {
      const player = players.value.find(p => p.id === id)
      players.value = players.value.filter(p => p.id !== id)
      if (currentPlayer.value?.id === id) currentPlayer.value = null

      dataService.setData('players', players.value)
      await dataService.save()

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
  }

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

  const calculateMissingMaterials = async () => {
    const now = Date.now()
    if (missingMaterialsCache && now - missingMaterialsCacheTime < 5000) {
      return missingMaterialsCache
    }

    const config = dataService.getData('config') || {}
    const stageMaterials = config.stageMaterials || {}
    const materialTypes = dataService.getData('materialTypes') || []
    const missingPlayers = []

    for (const player of players.value) {
      const currentStage = player.stage
      const requiredTypes = stageMaterials[currentStage] || []

      if (requiredTypes.length === 0) continue

      const applicableTypes = requiredTypes.filter(typeName => {
        const mt = materialTypes.find(t => t.name === typeName)
        if (!mt) return true
        if (!mt.orgId) return true
        return mt.orgId === player.orgId
      })

      if (applicableTypes.length === 0) continue

      let uploadedTypes = []
      let scanSuccess = false

      try {
        const result = await get(`/api/scan-player-files?name=${encodeURIComponent(player.name)}`)
        if (result.success && result.material_types && result.material_types.length > 0) {
          uploadedTypes = result.material_types
          scanSuccess = true
        } else if (result.success && result.message && result.message.includes('不存在')) {
          scanSuccess = false
        } else if (result.success) {
          scanSuccess = true
        }
      } catch (e) {
        console.warn('扫描选手文件失败，降级到数据检查:', player.name, e)
      }

      if (!scanSuccess) {
        const history = player.stageHistory || player.history || []
        const currentStageHistory = history.find(h => h.stage === currentStage)
        if (currentStageHistory && currentStageHistory.materials) {
          uploadedTypes = currentStageHistory.materials.map(m => m.type)
        } else if (player.materials && player.materials.length > 0) {
          uploadedTypes = player.materials.map(m => m.type)
        }
      }

      const missingTypes = applicableTypes.filter(type => !uploadedTypes.includes(type))

      if (missingTypes.length > 0) {
        missingPlayers.push({
          id: player.id,
          name: player.name,
          stage: currentStage,
          category: player.category,
          missingCount: missingTypes.length,
          missingTypes: missingTypes
        })
        player.missingMaterials = true
        player.missingCount = missingTypes.length
        player.missingTypes = missingTypes
      } else {
        player.missingMaterials = false
        player.missingCount = 0
        player.missingTypes = []
      }
    }

    players.value.forEach(player => {
      if (!missingPlayers.find(mp => mp.id === player.id)) {
        player.missingMaterials = false
        player.missingCount = 0
        player.missingTypes = []
      }
    })

    missingMaterialsCache = {
      total: missingPlayers.length,
      players: missingPlayers
    }
    missingMaterialsCacheTime = now

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
    invalidateMissingMaterialsCache,
    getMissingMaterialsCount,
    getMissingMaterialsPlayers
  }
})
