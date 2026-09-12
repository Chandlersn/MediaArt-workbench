<template>
  <div class="project-detail-page">
    <div class="page-header">
      <h2>{{ project?.name || '项目详情' }}</h2>
      <button class="btn-secondary" @click="$router.push('/projects')">
        返回列表
      </button>
    </div>

    <div v-if="!project" class="empty-state">
      项目不存在或已删除
    </div>

    <div v-else class="detail-content">
      <div class="detail-section">
        <h3>基本信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">项目名称</span>
            <span class="detail-value">{{ project.name }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">项目类型</span>
            <span class="detail-value">{{ project.type || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">项目状态</span>
            <span class="detail-value">
              <span :class="['status-badge', 'status-' + project.status]">
                {{ project.status || '筹备中' }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">开始日期</span>
            <span class="detail-value">{{ project.startDate || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">结束日期</span>
            <span class="detail-value">{{ project.endDate || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">预算</span>
            <span class="detail-value">{{ project.budget ? `¥${project.budget}` : '-' }}</span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>项目描述</h3>
        <div class="detail-desc">{{ project.description || '暂无描述' }}</div>
      </div>

      <div class="detail-section">
        <h3>项目资料</h3>
        <div class="material-upload-section">
          <div class="upload-header">
            <span>资料上传</span>
            <CustomSelect
              v-model="materialType"
              placeholder="选择资料类型"
              :options="projectMaterialTypes.map(mt => ({ value: mt.name, label: mt.name }))"
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
            <div v-if="!project.materials || project.materials.length === 0" class="empty-state">
              暂无项目资料
            </div>
            <div
              v-for="(material, index) in project.materials"
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
                <button class="btn-sm" @click="downloadMaterial(material)" title="下载">下载</button>
                <button class="btn-sm btn-danger" @click="deleteMaterial(index)" title="删除">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

    <!-- 文件预览：统一由 FilePreviewPanel 组件承担加载与鉴权 -->
    <FilePreviewPanel
      v-model="showPreview"
      source="project"
      :owner-name="project?.name || ''"
      :file-name="previewTarget.fileName"
      :material-type="previewTarget.materialType"
    />

      <div class="detail-section">
        <h3>关联证书</h3>
        <div v-if="projectCertStats.total > 0" class="cert-metrics">
          <div class="cert-metric">
            <span class="num">{{ projectCertStats.total }}</span>
            <span class="lbl">证书总数</span>
          </div>
          <div class="cert-metric" v-for="a in projectCertStats.byAward" :key="a.award">
            <span class="num">{{ a.count }}</span>
            <span class="lbl">{{ a.award }}</span>
          </div>
          <div class="cert-metric">
            <span class="num">{{ projectCertStats.missingWorkName }}</span>
            <span class="lbl">缺作品名</span>
          </div>
        </div>
        <div v-else class="empty-state">该项目暂无关联证书，可在「证书管理」导入时选择归属本项目</div>
      </div>

      <div class="detail-section">
        <div class="section-header-with-action">
          <h3>关联机构</h3>
          <button class="btn-primary btn-sm" @click="showAddOrgModal = true">
            添加机构
          </button>
        </div>
        <div class="linked-list">
          <div v-if="projectOrgs.length === 0" class="empty-state">
            暂无关联机构
          </div>
          <div
            v-for="org in projectOrgs"
            :key="org.id"
            class="linked-item"
          >
            <div @click="$router.push(`/organizations/${org.id}`)">
              <span class="linked-item-name">{{ org.name }}</span>
              <span class="linked-item-meta">{{ org.type || '-' }}</span>
            </div>
            <button class="btn-sm btn-danger" @click.stop="removeOrgFromProject(org.id)">移除</button>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>操作</h3>
        <div class="detail-actions">
          <button class="btn-primary" @click="$router.push(`/projects/${project.id}/edit`)">
            编辑项目
          </button>
          <button class="btn-danger" @click="confirmDelete">
            删除项目
          </button>
        </div>
      </div>

      <!-- 添加机构模态框 -->
      <div v-if="showAddOrgModal" class="modal-overlay active" @click.self="showAddOrgModal = false">
        <div class="modal-content">
          <div class="modal-header">
            <h3>添加关联机构</h3>
            <button class="modal-close" @click="showAddOrgModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div v-if="availableOrgs.length === 0" class="empty-state">
              暂无可关联的机构
            </div>
            <div v-else class="org-select-list">
              <div
                v-for="org in availableOrgs"
                :key="org.id"
                class="org-select-item"
                @click="addOrgToProject(org.id)"
              >
                <span class="org-name">{{ org.name }}</span>
                <span class="org-type">{{ org.type || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, onActivated, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore, useOrganizationStore } from '../stores'
import { useCertificateStore } from '../stores/certificate'
import { get, fetchWithAuth, getBlob } from '../services/http.js'
import { parseOrgIds } from '../utils/dataHelpers'
import CustomSelect from '../components/CustomSelect.vue'
import FilePreviewPanel from '../components/FilePreviewPanel.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'

const { success, error, warning } = useToast()
const { confirm } = useConfirmDialog()

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()
const certStore = useCertificateStore()

const project = computed(() => projectStore.getProjectById(route.params.id))

const projectOrgs = computed(() => {
  if (!project.value) return []
  const orgIds = parseOrgIds(project.value.orgIds)
  return orgStore.organizations.filter(org => orgIds.includes(org.id))
})

const projectCertStats = computed(() => certStore.getCertStats({ projectId: project.value?.id }))

// 项目资料相关
const materialType = ref('')
const selectedFile = ref(null)
const materialFileInput = ref(null)
const projectMaterialTypes = ref([])
const showAddOrgModal = ref(false)
const availableOrgs = computed(() => {
  if (!project.value) return []
  const linkedOrgIds = projectOrgs.value.map(o => o.id)
  return orgStore.organizations.filter(org => !linkedOrgIds.includes(org.id))
})

// 加载项目资料类型
const loadProjectMaterialTypes = async () => {
  try {
    const result = await get('/api/data/load')

    if (result.data && result.data.archiveConfig && result.data.archiveConfig.projects && result.data.archiveConfig.projects.materialTypes) {
      const types = result.data.archiveConfig.projects.materialTypes
      projectMaterialTypes.value = types.map((item, index) => ({
        id: item.id || `pmt${index + 1}`,
        name: item.name || item,
        icon: item.icon || '📋'
      }))
    } else {
      projectMaterialTypes.value = []
    }
  } catch (e) {
    console.error('加载项目资料类型失败:', e)
    projectMaterialTypes.value = []
  }
}

// 加载项目资料
const loadProjectMaterials = async () => {
  if (!project.value) return

  try {
    const result = await get(`/api/scan-project-files?name=${encodeURIComponent(project.value.name)}`)

    if (result.materials) {
      projectStore.updateProject(project.value.id, {
        materials: result.materials.map(m => ({
          type: m.type,
          name: m.file_name,
          uploadDate: m.upload_date || new Date().toISOString()
        }))
      })
    }
  } catch (e) {
    console.error('加载项目资料失败:', e)
  }
}

onMounted(() => {
  projectStore.loadProjects()
  orgStore.loadOrganizations()
  loadProjectMaterialTypes()
  loadProjectMaterials()
  certStore.loadCertificates()
})

onActivated(() => {
  projectStore.loadProjects()
  orgStore.loadOrganizations()
  loadProjectMaterials()
  certStore.loadCertificates()
})

watch(
  () => route.params.id,
  (newId, oldId) => {
    if (newId !== oldId) {
      projectStore.loadProjects()
      orgStore.loadOrganizations()
      loadProjectMaterialTypes()
      loadProjectMaterials()
    }
  }
)

const confirmDelete = async () => {
  const confirmed = await confirm({
    title: '删除确认',
    message: `确定要删除项目"${project.value.name}"吗？此操作不可恢复。`,
    type: 'danger'
  })

  if (confirmed) {
    await projectStore.deleteProject(project.value.id)
    success('删除成功')
    router.push('/projects')
  }
}

const addOrgToProject = async (orgId) => {
  if (!project.value || !orgId) return

  const currentOrgIds = parseOrgIds(project.value.orgIds)
  if (!currentOrgIds.includes(orgId)) {
    currentOrgIds.push(orgId)
  }

  await projectStore.updateProject(project.value.id, { orgIds: currentOrgIds })
  await projectStore.loadProjects()
  await orgStore.loadOrganizations()
  success('机构关联成功')
  showAddOrgModal.value = false
}

const removeOrgFromProject = async (orgId) => {
  const confirmed = await confirm({
    title: '移除确认',
    message: '确定要移除该机构的关联吗？',
    type: 'warning'
  })

  if (!confirmed) return

  const currentOrgIds = parseOrgIds(project.value.orgIds).filter(id => id !== orgId)

  await projectStore.updateProject(project.value.id, { orgIds: currentOrgIds })
  await projectStore.loadProjects()
  await orgStore.loadOrganizations()
  success('机构已移除')
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
  formData.append('projectName', project.value.name)
  formData.append('materialType', materialType.value)

  try {
    const response = await fetchWithAuth('/api/upload', {
      method: 'POST',
      body: formData
    })
    const result = await response.json()

    if (result.success || result.message?.includes('uploaded successfully')) {
      success('资料上传成功')
      loadProjectMaterials()
      materialType.value = ''
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
    const url = `/api/download-project-material?projectName=${encodeURIComponent(project.value.name)}&fileName=${encodeURIComponent(material.name)}`
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

const deleteMaterial = async (index) => {
  const confirmed = await confirm({
    title: '删除确认',
    message: '确定要删除这个资料吗？',
    type: 'warning'
  })

  if (!confirmed) return

  const material = project.value.materials[index]
  try {
    const response = await fetchWithAuth('/api/delete-project-material', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectName: project.value.name,
        fileName: material.name
      })
    })
    const result = await response.json()

    if (result.success) {
      success('删除成功')
      loadProjectMaterials()
    } else {
      error(`删除失败：${result.message}`)
    }
  } catch (e) {
    console.error('删除失败:', e)
    error('删除失败，请重试')
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

</script>

<style scoped>
.project-detail-page {
  padding: 24px;
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
  gap: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-item.full-width { grid-column: 1 / -1; }

.detail-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-筹备中 { background: #e6f7ff; color: #1890ff; }
.status-进行中 { background: #e6fffb; color: #13c2c2; }
.status-已结束 { background: #f5f5f5; color: #999; }
.status-已归档 { background: #f6ffed; color: #52c41a; }

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
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  gap: 12px;
}

.linked-item > div {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.linked-item:hover { background: var(--bg-hover); }

.linked-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.linked-item-meta { font-size: 12px; color: var(--text-secondary); }

.linked-item .btn-sm {
  flex-shrink: 0;
}

.detail-actions { display: flex; gap: 12px; }

.empty-state {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-secondary);
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
  background: var(--bg-primary);
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0;
  line-height: 1;
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.org-select-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.org-select-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.org-select-item:hover {
  background: var(--accent-light);
  border-color: var(--accent);
}

.org-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.org-type {
  font-size: 12px;
  color: var(--text-secondary);
}

[data-theme="dark"] .status-筹备中 { background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); }
[data-theme="dark"] .status-进行中 { background: rgba(45, 212, 191, 0.15); color: #2dd4bf; border: 1px solid rgba(45, 212, 191, 0.3); }
[data-theme="dark"] .status-已结束 { background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); }
[data-theme="dark"] .status-已归档 { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }

.btn-preview {
  background: var(--bg-secondary, #f1f5f9);
  color: var(--text-primary, #0f172a);
  border: 1px solid var(--border-light, #e2e8f0);
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-preview:hover {
  background: var(--primary-light, #dbeafe);
  color: var(--primary, #2563eb);
  border-color: var(--primary, #2563eb);
}

.cert-metrics { display: flex; flex-wrap: wrap; gap: 16px; }
.cert-metric { display: flex; flex-direction: column; align-items: center; min-width: 88px; padding: 12px 16px; background: var(--bg-secondary); border-radius: 8px; }
.cert-metric .num { font-size: 22px; font-weight: 700; color: var(--cinnabar, #b0392b); }
.cert-metric .lbl { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }

</style>
