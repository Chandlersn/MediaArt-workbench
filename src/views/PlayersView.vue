<template>
  <div class="players-page">
    <div class="page-header">
      <h2>选手</h2>
      <div class="header-buttons">
        <button class="btn-secondary" @click="showImportModal = true">
          批量导入
        </button>
        <button class="btn-primary" @click="$router.push('/players/new')">
          添加选手
        </button>
      </div>
    </div>

    <div id="playerMissingMaterialsAlert" class="missing-materials-alert" v-if="missingMaterialsTotal > 0">
      <div class="alert-content">
        <span class="alert-icon">⚠️</span>
        <span class="alert-text">待完善资料人员 ({{ missingMaterialsTotal }}人)</span>
      </div>
    </div>

    <div class="filter-bar">
      <input
        v-model="searchKeyword"
        type="text"
        class="search-input"
        placeholder="搜索选手..."
      />
      <CustomSelect v-model="filterCategory">
        <option value="all">全部类别</option>
        <option value="音乐">音乐</option>
        <option value="舞蹈">舞蹈</option>
        <option value="美术">美术</option>
        <option value="戏剧">戏剧</option>
        <option value="其他">其他</option>
      </CustomSelect>
      <button
        class="btn-secondary"
        @click="toggleSelectAll"
      >
        {{ isAllSelected ? '取消全选' : '全选' }}
      </button>
    </div>

    <div class="player-list">
      <div v-if="filteredPlayers.length === 0" class="empty-state">
        {{ searchKeyword ? '没有找到匹配的选手' : '暂无选手' }}
      </div>
      <div
        v-for="player in filteredPlayers"
        :key="player.id"
        class="player-card"
        :class="{ 'missing-materials': player.missingMaterials, 'selected': selectedIds.has(player.id) }"
        @click="$router.push(`/players/${player.id}`)"
      >
        <div class="player-card-header">
          <div class="player-header-left">
            <input
              type="checkbox"
              class="card-checkbox"
              :checked="selectedIds.has(player.id)"
              @click.stop="toggleSelect(player.id)"
            />
            <h3 class="player-name">{{ player.name }}</h3>
          </div>
          <span :class="['player-gender', `gender-${player.gender}`]">{{ player.gender }}</span>
        </div>
        <div class="player-card-body">
          <span class="player-category">{{ player.category || '未分类' }}</span>
          <span class="player-level" v-if="player.level">{{ player.level }}</span>
        </div>
        <div class="player-card-footer">
          <span class="player-meta">
            项目：{{ getProjectName(player) }} | 机构：{{ getOrgName(player) }}
          </span>
          <span v-if="player.missingCount > 0" class="missing-badge" title="缺失资料">
            缺{{ player.missingCount }}项
          </span>
        </div>
      </div>
    </div>

    <Pagination
      :total-items="totalCount"
      :page-size="pageSize"
      :current-page="currentPage"
      @page-change="handlePageChange"
      @page-size-change="handlePageSizeChange"
    />

    <div v-if="selectedIds.size > 0" class="batch-actions">
      <span>已选择 {{ selectedIds.size }} 项</span>
      <button @click="batchDelete" class="danger">批量删除</button>
      <button @click="clearSelection">取消选择</button>
    </div>

    <div v-if="showImportModal" class="modal-overlay" @click.self="showImportModal = false">
      <div class="modal-content" style="max-width: 600px;">
        <div class="modal-header">
          <h3>批量导入选手</h3>
          <button class="modal-close" @click="showImportModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="importStep === 1">
            <p style="margin-bottom: 12px;">第一步：下载导入模板</p>
            <button class="btn-secondary" @click="downloadTemplate">下载CSV模板</button>
          </div>
          <div v-if="importStep === 2">
            <p style="margin-bottom: 12px;">第二步：选择CSV文件</p>
            <input type="file" ref="importFileInput" accept=".csv" @change="handleImportFileSelect" style="display:none;" />
            <button class="btn-secondary" @click="importFileInput?.click()">选择文件</button>
            <span v-if="importFile" style="margin-left: 12px;">{{ importFile.name }}</span>
            <div style="margin-top: 16px; display: flex; gap: 8px;">
              <button class="btn-secondary" @click="importStep = 1">上一步</button>
              <button class="btn-primary" @click="previewImport" :disabled="!importFile">预览</button>
            </div>
          </div>
          <div v-if="importStep === 3">
            <p style="margin-bottom: 12px;">第三步：预览数据（前5行）</p>
            <div v-if="importPreview.length > 0" class="preview-table-wrap">
              <table class="preview-table">
                <thead>
                  <tr>
                    <th v-for="h in importHeaders" :key="h">{{ h }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in importPreview.slice(0, 5)" :key="i">
                    <td v-for="h in importHeaders" :key="h">{{ row[h] }}</td>
                  </tr>
                </tbody>
              </table>
              <p style="font-size: 13px; color: var(--text-secondary); margin-top: 8px;">
                共 {{ importPreview.length }} 条数据
              </p>
            </div>
            <div style="margin-top: 16px; display: flex; gap: 8px;">
              <button class="btn-secondary" @click="importStep = 2">上一步</button>
              <button class="btn-primary" @click="executeImport">确认导入</button>
            </div>
          </div>
          <div v-if="importStep === 4">
            <p style="margin-bottom: 12px;">导入结果</p>
            <p>成功导入：{{ importResult.imported }} 条</p>
            <p v-if="importResult.failed > 0" style="color: var(--danger-color);">失败：{{ importResult.failed }} 条</p>
            <ul v-if="importResult.errors?.length" style="font-size: 13px; color: var(--danger-color);">
              <li v-for="(err, i) in importResult.errors" :key="i">{{ err }}</li>
            </ul>
            <div style="margin-top: 16px;">
              <button class="btn-primary" @click="closeImportModal">完成</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import { usePlayerStore, useProjectStore, useOrganizationStore } from '../stores'
import * as dataService from '../services/dataService.js'
import Pagination from '../components/Pagination.vue'
import { get, fetchWithAuth } from '../services/http.js'
import CustomSelect from '../components/CustomSelect.vue'

const playerStore = usePlayerStore()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()

const searchKeyword = ref('')
const filterCategory = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const allPlayers = ref([])
const loading = ref(false)
const showImportModal = ref(false)
const importStep = ref(1)
const importFile = ref(null)
const importFileInput = ref(null)
const importPreview = ref([])
const importHeaders = ref([])
const importResult = ref({ imported: 0, failed: 0, errors: [] })
const selectedIds = ref(new Set())

const computeMissingMaterials = async (playerList) => {
  if (!dataService.isLoaded()) {
    await dataService.load()
  }

  const config = dataService.getData('config') || {}
  const stageMaterials = config.stageMaterials || {}
  const materialTypes = dataService.getData('materialTypes') || []

  let pageMissing = 0

  for (const player of playerList) {
    const currentStage = player.stage
    const requiredTypes = stageMaterials[currentStage] || []

    if (requiredTypes.length === 0) {
      player.missingMaterials = false
      player.missingCount = 0
      player.missingTypes = []
      continue
    }

    const applicableTypes = requiredTypes.filter(typeName => {
      const mt = materialTypes.find(t => t.name === typeName)
      if (!mt) return true
      if (!mt.orgId) return true
      return mt.orgId === player.orgId
    })

    if (applicableTypes.length === 0) {
      player.missingMaterials = false
      player.missingCount = 0
      player.missingTypes = []
      continue
    }

    let uploadedTypes = []
    const stageHistory = player.stageHistory
    const history = Array.isArray(stageHistory) ? stageHistory :
      (Array.isArray(player.history) ? player.history : [])
    const currentStageHistory = history.find(h => h.stage === currentStage)
    if (currentStageHistory && currentStageHistory.materials) {
      uploadedTypes = currentStageHistory.materials.map(m => m.type)
    } else if (player.materials && player.materials.length > 0) {
      uploadedTypes = player.materials.map(m => m.type)
    }

    const missingTypes = applicableTypes.filter(type => !uploadedTypes.includes(type))

    if (missingTypes.length > 0) {
      player.missingMaterials = true
      player.missingCount = missingTypes.length
      player.missingTypes = missingTypes
      pageMissing++
    } else {
      player.missingMaterials = false
      player.missingCount = 0
      player.missingTypes = []
    }
  }

  return pageMissing
}

const computeAllMissingCount = () => {
  const allP = dataService.getData('players') || []
  const config = dataService.getData('config') || {}
  const stageMaterials = config.stageMaterials || {}
  const materialTypes = dataService.getData('materialTypes') || []

  let total = 0

  for (const player of allP) {
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
    const stageHistory = player.stageHistory
    const history = Array.isArray(stageHistory) ? stageHistory :
      (Array.isArray(player.history) ? player.history : [])
    const currentStageHistory = history.find(h => h.stage === currentStage)
    if (currentStageHistory && currentStageHistory.materials) {
      uploadedTypes = currentStageHistory.materials.map(m => m.type)
    } else if (player.materials && player.materials.length > 0) {
      uploadedTypes = player.materials.map(m => m.type)
    }

    const missingTypes = applicableTypes.filter(type => !uploadedTypes.includes(type))
    if (missingTypes.length > 0) total++
  }

  return total
}

const filteredAllPlayers = computed(() => {
  let result = allPlayers.value

  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(p => p.name && p.name.toLowerCase().includes(keyword))
  }

  if (filterCategory.value !== 'all') {
    result = result.filter(p => p.category === filterCategory.value)
  }

  return result.sort((a, b) => {
    if (a.missingMaterials && !b.missingMaterials) return -1
    if (!a.missingMaterials && b.missingMaterials) return 1
    return 0
  })
})

const totalCount = computed(() => filteredAllPlayers.value.length)

const filteredPlayers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredAllPlayers.value.slice(start, end)
})

const loadPlayers = async () => {
  loading.value = true
  try {
    const result = await get('/api/players/list')

    if (result.success) {
      allPlayers.value = result.data

      await computeMissingMaterials(allPlayers.value)
      missingMaterialsTotal.value = computeAllMissingCount()
    }
  } catch (e) {
    console.error('加载选手失败:', e)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
}

const handlePageSizeChange = (newPageSize) => {
  pageSize.value = newPageSize
  currentPage.value = 1
}

onMounted(async () => {
  await loadPlayers()
  await projectStore.loadProjects()
  await orgStore.loadOrganizations()
})

onActivated(async () => {
  await loadPlayers()
})

watch(searchKeyword, () => {
  currentPage.value = 1
})

watch(filterCategory, () => {
  currentPage.value = 1
})

const missingMaterialsTotal = ref(0)

const getProjectName = (player) => {
  const project = projectStore.getProjectById(player.projectId)
  return project?.name || '-'
}

const getOrgName = (player) => {
  const org = orgStore.getOrgById(player.orgId)
  return org?.name || '-'
}

const downloadTemplate = () => {
  const headers = '姓名,性别,艺术类别,专业等级,联系电话,身份证,所属项目,所属机构,当前阶段,备注'
  const blob = new Blob([`\uFEFF${headers}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '选手导入模板.csv'
  a.click()
  URL.revokeObjectURL(url)
  importStep.value = 2
}

const handleImportFileSelect = (e) => {
  importFile.value = e.target.files[0]
}

const previewImport = () => {
  if (!importFile.value) return
  const reader = new FileReader()
  reader.onload = (e) => {
    const text = e.target.result
    const lines = text.trim().split('\n')
    if (lines.length < 2) return
    importHeaders.value = lines[0].split(',').map(h => h.trim())
    importPreview.value = []
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',').map(v => v.trim())
      const row = {}
      importHeaders.value.forEach((h, j) => {
        row[h] = values[j] || ''
      })
      importPreview.value.push(row)
    }
    importStep.value = 3
  }
  reader.readAsText(importFile.value, 'utf-8')
}

const executeImport = async () => {
  try {
    const response = await fetchWithAuth('/api/import-players', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ players: importPreview.value })
    })
    const result = await response.json()
    importResult.value = result
    importStep.value = 4
    if (result.success && result.imported > 0) {
      await playerStore.loadPlayers()
    }
  } catch (e) {
    console.error('导入失败:', e)
    importResult.value = { imported: 0, failed: importPreview.value.length, errors: [e.message] }
    importStep.value = 4
  }
}

const closeImportModal = () => {
  showImportModal.value = false
  importStep.value = 1
  importFile.value = null
  importPreview.value = []
  importHeaders.value = []
  importResult.value = { imported: 0, failed: 0, errors: [] }
  if (importFileInput.value) importFileInput.value.value = ''
}

const isAllSelected = computed(() => {
  const pageIds = filteredPlayers.value.map(p => p.id)
  return pageIds.length > 0 && pageIds.every(id => selectedIds.value.has(id))
})

const toggleSelect = (id) => {
  const newSet = new Set(selectedIds.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  selectedIds.value = newSet
}

const toggleSelectAll = () => {
  const pageIds = filteredPlayers.value.map(p => p.id)
  const newSet = new Set(selectedIds.value)
  if (isAllSelected.value) {
    pageIds.forEach(id => newSet.delete(id))
  } else {
    pageIds.forEach(id => newSet.add(id))
  }
  selectedIds.value = newSet
}

const clearSelection = () => {
  selectedIds.value = new Set()
}

const batchDelete = async () => {
  const count = selectedIds.value.size
  if (!confirm(`确定要删除选中的 ${count} 位选手吗？此操作不可撤销。`)) return
  for (const id of selectedIds.value) {
    await playerStore.deletePlayer(id)
  }
  selectedIds.value = new Set()
}
</script>

<style scoped>
.players-page {
  padding: 24px;
  max-width: 900px;
  width: 100%;
  margin: 0;
}

.page-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
}

.search-input {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
}

.filter-select {
  padding: 10px 16px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  min-width: 140px;
}

.player-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.player-card {
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: all 0.2s;
}

.player-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.player-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.player-name {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.player-gender {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  background: var(--bg-secondary, #f5f5f5);
  color: var(--text-secondary, #666);
  font-weight: 500;
}

.gender-男 {
  background: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.gender-女 {
  background: #fff1f0;
  color: #ff4d4f;
  border: 1px solid #ffa39e;
}

.player-card-body {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.player-category, .player-level {
  font-size: 14px;
  color: var(--text-secondary, #666);
}

.player-card-footer {
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #eee);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.player-meta {
  font-size: 12px;
  color: var(--text-secondary, #999);
  flex: 1;
}

.missing-badge {
  background: #ff4d4f;
  color: #fff;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
  margin-left: 8px;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-secondary, #999);
  font-size: 14px;
  background: var(--bg-primary, #fff);
  border-radius: 12px;
}

.missing-materials-alert {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}

.alert-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.alert-icon {
  font-size: 16px;
}

.alert-text {
  font-size: 14px;
  color: #ad6800;
}

.player-card.missing-materials {
  border-left: 3px solid #faad14;
}

.missing-materials-alert {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(245, 158, 11, 0.05) 100%);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: var(--radius-md, 8px);
  padding: 12px 16px;
  margin-bottom: 16px;
}

.alert-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.alert-icon {
  font-size: 18px;
}

.alert-text {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.header-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-secondary);
  border-radius: 12px;
  width: 90%;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-secondary);
}

.modal-body {
  padding: 20px;
}

.preview-table-wrap {
  overflow-x: auto;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.preview-table th,
.preview-table td {
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  text-align: left;
  white-space: nowrap;
}

.preview-table th {
  background: var(--bg-tertiary);
  font-weight: 600;
}

[data-theme="dark"] .gender-男 { background: rgba(96, 165, 250, 0.15); color: #60a5fa; border-color: rgba(96, 165, 250, 0.3); }
[data-theme="dark"] .gender-女 { background: rgba(248, 113, 113, 0.15); color: #f87171; border-color: rgba(248, 113, 113, 0.3); }
[data-theme="dark"] .missing-badge { background: var(--danger); }
[data-theme="dark"] .missing-materials-alert { background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); }
[data-theme="dark"] .alert-text { color: var(--text-primary); }
[data-theme="dark"] .player-card.missing-materials { border-left-color: var(--warning); }

.player-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.card-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--accent);
  flex-shrink: 0;
}

.player-card.selected {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.batch-actions {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--accent);
  color: white;
  padding: 12px 24px;
  border-radius: 12px;
  box-shadow: var(--shadow-lg, 0 8px 24px rgba(0, 0, 0, 0.2));
  display: flex;
  align-items: center;
  gap: 16px;
  z-index: 100;
}

.batch-actions button {
  padding: 6px 16px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.3);
  background: rgba(255,255,255,0.15);
  color: white;
  cursor: pointer;
  font-size: 14px;
}

.batch-actions button:hover {
  background: rgba(255,255,255,0.25);
}

.batch-actions button.danger {
  background: var(--danger, #ff4d4f);
  border-color: var(--danger, #ff4d4f);
}
</style>
