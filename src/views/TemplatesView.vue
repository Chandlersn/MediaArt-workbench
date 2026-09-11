<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import Modal from '../components/Modal.vue'
import * as dataService from '../services/dataService.js'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { fetchWithAuth, getBlob } from '../services/http.js'
import CustomSelect from '../components/CustomSelect.vue'

const { success, error, warning } = useToast()
const { confirm } = useConfirmDialog()

const defaultCategories = [
  { id: 'cat1', name: '表格模板', icon: '📋' },
  { id: 'cat2', name: '合同模板', icon: '📄' },
  { id: 'cat3', name: '自定义模板', icon: '📁' }
]

const categories = ref([...defaultCategories])
const templates = ref([])
const loading = ref(false)
const showAddCategoryModal = ref(false)
const showUploadModal = ref(false)
const newCategoryName = ref('')
const newCategoryIcon = ref('📁')
const uploadFile = ref(null)
const uploadFileInput = ref(null)
const uploadCategoryId = ref('cat1')
const uploadTemplateName = ref('')

const iconOptions = ['📋', '📄', '📁', '📝', '📊', '🖼️', '📦', '🏷️']

const loadTemplates = async () => {
  loading.value = true
  try {
    await dataService.load()
    const data = dataService.getData('templates')
    // 注意：[] 也是 truthy，若无脑覆盖会把内置的 defaultCategories 清空，
    // 因此只在后端确实返回了非空分类时才覆盖本地默认值
    if (data && Array.isArray(data.categories) && data.categories.length) {
      categories.value = data.categories
    }
    if (data && Array.isArray(data.items) && data.items.length) {
      templates.value = data.items
    }
  } catch (e) {
    console.error('加载模板失败:', e)
  } finally {
    loading.value = false
  }
}

const saveTemplates = async () => {
  try {
    dataService.setData('templates', {
      categories: categories.value,
      items: templates.value
    })
    await dataService.save()
  } catch (e) {
    console.error('保存模板失败:', e)
  }
}

const addCategory = async () => {
  if (!newCategoryName.value.trim()) return
  const newCat = {
    id: `cat${Date.now()}`,
    name: newCategoryName.value.trim(),
    icon: newCategoryIcon.value
  }
  categories.value.push(newCat)
  newCategoryName.value = ''
  newCategoryIcon.value = '📁'
  showAddCategoryModal.value = false
  await saveTemplates()
  success('分类添加成功')
}

const deleteCategory = async (catId) => {
  const cat = categories.value.find(c => c.id === catId)
  const catTemplates = templates.value.filter(t => t.categoryId === catId)
  const confirmed = await confirm({
    title: '确认删除',
    message: `确定要删除分类"${cat?.name}"吗？${catTemplates.length > 0 ? '该分类下的模板将移至"自定义模板"。' : ''}`,
    type: 'danger'
  })
  if (!confirmed) return

  if (catTemplates.length > 0) {
    const customCat = categories.value.find(c => c.name === '自定义模板')
    if (customCat) {
      catTemplates.forEach(t => { t.categoryId = customCat.id })
    }
  }

  categories.value = categories.value.filter(c => c.id !== catId)
  await saveTemplates()
  success('分类已删除')
}

const triggerUploadFile = () => {
  uploadFileInput.value?.click()
}

const handleUploadFileSelect = (e) => {
  uploadFile.value = e.target.files[0]
  if (uploadFile.value && !uploadTemplateName.value) {
    uploadTemplateName.value = uploadFile.value.name
  }
}

const submitUpload = async () => {
  if (!uploadFile.value) return
  if (!uploadTemplateName.value.trim()) {
    warning('请输入模板名称')
    return
  }

  const formData = new FormData()
  formData.append('file', uploadFile.value)
  formData.append('targetPath', 'templates')

  try {
    const response = await fetchWithAuth('/api/upload', {
      method: 'POST',
      body: formData
    })
    const result = await response.json()
    if (result.success) {
      const newTemplate = {
        id: `tpl${Date.now()}`,
        name: uploadTemplateName.value.trim(),
        categoryId: uploadCategoryId.value,
        fileName: uploadFile.value.name,
        size: uploadFile.value.size,
        uploadedAt: new Date().toISOString()
      }
      templates.value.push(newTemplate)
      await saveTemplates()

      showUploadModal.value = false
      uploadFile.value = null
      uploadTemplateName.value = ''
      if (uploadFileInput.value) uploadFileInput.value.value = ''
      success('模板上传成功')
    } else {
      error(result.message || '上传失败')
    }
  } catch (e) {
    console.error('上传失败:', e)
    error('上传失败')
  }
}

const downloadTemplate = async (tpl) => {
  try {
    // 修复：此前用 window.open('/api/get-file?...')——新窗口请求由浏览器发起，
    // 不带 Authorization 头，必然 401（下到的是一个 JSON 错误页）。
    const blob = await getBlob(`/api/get-file?path=${encodeURIComponent(`templates/${tpl.fileName}`)}`)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = tpl.fileName || tpl.name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('下载模板失败:', e)
    error('下载失败')
  }
}

const deleteTemplate = async (tpl) => {
  const confirmed = await confirm({
    title: '确认删除',
    message: `确定要删除模板"${tpl.name}"吗？`,
    type: 'danger'
  })
  if (!confirmed) return

  try {
    await fetchWithAuth('/api/delete-file', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: `templates/${tpl.fileName}` })
    })
  } catch (e) {
    console.warn('删除文件失败:', e)
  }

  templates.value = templates.value.filter(t => t.id !== tpl.id)
  await saveTemplates()
  success('模板已删除')
}

const getFileIcon = (filename) => {
  const ext = filename?.split('.').pop()?.toLowerCase()
  const icons = {
    pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊',
    ppt: '📽️', pptx: '📽️', txt: '📃', zip: '📦', rar: '📦'
  }
  return icons[ext] || '📄'
}

const formatSize = (bytes) => {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

const templatesByCategory = computed(() => {
  const map = {}
  for (const cat of categories.value) {
    map[cat.id] = templates.value.filter(t => t.categoryId === cat.id)
  }
  return map
})

onMounted(() => {
  loadTemplates()
})

onActivated(() => {
  loadTemplates()
})
</script>

<template>
  <div class="templates-view">
    <div class="page-header">
      <h2>模板管理</h2>
      <div class="header-actions">
        <button class="btn-secondary" @click="showAddCategoryModal = true">添加分类</button>
        <button class="btn-primary" @click="showUploadModal = true">上传模板</button>
      </div>
    </div>

    <div class="template-container">
      <div
        v-for="cat in categories"
        :key="cat.id"
        class="template-category"
      >
        <div class="template-category-header">
          <h3>
            <span class="category-icon">{{ cat.icon }}</span>
            {{ cat.name }}
            <span class="category-count">({{ templatesByCategory[cat.id]?.length || 0 }})</span>
          </h3>
          <div class="template-category-actions">
            <button class="btn-sm btn-danger" @click="deleteCategory(cat.id)">删除分类</button>
          </div>
        </div>

        <div class="template-list">
          <div
            v-for="tpl in templatesByCategory[cat.id]"
            :key="tpl.id"
            class="template-item"
            @click="downloadTemplate(tpl)"
          >
            <div class="template-item-icon">{{ getFileIcon(tpl.fileName) }}</div>
            <div class="template-item-info">
              <div class="template-item-name">{{ tpl.name }}</div>
              <div class="template-item-meta">{{ formatSize(tpl.size) }} · {{ formatDate(tpl.uploadedAt) }}</div>
            </div>
            <div class="template-item-actions" @click.stop>
              <button title="下载" @click="downloadTemplate(tpl)">⬇️</button>
              <button class="danger" title="删除" @click="deleteTemplate(tpl)">🗑️</button>
            </div>
          </div>

          <div
            v-if="!templatesByCategory[cat.id]?.length"
            class="empty-category"
          >
            暂无模板，点击"上传模板"添加
          </div>
        </div>
      </div>
    </div>

    <Modal
      :show="showAddCategoryModal"
      title="添加分类"
      size="small"
      @close="showAddCategoryModal = false"
    >
      <div class="form-group">
        <label class="form-label">分类名称</label>
        <input
          type="text"
          v-model="newCategoryName"
          class="form-input"
          placeholder="请输入分类名称"
          @keyup.enter="addCategory"
        />
      </div>
      <div class="form-group">
        <label class="form-label">选择图标</label>
        <div class="icon-picker">
          <button
            v-for="icon in iconOptions"
            :key="icon"
            class="icon-option"
            :class="{ active: newCategoryIcon === icon }"
            @click="newCategoryIcon = icon"
          >
            {{ icon }}
          </button>
        </div>
      </div>
      <template #footer>
        <button class="btn-secondary" @click="showAddCategoryModal = false">取消</button>
        <button class="btn-primary" @click="addCategory" :disabled="!newCategoryName.trim()">添加</button>
      </template>
    </Modal>

    <Modal
      :show="showUploadModal"
      title="上传模板"
      size="medium"
      @close="showUploadModal = false"
    >
      <div class="form-group">
        <label class="form-label">模板名称</label>
        <input
          type="text"
          v-model="uploadTemplateName"
          class="form-input"
          placeholder="请输入模板名称"
        />
      </div>
      <div class="form-group">
        <label class="form-label">选择分类</label>
        <CustomSelect v-model="uploadCategoryId" style="width:100%">
          <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.icon }} {{ cat.name }}</option>
        </CustomSelect>
      </div>
      <div class="form-group">
        <label class="form-label">选择文件</label>
        <input
          type="file"
          ref="uploadFileInput"
          style="display: none;"
          @change="handleUploadFileSelect"
        />
        <button class="btn-secondary" @click="triggerUploadFile">选择文件</button>
        <span v-if="uploadFile" class="selected-file">{{ uploadFile.name }}</span>
      </div>
      <template #footer>
        <button class="btn-secondary" @click="showUploadModal = false">取消</button>
        <button class="btn-primary" @click="submitUpload" :disabled="!uploadFile || !uploadTemplateName.trim()">上传</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.templates-view {
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.template-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.template-category {
  background: var(--surface);
  border-radius: 10px;
  border: 1px solid var(--border-light);
  overflow: hidden;
}

.template-category-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-light);
}

.template-category-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.category-icon {
  font-size: 18px;
}

.category-count {
  font-size: 13px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.template-category-actions {
  display: flex;
  gap: 8px;
}

.template-list {
  padding: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.template-item {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.template-item:hover {
  background: var(--bg-tertiary);
  border-color: var(--accent);
}

.template-item-icon {
  width: 40px;
  height: 40px;
  background: var(--surface);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.template-item-info {
  flex: 1;
  min-width: 0;
}

.template-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.template-item-meta {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.template-item-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.template-item:hover .template-item-actions {
  opacity: 1;
}

.template-item-actions button {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: var(--surface);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.15s;
  padding: 0;
}

.template-item-actions button:hover {
  background: var(--accent);
  color: white;
}

.template-item-actions button.danger:hover {
  background: var(--danger);
}

.empty-category {
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 14px;
  grid-column: 1 / -1;
}

.icon-picker {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.icon-option {
  width: 40px;
  height: 40px;
  border: 2px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  transition: all 0.15s;
  padding: 0;
}

.icon-option:hover {
  border-color: var(--accent);
}

.icon-option.active {
  border-color: var(--accent);
  background: var(--accent-light);
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--text-primary);
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background-color: var(--surface);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

.form-input:focus {
  border-color: var(--accent);
}

.selected-file {
  margin-left: 12px;
  font-size: 14px;
  color: var(--text-primary);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  background: var(--accent);
  color: white;
  transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  transition: all 0.2s;
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--surface);
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-sm:hover {
  background: var(--bg-hover);
}

.btn-sm.btn-danger {
  color: var(--danger);
  border-color: var(--danger);
}

.btn-sm.btn-danger:hover {
  background: var(--danger);
  color: white;
}
</style>
