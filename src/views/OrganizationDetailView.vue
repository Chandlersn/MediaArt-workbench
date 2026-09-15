<template>
  <div class="organization-detail-page">
    <div class="page-header">
      <h2>{{ org?.name || '机构详情' }}</h2>
      <button class="btn-secondary" @click="$router.push('/organizations')">
        返回列表
      </button>
    </div>

    <div v-if="!org" class="empty-state">
      机构不存在或已删除
    </div>

    <div v-else class="detail-content">
      <div class="detail-section">
        <h3>基本信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">机构名称</span>
            <span class="detail-value">{{ org.name }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">机构类型</span>
            <span class="detail-value">{{ org.type || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">合作等级</span>
            <span class="detail-value">{{ org.level || '待评估' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">联系人</span>
            <span class="detail-value">{{ org.contact || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">联系电话</span>
            <span class="detail-value">{{ org.phone || '-' }}</span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>其他信息</h3>
        <div class="detail-grid">
          <div class="detail-item full-width">
            <span class="detail-label">机构地址</span>
            <span class="detail-value">{{ org.address || '-' }}</span>
          </div>
        </div>
        <div class="detail-item" style="margin-top: 16px;">
          <span class="detail-label">备注</span>
          <div class="detail-desc">{{ org.note || '暂无备注' }}</div>
        </div>
      </div>

      <div class="detail-section">
        <h3>机构资料</h3>
        <div class="material-upload-section">
          <div class="upload-header">
            <span>资料上传</span>
            <CustomSelect
              v-model="materialType"
              placeholder="选择资料类型"
              :options="orgMaterialTypes.map(mt => ({ value: mt.name, label: mt.name }))"
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
          <div class="material-list">
            <div v-if="!org.materials || org.materials.length === 0" class="empty-state">
              暂无机构资料
            </div>
            <div
              v-for="(material, index) in org.materials"
              :key="index"
              class="material-item"
            >
              <div class="material-info">
                <span class="material-type">{{ material.type }}</span>
                <span class="material-name">{{ material.name }}</span>
                <span class="material-date">{{ material.uploadDate }}</span>
              </div>
              <div class="material-actions">
                <button class="btn-sm btn-preview" @click="previewMaterial(material)" title="预览资料">预览</button>
                <button class="btn-sm btn-danger" @click="deleteMaterial(index)" title="删除资料">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

    <!-- 文件预览：统一由 FilePreviewPanel 组件承担加载与鉴权 -->
    <FilePreviewPanel
      v-model="showPreview"
      source="org"
      :owner-name="org?.name || ''"
      :file-name="previewTarget.fileName"
      :material-type="previewTarget.materialType"
    />

      <div class="detail-section">
        <h3>关联证书</h3>
        <div v-if="orgCertStats.total > 0" class="cert-metrics">
          <button type="button" class="cert-metric" title="在证书管理中查看本机构全部证书" @click="goCerts()">
            <span class="num">{{ orgCertStats.total }}</span>
            <span class="lbl">证书总数</span>
          </button>
          <button
            type="button"
            class="cert-metric"
            v-for="a in orgCertStats.byAward"
            :key="a.award"
            :title="`在证书管理中查看「${a.award}」`"
            @click="goCerts({ award: a.award })"
          >
            <span class="num">{{ a.count }}</span>
            <span class="lbl">{{ a.award }}</span>
          </button>
          <button
            type="button"
            class="cert-metric"
            title="在证书管理中查看缺作品名的证书"
            @click="goCerts({ missingWorkName: 1 })"
          >
            <span class="num">{{ orgCertStats.missingWorkName }}</span>
            <span class="lbl">缺作品名</span>
          </button>
        </div>
        <div v-else class="empty-state">该机构暂无关联证书（证书按「选送机构」名称匹配）</div>
      </div>

      <div class="detail-section">
        <div class="section-header-with-action">
          <h3>参赛选手</h3>
          <button class="btn-primary btn-sm" @click="$router.push('/players/new')">
            添加选手
          </button>
        </div>
        <div class="linked-list">
          <div v-if="orgPlayers.length === 0" class="empty-state">
            暂无参赛选手
          </div>
          <div
            v-for="player in orgPlayers"
            :key="player.id"
            class="linked-item"
            @click="$router.push(`/players/${player.id}`)"
          >
            <span class="linked-item-name">{{ player.name }}</span>
            <span class="linked-item-meta">{{ player.category || player.gender }}</span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>关联项目</h3>
        <div class="linked-list">
          <div v-if="orgProjects.length === 0" class="empty-state">
            暂无关联项目
          </div>
          <div
            v-for="project in orgProjects"
            :key="project.id"
            class="linked-item"
            @click="router.push(`/projects/${project.id}`)"
          >
            <span class="linked-item-name">{{ project.name }}</span>
            <span class="status-badge" :class="'status-' + (project.status || '筹备中')">
              {{ project.status || '筹备中' }}
            </span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>操作</h3>
        <div class="detail-actions">
          <button class="btn-primary" @click="$router.push(`/organizations/${org.id}/edit`)">
            编辑机构
          </button>
          <button class="btn-danger" @click="confirmDelete">
            删除机构
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, onActivated, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useOrganizationStore, usePlayerStore, useProjectStore } from '../stores'
import { useCertificateStore } from '../stores/certificate'
import { get, fetchWithAuth } from '../services/http.js'
import { parseOrgIds } from '../utils/dataHelpers'
import CustomSelect from '../components/CustomSelect.vue'
import FilePreviewPanel from '../components/FilePreviewPanel.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
const { success, error, warning } = useToast()
const { confirm } = useConfirmDialog()

const route = useRoute()
const router = useRouter()
const orgStore = useOrganizationStore()
const playerStore = usePlayerStore()
const projectStore = useProjectStore()
const certStore = useCertificateStore()

const org = computed(() => orgStore.getOrgById(route.params.id))

const orgPlayers = computed(() => {
  if (!org.value) return []
  return playerStore.players.filter(p => p.orgId === org.value.id)
})

const orgProjects = computed(() => {
  if (!org.value) return []
  return projectStore.projects.filter(p => parseOrgIds(p.orgIds).includes(org.value.id))
})

const orgCertStats = computed(() => certStore.getCertStats({ orgId: org.value?.id, orgName: org.value?.name }))

// 「关联证书」各指标可点击 → 跳证书管理，并按本机构（+奖项/缺作品名）预置筛选
const goCerts = (extra = {}) => {
  const query = { orgId: org.value?.id || '', orgName: org.value?.name || '' }
  if (extra.award) query.award = extra.award
  if (extra.missingWorkName) query.missingWorkName = '1'
  router.push({ path: '/certificates', query })
}

// 机构资料相关
const materialType = ref('')
const uploadTitle = ref('')
const selectedFile = ref(null)
const materialFileInput = ref(null)
const orgMaterialTypes = ref([])

// 加载机构资料类型
const loadOrgMaterialTypes = async () => {
  try {
    const result = await get('/api/data/load')

    if (result.data && result.data.archiveConfig && result.data.archiveConfig.organizations && result.data.archiveConfig.organizations.materialTypes) {
      const types = result.data.archiveConfig.organizations.materialTypes
      orgMaterialTypes.value = types.map((item, index) => ({
        id: item.id || `omt${index + 1}`,
        name: item.name || item,
        icon: item.icon || '📄'
      }))
    } else {
      orgMaterialTypes.value = []
    }
  } catch (e) {
    console.error('加载机构资料类型失败:', e)
    orgMaterialTypes.value = []
  }
}

// 加载机构资料
const loadOrgMaterials = async () => {
  if (!org.value) return

  try {
    const result = await get(`/api/scan-org-files?name=${encodeURIComponent(org.value.name)}`)

    if (result.materials) {
      orgStore.updateOrganization(org.value.id, {
        materials: result.materials.map(m => ({
          type: m.type,
          name: m.name,
          uploadDate: m.upload_date || new Date().toISOString()
        }))
      })
    } else {
      orgStore.updateOrganization(org.value.id, { materials: [] })
    }
  } catch (e) {
    console.error('加载机构资料失败:', e)
    if (org.value) {
      orgStore.updateOrganization(org.value.id, { materials: [] })
    }
  }
}

onMounted(() => {
  orgStore.loadOrganizations()
  playerStore.loadPlayers()
  projectStore.loadProjects()
  loadOrgMaterialTypes()
  loadOrgMaterials()
  certStore.loadCertificates()
})

onActivated(() => {
  orgStore.loadOrganizations()
  playerStore.loadPlayers()
  projectStore.loadProjects()
  loadOrgMaterials()
  certStore.loadCertificates()
})

watch(
  () => route.params.id,
  (newId, oldId) => {
    if (newId !== oldId) {
      orgStore.loadOrganizations()
      playerStore.loadPlayers()
      projectStore.loadProjects()
      loadOrgMaterialTypes()
      loadOrgMaterials()
      certStore.loadCertificates()
    }
  }
)

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
  formData.append('orgName', org.value.name)
  formData.append('materialType', materialType.value)

  try {
    const response = await fetchWithAuth('/api/upload', {
      method: 'POST',
      body: formData
    })
    const result = await response.json()

    if (result.success || result.message?.includes('uploaded successfully')) {
      success('资料上传成功')
      // 重新加载资料
      loadOrgMaterials()
      // 清空选择
      materialType.value = ''
      uploadTitle.value = ''
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

const deleteMaterial = async (index) => {
  const confirmed = await confirm({
    title: '删除确认',
    message: '确定要删除这个资料吗？',
    type: 'warning'
  })

  if (!confirmed) return

  const material = org.value.materials[index]
  try {
    const response = await fetchWithAuth('/api/delete-org-material', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        orgName: org.value.name,
        fileName: material.name,
        materialType: material.type
      })
    })
    const result = await response.json()

    if (result.success) {
      success('删除成功')
      loadOrgMaterials()
    } else {
      error(`删除失败：${result.message}`)
    }
  } catch (e) {
    console.error('删除失败:', e)
    error('删除失败，请重试')
  }
}

const confirmDelete = async () => {
  const confirmed = await confirm({
    title: '删除确认',
    message: `确定要删除机构"${org.value.name}"吗？此操作不可恢复。`,
    type: 'danger'
  })

  if (confirmed) {
    await orgStore.deleteOrganization(org.value.id)
    success('删除成功')
    router.push('/organizations')
  }
}
</script>

<style scoped>
.title-input {
  flex: 1 1 170px;
  min-width: 120px;
  padding: 6px 10px;
  border: 1px solid var(--line, #d8cfc0);
  border-radius: 6px;
  background: var(--paper, #fbf8f1);
  color: var(--ink, #2b2b2b);
  font-size: 13px;
}
.title-input:focus {
  outline: none;
  border-color: var(--cinnabar, #b03a2e);
}
.organization-detail-page {
  padding: 24px;
}

.detail-content {
  max-width: 900px;
  width: 100%;
  margin: 0;
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

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
  color: var(--text-primary, #333);
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
  color: var(--text-secondary, #999);
  text-transform: uppercase;
}

.detail-value { font-size: 14px; color: var(--text-primary, #333); }

.detail-desc {
  font-size: 14px;
  color: var(--text-primary, #333);
  line-height: 1.6;
  white-space: pre-wrap;
}

.linked-list { display: flex; flex-direction: column; gap: 8px; }

.linked-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary, #f5f5f5);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.linked-item:hover { background: var(--bg-hover, #e8e8e8); }

.linked-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #333);
}

.linked-item-meta { font-size: 12px; color: var(--text-secondary, #999); }

.detail-actions { display: flex; gap: 12px; }

.empty-state {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-secondary, #999);
  font-size: 14px;
}

.material-upload-section {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
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

.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.status-筹备中 { background: #e6f7ff; color: #1890ff; }
.status-进行中 { background: #e6fffb; color: #13c2c2; }
.status-已结束 { background: #f5f5f5; color: #999; }
.status-已归档 { background: #f6ffed; color: #52c41a; }

[data-theme="dark"] .status-筹备中 { background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); }
[data-theme="dark"] .status-进行中 { background: rgba(45, 212, 191, 0.15); color: #2dd4bf; border: 1px solid rgba(45, 212, 191, 0.3); }
[data-theme="dark"] .status-已结束 { background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); }
[data-theme="dark"] .status-已归档 { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }

.btn-preview {
  background: var(--accent, #3b82f6);
  color: white;
}

.btn-preview:hover {
  background: var(--accent-hover, #2563eb);
}

.cert-metrics { display: flex; flex-wrap: wrap; gap: 16px; }
.cert-metric { display: flex; flex-direction: column; align-items: center; min-width: 88px; padding: 12px 16px; background: var(--bg-secondary); border: 1px solid transparent; border-radius: 8px; font: inherit; color: inherit; cursor: pointer; transition: all 0.15s; }
.cert-metric:hover { border-color: var(--accent); background: var(--bg-hover); }
.cert-metric .num { font-size: 22px; font-weight: 700; color: var(--cinnabar, #b0392b); }
.cert-metric .lbl { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
</style>
