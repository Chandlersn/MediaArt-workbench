<template>
  <div class="player-detail-page">
    <div class="page-header">
      <h2>{{ player?.name || '选手详情' }}</h2>
      <button class="btn-secondary" @click="$router.push('/players')">
        返回列表
      </button>
    </div>

    <div v-if="!player" class="empty-state">
      选手不存在或已删除
    </div>

    <div v-else class="detail-content">
      <div class="detail-section">
        <h3>基本信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">姓名</span>
            <span class="detail-value">{{ player.name }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">性别</span>
            <span class="detail-value">{{ player.gender || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">艺术类别</span>
            <span class="detail-value">{{ player.category || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">专业等级</span>
            <span class="detail-value">{{ player.level || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">所属项目</span>
            <span class="detail-value clickable" @click="goToProject">
              {{ getProjectName() }}
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">所属机构</span>
            <span class="detail-value clickable" @click="goToOrg">
              {{ getOrgName() }}
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">联系电话</span>
            <span class="detail-value">{{ player.phone || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">身份证</span>
            <span class="detail-value">{{ player.idCard || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">当前阶段</span>
            <span class="detail-value">
              <span v-if="player.stage" class="stage-badge">{{ player.stage }}</span>
              <span v-else>-</span>
            </span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>
          参赛资料
          <span v-if="missingMaterials && missingMaterials.length > 0" class="material-status-badge warning">
            缺失 {{ missingMaterials.length }} 项资料
          </span>
          <span v-else class="material-status-badge success">资料完整</span>
        </h3>
        <!-- 缺失资料提示 -->
        <div v-if="missingMaterials && missingMaterials.length > 0" class="missing-materials-alert">
          <div class="alert-header">
            <span class="alert-icon">⚠️</span>
            <span class="alert-title">待完善资料</span>
          </div>
          <div class="missing-materials-list">
            <span v-for="(mat, index) in missingMaterials" :key="index" class="missing-material-tag">
              {{ mat }}
            </span>
          </div>
        </div>
        <div class="material-upload-section">
          <div class="upload-header">
            <span>资料上传</span>
            <CustomSelect
              v-model="materialType"
              placeholder="选择资料类型"
              :options="materialTypes.map(mt => ({ value: mt.name, label: mt.name }))"
            />
            <CustomSelect
              v-model="uploadStage"
              placeholder="选择阶段"
              :options="stageOptions.map(s => ({ value: s, label: s }))"
            />
            <input
              type="file"
              ref="materialFileInput"
              style="display: none;"
              accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.gif,.mp4,.avi,.mov"
              @change="handleFileSelect"
            />
            <button class="btn-secondary" @click="triggerFileSelect">选择文件</button>
            <button class="btn-primary" @click="uploadMaterial" :disabled="!selectedFile || !materialType">
              上传
            </button>
          </div>
          <div v-if="!player.materials || player.materials.length === 0" class="empty-state">
            暂无参赛资料
          </div>
          <div v-else class="stage-groups">
            <div
              v-for="(materials, stage) in materialsByStage"
              :key="stage"
              class="stage-group"
            >
              <div
                class="stage-group-header"
                :class="{ active: expandedStages[stage] }"
                @click="expandedStages[stage] = !expandedStages[stage]"
              >
                <span class="stage-group-name">{{ stage }}</span>
                <span class="stage-group-count">{{ materials.length }} 项</span>
                <span class="stage-group-toggle">{{ expandedStages[stage] ? '▼' : '▶' }}</span>
              </div>
              <div v-if="expandedStages[stage]" class="stage-group-content">
                <div
                  v-for="(material, mIndex) in materials"
                  :key="mIndex"
                  class="material-item"
                >
                  <div class="material-info">
                    <span class="material-type">{{ material.type }}</span>
                    <span class="material-name">{{ material.name }}</span>
                    <span class="material-date">{{ material.uploadDate }}</span>
                  </div>
                  <div class="material-actions">
                    <button class="btn-sm" @click="previewMaterial(material)">预览</button>
                    <button class="btn-sm" @click="downloadMaterial(material)">下载</button>
                    <button class="btn-sm btn-danger" @click="deleteMaterial(material)">删除</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <div class="section-header-with-action">
          <h3>赛事历程</h3>
          <button class="btn-primary btn-sm" @click="showAdvanceModal = true">
            晋级记录
          </button>
        </div>
        <div class="linked-list">
          <div v-if="!player.history || player.history.length === 0" class="empty-state">
            暂无赛事记录
          </div>
          <div
            v-for="(record, index) in (player.history || player.stageHistory || [])"
            :key="index"
            class="linked-item"
          >
            <div class="history-item">
              <span class="history-stage">{{ record.stage }}</span>
              <span class="history-result" :class="record.result">{{ record.result }}</span>
              <span class="history-date">{{ record.date }}</span>
            </div>
            <div v-if="record.note" class="history-note">{{ record.note }}</div>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>操作</h3>
        <div class="detail-actions">
          <button class="btn-primary" @click="$router.push(`/players/${player.id}/edit`)">
            编辑选手
          </button>
          <button class="btn-secondary" @click="showAdvanceModal = true">
            晋级下一阶段
          </button>
          <button class="btn-danger" @click="confirmDelete">
            删除选手
          </button>
        </div>
      </div>
    </div>

    <!-- 文件预览：统一由 FilePreviewPanel 组件承担加载与鉴权 -->
    <FilePreviewPanel
      v-model="showPreview"
      source="player"
      :owner-name="player?.name || ''"
      :file-name="previewTarget.fileName"
      :material-type="previewTarget.materialType"
    />

    <!-- 晋级模态框 -->
    <div v-if="showAdvanceModal" class="modal-overlay active" @click.self="showAdvanceModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>晋级下一阶段</h3>
          <button class="modal-close" @click="showAdvanceModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>阶段名称 <span class="required">*</span></label>
            <CustomSelect v-model="advanceForm.stage" style="width:100%">
              <option value="">请选择阶段</option>
              <option value="初赛">初赛</option>
              <option value="市赛">市赛</option>
              <option value="省赛">省赛</option>
              <option value="决赛">决赛</option>
              <option value="__custom__">自定义...</option>
            </CustomSelect>
            <input v-if="advanceForm.stage === '__custom__'" type="text" v-model="advanceForm.customStage" class="form-input" style="margin-top: 8px;" placeholder="请输入自定义阶段名称" />
          </div>
          <div class="form-group">
            <label>比赛结果</label>
            <CustomSelect v-model="advanceForm.result" style="width:100%">
              <option value="">请选择结果</option>
              <option value="晋级">晋级</option>
              <option value="获奖">获奖</option>
              <option value="淘汰">淘汰</option>
              <option value="__custom__">自定义...</option>
            </CustomSelect>
            <input v-if="advanceForm.result === '__custom__'" type="text" v-model="advanceForm.customResult" class="form-input" style="margin-top: 8px;" placeholder="请输入自定义结果" />
          </div>
          <div class="form-group">
            <label>备注</label>
            <textarea v-model="advanceForm.note" class="form-input" rows="3" placeholder="请输入备注"></textarea>
          </div>
          <div class="form-actions">
            <button class="btn-secondary" @click="showAdvanceModal = false">取消</button>
            <button class="btn-primary" @click="advancePlayer">确定</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, reactive, onActivated, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerStore, useProjectStore, useOrganizationStore } from '../stores'
import { get, fetchWithAuth } from '../services/http.js'
import * as dataService from '../services/dataService.js'
import CustomSelect from '../components/CustomSelect.vue'
import FilePreviewPanel from '../components/FilePreviewPanel.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
const { success, error, warning } = useToast()
const { confirm } = useConfirmDialog()

const route = useRoute()
const router = useRouter()
const playerStore = usePlayerStore()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()

const showAdvanceModal = ref(false)
const advanceForm = ref({
  stage: '',
  customStage: '',
  result: '',
  customResult: '',
  note: ''
})

const materialType = ref('')
const uploadStage = ref('')
const selectedFile = ref(null)
const materialFileInput = ref(null)
const materialTypes = ref([])
const expandedStages = reactive({})

const stageOptions = ['初赛', '市赛', '省赛', '国赛', '决赛']

const player = computed(() => playerStore.getPlayerById(route.params.id))

const materialsByStage = computed(() => {
  if (!player.value?.materials) return {}
  const stages = {}
  const stageOrder = [...stageOptions]

  for (const mat of player.value.materials) {
    const stage = mat.stage || '通用资料'
    if (!stages[stage]) stages[stage] = []
    stages[stage].push(mat)
  }

  const ordered = {}
  for (const s of stageOrder) {
    if (stages[s]) ordered[s] = stages[s]
  }
  for (const s of Object.keys(stages)) {
    if (!stageOrder.includes(s) && s !== '通用资料') ordered[s] = stages[s]
  }
  if (stages['通用资料']) ordered['通用资料'] = stages['通用资料']

  return ordered
})

// 缺失资料检测
const missingMaterials = computed(() => {
  if (!player.value) return []

  const config = dataService.getData('config') || {}
  const stageMaterials = config.stageMaterials || {}
  const materialTypes = dataService.getData('materialTypes') || []

  const currentStage = player.value.stage
  const requiredTypes = stageMaterials[currentStage] || []

  if (requiredTypes.length === 0) return []

  const applicableTypes = requiredTypes.filter(typeName => {
    const mt = materialTypes.find(t => t.name === typeName)
    if (!mt) return true
    if (!mt.orgId) return true
    return mt.orgId === player.value.orgId
  })

  if (applicableTypes.length === 0) return []

  let uploadedTypes = []

  if (player.value.missingTypes && player.value.missingTypes.length > 0) {
    return player.value.missingTypes
  }

  const stageHistory = player.value.stageHistory
  const history = Array.isArray(stageHistory) ? stageHistory :
    (Array.isArray(player.value.history) ? player.value.history : [])
  const currentStageHistory = history.find(h => h.stage === currentStage)
  if (currentStageHistory && currentStageHistory.materials) {
    uploadedTypes = currentStageHistory.materials.map(m => m.type)
  } else if (player.value.materials && player.value.materials.length > 0) {
    uploadedTypes = player.value.materials.map(m => m.type)
  }

  return applicableTypes.filter(type => !uploadedTypes.includes(type))
})

// 加载资料类型配置
const loadMaterialTypes = async () => {
  try {
    const result = await get('/api/data/load')

    if (result.data && result.data.materialTypes && result.data.materialTypes.length > 0) {
      materialTypes.value = result.data.materialTypes
    } else {
      materialTypes.value = []
    }
  } catch (e) {
    console.error('加载资料类型失败:', e)
    materialTypes.value = []
  }
}

// 加载选手的资料信息
const loadPlayerMaterials = async () => {
  if (!player.value) return

  try {
    const result = await get(`/api/scan-player-files?name=${encodeURIComponent(player.value.name)}`)

    if (result.materials) {
      player.value.materials = result.materials.map(m => ({
        type: m.type,
        name: m.file_name,
        uploadDate: m.upload_date || new Date().toISOString(),
        stage: m.stage || ''
      }))
    } else {
      player.value.materials = []
    }

    for (const stage of Object.keys(materialsByStage.value)) {
      if (expandedStages[stage] === undefined) {
        expandedStages[stage] = (stage === player.value.stage)
      }
    }
  } catch (e) {
    console.error('加载选手资料失败:', e)
    player.value.materials = []
  }
}

onMounted(() => {
  playerStore.loadPlayers()
  projectStore.loadProjects()
  orgStore.loadOrganizations()
  loadMaterialTypes()
  loadPlayerMaterials()
})

onActivated(() => {
  playerStore.loadPlayers()
  projectStore.loadProjects()
  orgStore.loadOrganizations()
  loadPlayerMaterials()
})

watch(
  () => route.params.id,
  (newId, oldId) => {
    if (newId !== oldId) {
      playerStore.loadPlayers()
      projectStore.loadProjects()
      orgStore.loadOrganizations()
      loadMaterialTypes()
      loadPlayerMaterials()
    }
  }
)

const getProjectName = () => {
  if (!player.value?.projectId) return '-'
  const project = projectStore.getProjectById(player.value.projectId)
  return project?.name || '-'
}

const getOrgName = () => {
  if (!player.value?.orgId) return '-'
  const org = orgStore.getOrgById(player.value.orgId)
  return org?.name || '-'
}

const goToProject = () => {
  if (player.value?.projectId) {
    router.push(`/projects/${player.value.projectId}`)
  }
}

const goToOrg = () => {
  if (player.value?.orgId) {
    router.push(`/organizations/${player.value.orgId}`)
  }
}

const advancePlayer = async () => {
  if (!advanceForm.value.stage) {
    warning('请选择阶段名称')
    return
  }

  const stage = advanceForm.value.stage === '__custom__' ? advanceForm.value.customStage : advanceForm.value.stage
  const result = advanceForm.value.result === '__custom__' ? advanceForm.value.customResult : advanceForm.value.result

  // 兼容 history 和 stageHistory 两种字段
  const history = player.value.history || player.value.stageHistory || []
  history.push({
    stage,
    result: result || '晋级',
    note: advanceForm.value.note,
    date: new Date().toISOString().split('T')[0]
  })

  // 同时更新选手的当前阶段
  await playerStore.updatePlayer(player.value.id, {
    history,
    stage
  })
  showAdvanceModal.value = false
  advanceForm.value = { stage: '', customStage: '', result: '', customResult: '', note: '' }
  await playerStore.loadPlayers()
  success('晋级记录已保存')
}

const confirmDelete = async () => {
  const confirmed = await confirm({
    title: '删除确认',
    message: `确定要删除选手"${player.value.name}"吗？此操作不可恢复。`,
    type: 'danger'
  })

  if (confirmed) {
    await playerStore.deletePlayer(player.value.id)
    success('删除成功')
    router.push('/players')
  }
}

// 资料上传相关函数
const triggerFileSelect = () => {
  materialFileInput.value?.click()
}

const handleFileSelect = (event) => {
  const file = event.target.files[0]
  if (file) {
    selectedFile.value = file
  }
}

const uploadMaterial = async () => {
  if (!materialType.value) {
    warning('请选择资料类型')
    return
  }
  if (!selectedFile.value) {
    warning('请选择文件')
    return
  }

  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('playerName', player.value.name)
  formData.append('materialType', materialType.value)
  if (uploadStage.value) {
    formData.append('stage', uploadStage.value)
  }

  try {
    // fetchWithAuth 返回的是 Response，必须 json() 后才能取 success/message，
    // 否则恒为 undefined、成功也会被判成失败（此处曾漏写 .json()）。
    const response = await fetchWithAuth('/api/upload', {
      method: 'POST',
      body: formData
    })
    const result = await response.json()

    if (result.success || result.message?.includes('uploaded successfully')) {
      success('资料上传成功')
      // 刷新选手数据和资料
      await playerStore.loadPlayers()
      await loadPlayerMaterials()
      // 重新计算缺失资料
      await playerStore.calculateMissingMaterials()
      // 展开上传阶段
      const stage = uploadStage.value || player.value.stage || '通用资料'
      expandedStages[stage] = true
      // 清空选择
      materialType.value = ''
      uploadStage.value = ''
      selectedFile.value = null
      if (materialFileInput.value) {
        materialFileInput.value.value = ''
      }
    } else {
      error(`上传失败：${result.message || '未知错误'}`)
    }
  } catch (e) {
    console.error('上传失败:', e)
    error('上传失败，请重试')
  }
}

const downloadMaterial = async (material) => {
  try {
    const url = `/api/download-player-material?playerName=${encodeURIComponent(player.value.name)}&fileName=${encodeURIComponent(material.name)}`
    const blob = await getBlob(url)
    const objUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objUrl
    link.download = material.name
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(objUrl)
  } catch (e) {
    console.error('下载资料失败:', e)
    error(e?.message || '下载失败，请重试')
  }
}

// 文件预览：媒体加载、鉴权与文本提取统一交给 FilePreviewPanel 组件
const showPreview = ref(false)
const previewTarget = ref({ fileName: '', materialType: '' })

const previewMaterial = (material) => {
  previewTarget.value = {
    fileName: material.name,
    materialType: material.type || material.materialType || ''
  }
  showPreview.value = true
}

// 删除选手资料：后端 /api/delete-player-material 已提供
const deleteMaterial = async (index) => {
  const confirmed = await confirm({
    title: '删除确认',
    message: '确定要删除这个资料吗？',
    type: 'warning'
  })

  if (!confirmed) return

  const material = player.value.materials[index]
  try {
    const response = await fetchWithAuth('/api/delete-player-material', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        playerName: player.value.name,
        fileName: material.name
      })
    })
    const result = await response.json()

    if (result.success) {
      success('删除成功')
      await playerStore.loadPlayers()
      loadPlayerMaterials()
      await playerStore.calculateMissingMaterials()
    } else {
      error(`删除失败：${result.message}`)
    }
  } catch (e) {
    console.error('删除失败:', e)
    error('删除失败，请重试')
  }
}
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.detail-content {
  max-width: 900px;
  width: 100%;
  margin: 0;
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.detail-section { margin-bottom: 32px; }

.detail-section:last-child { margin-bottom: 0; }

.detail-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-light);
}

.section-header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header-with-action h3 {
  margin: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.detail-item { display: flex; flex-direction: column; gap: 4px; }

.full-width { grid-column: 1 / -1; }

.detail-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.detail-value { font-size: 14px; color: var(--text-primary); }

.player-detail-page {
  padding: 24px;
}

.clickable {
  color: var(--accent);
  cursor: pointer;
}

.clickable:hover { text-decoration: underline; }

.material-upload-section {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
}

.stage-groups {
  margin-top: 12px;
}

.stage-group {
  margin-bottom: 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  overflow: hidden;
}

.stage-group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.stage-group-header:hover {
  background: var(--bg-hover);
}

.stage-group-header.active {
  border-bottom: 1px solid var(--border-color);
}

.stage-group-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.stage-group-count {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 2px 8px;
  border-radius: 10px;
}

.stage-group-toggle {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary);
}

.stage-group-content {
  padding: 8px 14px;
}

.upload-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.upload-header span {
  font-weight: 500;
  color: var(--text-primary);
}

.upload-select {
  max-width: 160px;
  min-width: 120px;
}

.upload-select-stage {
  max-width: 140px;
  min-width: 100px;
}

.upload-select:focus,
.upload-select-stage:focus {
  outline: none;
  border-color: var(--accent);
}

.material-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.material-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-light);
}

.material-info {
  display: flex;
  gap: 16px;
  align-items: center;
  min-width: 0;
  overflow: hidden;
}

.material-type {
  font-weight: 500;
  color: var(--accent);
  min-width: 80px;
}

.material-name {
  color: var(--text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.material-date {
  color: var(--text-secondary);
  font-size: 13px;
}

.material-actions {
  display: flex;
  gap: 8px;
}

.stage-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  background: #e6f7ff;
  color: #1890ff;
}

.material-status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  margin-left: 12px;
}

.material-status-badge.warning {
  background: #fffbe6;
  color: #faad14;
}

.material-status-badge.success {
  background: #f6ffed;
  color: #52c41a;
}

.missing-materials-alert {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.alert-icon {
  font-size: 16px;
}

.alert-title {
  font-weight: 500;
  color: #faad14;
}

.missing-materials-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.missing-material-tag {
  background: #fff;
  border: 1px solid #ffe58f;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  color: #666;
}

.custom-fields-display {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.custom-field-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.custom-field-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.custom-field-value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.detail-desc {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.linked-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.linked-item {
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.linked-item:hover {
  background: var(--bg-hover);
}

.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.history-stage {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.history-result {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.history-result.晋级 {
  background: var(--success-light);
  color: var(--success);
}

.history-result.获奖 {
  background: var(--warning-light);
  color: var(--warning);
}

.history-result.淘汰 {
  background: var(--danger-light);
  color: var(--danger);
}

.history-date {
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: auto;
}

.history-note {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-light);
}

.detail-actions { display: flex; gap: 12px; flex-wrap: wrap; }

.empty-state {
  padding: 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
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
  max-width: 400px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
}

.modal-header h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
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

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.required {
  color: #ef4444;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  font-size: 14px;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-light);
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn-primary {
  padding: 10px 20px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-secondary {
  padding: 10px 20px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
}

.btn-danger {
  padding: 10px 20px;
  background: #ef4444;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-danger:hover {
  background: #dc2626;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}

[data-theme="dark"] .stage-badge { background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); }
[data-theme="dark"] .material-status-badge.warning { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }
[data-theme="dark"] .material-status-badge.success { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }
[data-theme="dark"] .missing-materials-alert { background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); }
[data-theme="dark"] .alert-title { color: var(--warning); }
[data-theme="dark"] .missing-material-tag { background: var(--bg-tertiary); border-color: rgba(251, 191, 36, 0.3); color: var(--text-secondary); }
[data-theme="dark"] .required { color: var(--danger); }
[data-theme="dark"] .btn-danger { background: var(--danger); }
[data-theme="dark"] .btn-danger:hover { background: #b91c1c; }

</style>
