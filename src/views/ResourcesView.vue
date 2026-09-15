<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import FilePreviewPanel from '../components/FilePreviewPanel.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { get, post, getBlob, fetchWithAuth } from '../services/http.js'
import CustomSelect from '../components/CustomSelect.vue'
import { useResourceStore } from '../stores'

const { success, error } = useToast()
const { confirm } = useConfirmDialog()
const resourceStore = useResourceStore()

const allFiles = ref([])
const loading = ref(false)
const currentType = ref('all')
const searchKeyword = ref('')
const currentView = ref('list')
const currentSort = ref('date-desc')
const showUploadModal = ref(false)
const uploadFile = ref(null)
const uploadFileInput = ref(null)
const uploadCategory = ref('')

// 分类管理
const showCatModal = ref(false)
const catForm = ref({ name: '', folder: '', icon: '📁' })
const editingCatId = ref(null)

const categories = computed(() => resourceStore.categories)

const typeTabs = computed(() => [
  { id: 'all', label: '全部', count: stats.value.total },
  ...categories.value.map(c => ({ id: c.id, label: c.name, count: stats.value[c.id] || 0 }))
])

const getFileType = (filename) => {
  const ext = filename?.split('.').pop()?.toLowerCase()
  const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp']
  const videoExts = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv']
  const docExts = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv']
  const audioExts = ['mp3', 'wav', 'flac', 'aac', 'ogg']
  if (imageExts.includes(ext)) return 'image'
  if (videoExts.includes(ext)) return 'video'
  if (docExts.includes(ext)) return 'document'
  if (audioExts.includes(ext)) return 'audio'
  return 'other'
}

// 文件是否落在某个分类的物理文件夹内
const inAnyCategoryFolder = (p) => categories.value.some(c => c.folder && (p.startsWith(c.folder + '/') || p.includes('/' + c.folder + '/')))

// 文件是否归属某分类：优先按物理文件夹归属；未落入任何分类文件夹的文件（如根目录）按扩展名类型兜底
const matchCategory = (file, cat) => {
  const p = file.path || file.name || ''
  if (cat.folder && (p.startsWith(cat.folder + '/') || p.includes('/' + cat.folder + '/'))) return true
  if (!inAnyCategoryFolder(p)) return getFileType(file.name) === cat.id
  return false
}

const typeMeta = (filename) => {
  const map = {
    image: { label: '图片', class: 'type-image' },
    video: { label: '视频', class: 'type-video' },
    document: { label: '文档', class: 'type-document' },
    audio: { label: '音频', class: 'type-audio' },
    other: { label: '其他', class: 'type-other' }
  }
  return map[getFileType(filename)] || map.other
}

const formatSize = (bytes) => {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const formatDate = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return `${date.toLocaleDateString('zh-CN')} ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

const stats = computed(() => {
  const s = { total: allFiles.value.length, image: 0, video: 0, document: 0, audio: 0, other: 0 }
  for (const f of allFiles.value) {
    const t = getFileType(f.name)
    if (t === 'image') s.image++; else if (t === 'video') s.video++
    else if (t === 'document') s.document++; else if (t === 'audio') s.audio++; else s.other++
  }
  categories.value.forEach(c => { s[c.id] = allFiles.value.filter(f => matchCategory(f, c)).length })
  return s
})

const filteredFiles = computed(() => {
  let files = [...allFiles.value]
  if (currentType.value !== 'all') {
    const cat = categories.value.find(c => c.id === currentType.value)
    if (cat) files = files.filter(f => matchCategory(f, cat))
  }
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    files = files.filter(f => f.name.toLowerCase().includes(kw))
  }
  switch (currentSort.value) {
    case 'date-desc': files.sort((a, b) => (b.modifiedTime || b.modified || 0) - (a.modifiedTime || a.modified || 0)); break
    case 'date-asc': files.sort((a, b) => (a.modifiedTime || a.modified || 0) - (b.modifiedTime || b.modified || 0)); break
    case 'name': files.sort((a, b) => a.name.localeCompare(b.name)); break
    case 'size': files.sort((a, b) => (b.size || 0) - (a.size || 0)); break
  }
  return files
})

const sortOptions = [
  { value: 'date-desc', label: '最新优先' },
  { value: 'date-asc', label: '最旧优先' },
  { value: 'name', label: '按名称' },
  { value: 'size', label: '按大小' }
]

const loadFiles = async () => {
  loading.value = true
  try {
    const result = await get('/api/list-files?folder=')
    allFiles.value = result.files || []
  } catch (e) {
    console.error('加载文件列表失败:', e)
    allFiles.value = []
  } finally {
    loading.value = false
  }
}

const filterByType = (type) => { currentType.value = type }

const openFile = async (file) => {
  try {
    const filePath = file.path || file.name
    const result = await post('/api/open-resource', { path: filePath })
    if (result.success) success(`正在用本地软件打开: ${file.name}`)
    else error(result.message || '打开失败')
  } catch (e) { console.error(e); error('打开失败') }
}

const openLocalFolder = async () => {
  try {
    const result = await post('/api/open-folder', { path: '' })
    if (result.success) success('已打开本地资源文件夹')
    else error(result.message || '打开失败')
  } catch (e) { console.error(e); error('打开本地文件夹失败') }
}

const downloadFile = async (file) => {
  const filePath = file.path || file.name
  try {
    const blob = await getBlob(`/api/get-file?path=${encodeURIComponent(filePath)}`)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = file.name
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) { console.error(e); error('下载失败') }
}

const showPreview = ref(false)
const previewTarget = ref({ fileName: '', filePath: '' })
const previewFileItem = (file) => {
  previewTarget.value = { fileName: file.name, filePath: file.path || file.name }
  showPreview.value = true
}

const deleteFile = async (file) => {
  const ok = await confirm({ title: '确认删除', message: `确定要删除 "${file.name}" 吗？此操作不可恢复。`, type: 'danger' })
  if (!ok) return
  try {
    const filePath = file.path || file.name
    const response = await fetchWithAuth(`/api/delete-file?path=${encodeURIComponent(filePath)}`, { method: 'DELETE' })
    const result = await response.json()
    if (result.success) { success('删除成功'); await loadFiles() }
    else error(result.message || '删除失败')
  } catch (e) { console.error(e); error('删除失败') }
}

const triggerUploadFile = () => uploadFileInput.value?.click()
const handleUploadFileSelect = (e) => { uploadFile.value = e.target.files[0] }
const submitUpload = async () => {
  if (!uploadFile.value) return
  const formData = new FormData()
  formData.append('file', uploadFile.value)
  // 未选分类时，按文件扩展名自动落位到对应类型文件夹（避免散落在根目录）
  const cat = categories.value.find(c => c.id === uploadCategory.value)
    || categories.value.find(c => c.id === getFileType(uploadFile.value.name))
  formData.append('targetPath', cat?.folder || '')
  try {
    const response = await fetchWithAuth('/api/upload', { method: 'POST', body: formData })
    const result = await response.json()
    if (result.success) { success('上传成功'); showUploadModal.value = false; uploadFile.value = null; if (uploadFileInput.value) uploadFileInput.value.value = ''; await loadFiles() }
    else error(result.message || '上传失败')
  } catch (e) { console.error(e); error('上传失败') }
}

// ===== 分类管理 =====
const openCatModal = (cat = null) => {
  editingCatId.value = cat ? cat.id : null
  catForm.value = cat ? { ...cat } : { name: '', folder: '', icon: '📁' }
  showCatModal.value = true
}
const saveCat = async () => {
  if (editingCatId.value) {
    const ok = await resourceStore.updateCategory(editingCatId.value, { name: catForm.value.name, folder: catForm.value.folder, icon: catForm.value.icon })
    if (ok) success('分类已更新')
  } else {
    const ok = await resourceStore.addCategory(catForm.value)
    if (ok) success('分类已添加')
    else error('分类已存在或信息不完整')
  }
  showCatModal.value = false
}
const removeCat = async (cat) => {
  const ok = await confirm({ title: '确认删除', message: `确定删除分类「${cat.name}」吗？文件夹中的文件不会被删除。`, type: 'danger' })
  if (ok) { await resourceStore.deleteCategory(cat.id); success('分类已删除') }
}

onMounted(async () => { await resourceStore.load(); await loadFiles() })
onActivated(() => { loadFiles() })
</script>

<template>
  <div class="resources-view">
    <PageHeader title="资源中心" description="管理项目图片、视频、文档等资源文件">
      <template #actions>
        <button class="btn-secondary" @click="openCatModal()">管理分类</button>
        <button class="btn-secondary" @click="openLocalFolder">打开本地文件夹</button>
        <button class="btn-primary" @click="showUploadModal = true">上传资源</button>
      </template>
    </PageHeader>

    <div class="category-tabs" role="tablist">
      <button
        v-for="tab in typeTabs"
        :key="tab.id"
        class="category-tab"
        :class="{ active: currentType === tab.id }"
        role="tab"
        :aria-selected="currentType === tab.id"
        @click="filterByType(tab.id)"
      >
        {{ tab.label }}
        <span class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <div class="toolbar">
      <input v-model="searchKeyword" type="text" class="search-input" placeholder="搜索资源文件..." />
      <div class="toolbar-actions">
        <CustomSelect v-model="currentSort">
          <option v-for="opt in sortOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </CustomSelect>
        <div class="view-toggle">
          <button class="view-btn" :class="{ active: currentView === 'grid' }" @click="currentView = 'grid'">网格</button>
          <button class="view-btn" :class="{ active: currentView === 'list' }" @click="currentView = 'list'">列表</button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty-state"><span class="empty-icon"></span><p>加载中...</p></div>
    <div v-else-if="filteredFiles.length === 0" class="empty-state">
      <span class="empty-icon"></span>
      <p>{{ searchKeyword ? '没有找到匹配的文件' : '暂无资源文件' }}</p>
      <button class="btn-secondary" @click="showUploadModal = true">上传第一个资源</button>
    </div>

    <div v-else class="resource-container" :class="currentView">
      <div
        v-for="file in filteredFiles"
        :key="file.path || file.name"
        class="resource-card"
        :class="{ 'list-view': currentView === 'list' }"
        @click="previewFileItem(file)"
      >
        <div class="card-main">
          <span class="type-badge" :class="typeMeta(file.name).class">{{ typeMeta(file.name).label }}</span>
          <div class="card-info">
            <div class="card-name" :title="file.name">{{ file.name }}</div>
            <div class="card-meta">{{ formatSize(file.size) }} · {{ formatDate(file.modifiedTime || file.modified) }}</div>
          </div>
        </div>
        <div class="card-actions" @click.stop>
          <button class="btn-link" @click="previewFileItem(file)">预览</button>
          <button class="btn-link" @click="openFile(file)">打开</button>
          <button class="btn-link" @click="downloadFile(file)">下载</button>
          <button class="btn-link danger" @click="deleteFile(file)">删除</button>
        </div>
      </div>
    </div>

    <Modal :show="showUploadModal" title="上传资源" size="medium" @close="showUploadModal = false">
      <div class="form-group">
        <label class="form-label">选择分类</label>
        <CustomSelect v-model="uploadCategory" style="width:100%">
          <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }} ({{ cat.folder }}/)</option>
        </CustomSelect>
      </div>
      <div class="form-group">
        <label class="form-label">选择文件</label>
        <input type="file" ref="uploadFileInput" style="display:none;" @change="handleUploadFileSelect" />
        <button class="btn-secondary" @click="triggerUploadFile">选择文件</button>
        <span v-if="uploadFile" class="selected-file">{{ uploadFile.name }}</span>
      </div>
      <template #footer>
        <button class="btn-secondary" @click="showUploadModal = false">取消</button>
        <button class="btn-primary" @click="submitUpload" :disabled="!uploadFile">上传</button>
      </template>
    </Modal>

    <Modal :show="showCatModal" title="管理资源分类" size="medium" @close="showCatModal = false">
      <div class="cat-list">
        <div v-for="cat in categories" :key="cat.id" class="cat-row">
          <span class="cat-icon">{{ cat.icon }}</span>
          <span class="cat-name">{{ cat.name }}</span>
          <span class="cat-folder">{{ cat.folder }}/</span>
          <button class="btn-link" @click="openCatModal(cat)">编辑</button>
          <button class="btn-link danger" @click="removeCat(cat)">删除</button>
        </div>
      </div>
      <div class="cat-form">
        <div class="form-group">
          <label class="form-label">分类名称 <span class="required">*</span></label>
          <input v-model="catForm.name" type="text" class="form-input" placeholder="如：设计素材" />
        </div>
        <div class="form-group">
          <label class="form-label">存储文件夹 <span class="required">*</span></label>
          <input v-model="catForm.folder" type="text" class="form-input" placeholder="如：designs" />
          <p class="form-hint">文件将保存到资源目录下的该文件夹中</p>
        </div>
      </div>
      <template #footer>
        <button class="btn-secondary" @click="showCatModal = false">关闭</button>
        <button class="btn-primary" @click="saveCat">保存分类</button>
      </template>
    </Modal>

    <FilePreviewPanel v-model="showPreview" source="file" :file-name="previewTarget.fileName" :file-path="previewTarget.filePath" />
  </div>
</template>

<style scoped>
.resources-view { padding: 24px; max-width: 1200px; width: 100%; }
.category-tabs {
  display: inline-flex; flex-wrap: wrap; gap: 4px; padding: 4px; margin-bottom: 20px;
  background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-md);
}
.category-tab {
  display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px; border: none;
  border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary);
  font-size: 14px; font-weight: 500; cursor: pointer; transition: all var(--transition-fast);
}
.category-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.category-tab.active { background: var(--surface); color: var(--text-primary); box-shadow: var(--shadow-sm); }
.tab-count { min-width: 20px; padding: 1px 6px; border-radius: 10px; background: var(--bg-tertiary); color: var(--text-secondary); font-size: 12px; font-weight: 500; text-align: center; }
.category-tab.active .tab-count { background: var(--accent-light); color: var(--accent); }

.toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.search-input {
  flex: 1; min-width: 200px; padding: 10px 16px; border: 1px solid var(--border);
  border-radius: var(--radius-md); background: var(--surface); color: var(--text-primary); font-size: 14px;
}
.search-input:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--accent-light); }
.toolbar-actions { display: flex; align-items: center; gap: 12px; }
.view-toggle { display: flex; padding: 3px; gap: 2px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-sm); }
.view-btn { padding: 7px 14px; border: none; border-radius: 4px; background: transparent; color: var(--text-secondary); font-size: 13px; font-weight: 500; cursor: pointer; transition: all var(--transition-fast); }
.view-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.view-btn.active { background: var(--surface); color: var(--accent); box-shadow: var(--shadow-sm); }

.resource-container.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.resource-container.list { display: flex; flex-direction: column; gap: 8px; }
.resource-card { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); transition: all var(--transition-base); }
.resource-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
.resource-card.list-view { flex-direction: row; align-items: center; gap: 20px; padding: 14px 20px; }
.card-main { display: flex; flex-direction: column; gap: 10px; flex: 1; min-width: 0; }
.resource-card.list-view .card-main { flex-direction: row; align-items: center; gap: 14px; }
.type-badge { align-self: flex-start; flex-shrink: 0; padding: 3px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }
.type-image { background: #e6f7ff; color: #1890ff; }
.type-video { background: #f4e7ff; color: #7c3aed; }
.type-document { background: #e6fffb; color: #0d9488; }
.type-audio { background: #f6ffed; color: #52c41a; }
.type-other { background: #f5f5f5; color: #8c8c8c; }
[data-theme="dark"] .type-image { background: rgba(96,165,250,0.15); color: #60a5fa; }
[data-theme="dark"] .type-video { background: rgba(167,139,250,0.15); color: #a78bfa; }
[data-theme="dark"] .type-document { background: rgba(45,212,191,0.15); color: #2dd4bf; }
[data-theme="dark"] .type-audio { background: rgba(52,211,153,0.15); color: #34d399; }
[data-theme="dark"] .type-other { background: rgba(148,163,184,0.15); color: #94a3b8; }
.card-info { flex: 1; min-width: 0; }
.card-name { font-size: 14px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-meta { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.card-actions { display: flex; gap: 6px; padding-top: 14px; border-top: 1px solid var(--border-light); }
.resource-card.list-view .card-actions { padding-top: 0; border-top: none; flex-shrink: 0; }
.btn-link { padding: 4px 10px; background: none; border: none; border-radius: var(--radius-sm); color: var(--accent); font-size: 13px; font-weight: 500; cursor: pointer; transition: all var(--transition-fast); }
.btn-link:hover { background: var(--accent-light); }
.btn-link.danger { color: var(--danger); }
.btn-link.danger:hover { background: var(--danger-light); }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 72px 20px; color: var(--text-secondary); background: var(--surface); border: 1px dashed var(--border); border-radius: var(--radius-lg); }
.empty-icon { width: 48px; height: 48px; border-radius: 50%; background: var(--bg-secondary); }
.empty-state p { font-size: 14px; color: var(--text-tertiary); }

.cat-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.cat-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; background: var(--bg-secondary); border-radius: var(--radius-sm); }
.cat-icon { font-size: 16px; }
.cat-name { flex: 1; font-size: 14px; color: var(--text-primary); font-weight: 500; }
.cat-folder { font-size: 12px; color: var(--text-tertiary); }
.cat-form { border-top: 1px solid var(--border-light); padding-top: 16px; }
.form-group { margin-bottom: 16px; }
.form-label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; color: var(--text-primary); }
.required { color: var(--danger-color); }
.form-input { width: 100%; padding: 10px 12px; font-size: 14px; border: 1px solid var(--border-color); border-radius: 6px; background-color: var(--bg-primary); color: var(--text-primary); transition: border-color 0.2s; }
.form-input:focus { outline: none; border-color: var(--accent); }
.form-hint { font-size: 12px; color: var(--text-tertiary); margin: 4px 0 0; }
.selected-file { margin-left: 12px; font-size: 14px; color: var(--text-primary); }

@media (max-width: 640px) {
  .toolbar { flex-direction: column; align-items: stretch; }
  .toolbar-actions { justify-content: space-between; }
}
</style>
