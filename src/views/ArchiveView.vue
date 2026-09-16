<script setup>
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import Modal from '../components/Modal.vue'
import FilePreviewPanel from '../components/FilePreviewPanel.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { get, post, del, fetchWithAuth } from '../services/http.js'
const { success, error } = useToast()
const { confirm, prompt } = useConfirmDialog()

// 归档根目录下的文件夹即"分类"。本地目录名带序号前缀（如 01_项目资料），
// 展示时去掉前缀；描述仅对内置 6 类保留文案，其余用默认。
// 分类描述以后端单一权威定义为准（server/archive/taxonomy.py），
// 这里保留一份兜底文案，接口不可用时仍能正常展示。
const CATEGORY_DESCRIPTIONS_FALLBACK = {
  '01_项目资料': '策划文档、宣传物料、现场记录、项目成果',
  '02_选手档案': '个人信息、参赛记录、作品、获奖证书、照片',
  '03_合作机构': '合作协议、往来函件、结算单据、合作记录',
  '04_财务管理': '收入凭证、支出凭证、财务报表、税务',
  '05_知识资源': '赛事规则、培训教材、经验总结',
  '06_系统备份': '自动备份、手动备份'
}
const categoryDescriptions = ref({ ...CATEGORY_DESCRIPTIONS_FALLBACK })

const loadTaxonomy = async () => {
  try {
    const tax = await get('/api/archive-taxonomy')
    if (tax && tax.descriptions) {
      categoryDescriptions.value = { ...CATEGORY_DESCRIPTIONS_FALLBACK, ...tax.descriptions }
    }
  } catch (e) {
    console.error('加载归档分类定义失败:', e)
  }
}

const stripSeqPrefix = (name) => name.replace(/^\d+_/, '')

// 分类列表直接来自归档根目录的真实文件夹，而非写死的数组。
// 这样新建分类后回读磁盘，刷新页面也不会丢失。
const categories = ref([])

const loadCategories = async () => {
  await loadTaxonomy()
  try {
    const items = await get('/api/list-archives?folder=')
    categories.value = (Array.isArray(items) ? items : [])
      .filter(i => i.type === 'folder')
      .map(i => ({
        id: i.name,
        name: stripSeqPrefix(i.name),
        path: i.name,
        description: categoryDescriptions.value[i.name] || '本地归档分类'
      }))
  } catch (e) {
    console.error('加载归档分类失败:', e)
    categories.value = []
  }
}

const browsing = ref(false)
const currentPath = ref('')
const files = ref([])
const pathHistory = ref([])
const loading = ref(false)
const categoryCounts = ref({})
// 各分类下是否有文件（用于把"有内容的分类/文件夹"自动高亮成绿色）
const categoryHasFiles = ref({})
const searchKeyword = ref('')
const showUploadModal = ref(false)
const showNewFolderModal = ref(false)
const newFolderName = ref('')
const uploadFile = ref(null)
const uploadFileInput = ref(null)
// 归档上传时的「文档标题」：人工填（默认预填上传文件的原名），
// 与主体、日期一起组成 主体_标题_日期.ext —— 这样同目录内才区分得开。
const uploadTitle = ref('')

const folders = computed(() => files.value.filter(f => f.type === 'folder'))
const fileItems = computed(() => files.value.filter(f => f.type === 'file'))

// ===== 递归搜索：像本地文件管理器那样，搜「当前分类下（含所有子目录）」或整个归档 =====
const searchResults = ref([])
const searchLoading = ref(false)
const searchTruncated = ref(false)
let searchTimer = null

const searchMode = computed(() => !!searchKeyword.value.trim())

const runSearch = async () => {
  const q = searchKeyword.value.trim()
  if (!q) {
    searchResults.value = []
    searchTruncated.value = false
    return
  }
  // 已进入分类 → 只搜该分类（含子目录）；在总览页 → 搜整个归档
  const folder = browsing.value ? currentPath.value : ''
  searchLoading.value = true
  try {
    const res = await get(`/api/search-archives?q=${encodeURIComponent(q)}&folder=${encodeURIComponent(folder)}`)
    searchResults.value = res.results || []
    searchTruncated.value = !!res.truncated
  } catch (e) {
    console.error('搜索失败:', e)
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

watch(searchKeyword, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(runSearch, 250)   // 防抖：避免每敲一个字就打一次接口
})

// 把路径拆成逐级历史，便于「返回上一级」一路往回走
const buildHistory = (p) => {
  const segs = String(p || '').split('/').filter(Boolean)
  return segs.map((_, i) => segs.slice(0, i + 1).join('/'))
}

// 命中片段高亮（分段渲染，不用 v-html，避免文件名注入）
const nameSegments = (name) => {
  const text = String(name ?? '')
  const kw = searchKeyword.value.trim()
  if (!kw) return [{ text, hit: false }]
  const lower = text.toLowerCase()
  const k = kw.toLowerCase()
  const out = []
  let i = 0
  while (i < text.length) {
    const idx = lower.indexOf(k, i)
    if (idx < 0) { out.push({ text: text.slice(i), hit: false }); break }
    if (idx > i) out.push({ text: text.slice(i, idx), hit: false })
    out.push({ text: text.slice(idx, idx + k.length), hit: true })
    i = idx + k.length
  }
  return out.length ? out : [{ text, hit: false }]
}

// 打开搜索结果：文件夹 → 进入该目录；文件 → 用本地软件打开
const openSearchResult = async (item) => {
  searchKeyword.value = ''
  if (item.type === 'folder') {
    browsing.value = true
    pathHistory.value = buildHistory(item.path)
    currentPath.value = item.path
    currentPage.value = 1
    await renderBrowserContent(item.path)
  } else {
    await openArchiveFile(item.path)
  }
}

// 定位：跳到该结果所在的目录
const locateResult = async (item) => {
  const parent = item.parent || ''
  searchKeyword.value = ''
  browsing.value = true
  pathHistory.value = buildHistory(parent)
  currentPath.value = parent
  currentPage.value = 1
  await renderBrowserContent(parent)
}

const currentPage = ref(1)
const pageSize = 15

const paginatedItems = computed(() => {
  const all = [...folders.value, ...fileItems.value]
  const start = (currentPage.value - 1) * pageSize
  return all.slice(start, start + pageSize)
})

const totalPages = computed(() => {
  const total = folders.value.length + fileItems.value.length
  return Math.max(1, Math.ceil(total / pageSize))
})

const goToPage = (page) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
  }
}

const visiblePages = computed(() => {
  const pages = []
  const total = totalPages.value
  const current = currentPage.value
  let start = Math.max(1, current - 2)
  const end = Math.min(total, start + 4)
  if (end - start < 4) start = Math.max(1, end - 4)
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
})

const fetchCategoryCounts = async () => {
  for (const cat of categories.value) {
    try {
      const result = await get(`/api/count-files?folder=${encodeURIComponent(cat.path)}&recursive=true`)
      const folderNum = result.folders || 0
      const fileNum = result.files || 0
      categoryHasFiles.value[cat.id] = fileNum > 0

      if (folderNum > 0 && fileNum > 0) {
        categoryCounts.value[cat.id] = `${folderNum} 个文件夹 / ${fileNum} 个文件`
      } else if (folderNum > 0) {
        categoryCounts.value[cat.id] = `${folderNum} 个文件夹`
      } else if (fileNum > 0) {
        categoryCounts.value[cat.id] = `${fileNum} 个文件`
      } else {
        categoryCounts.value[cat.id] = '空文件夹'
      }
    } catch (e) {
      console.error(`获取 ${cat.name} 文件统计失败:`, e)
      categoryCounts.value[cat.id] = '0 个文件'
      categoryHasFiles.value[cat.id] = false
    }
  }
}

const browseCategory = async (category) => {
  browsing.value = true
  currentPath.value = category
  pathHistory.value = [category]
  searchKeyword.value = ''
  currentPage.value = 1
  await renderBrowserContent(category)
}

const renderBrowserContent = async (folder) => {
  loading.value = true
  try {
    const result = await get(`/api/list-archives?folder=${encodeURIComponent(folder)}`)

    if (!result || !Array.isArray(result) || result.length === 0) {
      files.value = []
    } else {
      files.value = result.sort((a, b) => {
        if (a.type === b.type) return a.name.localeCompare(b.name)
        return a.type === 'folder' ? -1 : 1
      })

      // 更新文件夹统计
      updateFolderCounts(folders.value)
    }
  } catch (e) {
    console.error('加载文件列表失败:', e)
    files.value = []
  } finally {
    loading.value = false
  }
}

const updateFolderCounts = async (folderList) => {
  for (const folder of folderList) {
    try {
      const result = await get(`/api/count-files?folder=${encodeURIComponent(folder.path)}&recursive=true`)
      folder.fileCount = result.files || 0
    } catch (e) {
      console.error('统计文件夹失败:', folder.name, e)
      folder.fileCount = 0
    }
  }
}

const openFolder = async (path) => {
  pathHistory.value.push(path)
  currentPath.value = path
  searchKeyword.value = ''
  currentPage.value = 1
  await renderBrowserContent(path)
}

const goBack = async () => {
  if (pathHistory.value.length <= 1) {
    closeBrowser()
  } else {
    pathHistory.value.pop()
    currentPath.value = pathHistory.value[pathHistory.value.length - 1]
    await renderBrowserContent(currentPath.value)
  }
}

const closeBrowser = () => {
  browsing.value = false
  currentPath.value = ''
  files.value = []
  pathHistory.value = []
  fetchCategoryCounts()
}

const refresh = async () => {
  if (currentPath.value) {
    await renderBrowserContent(currentPath.value)
  } else {
    await fetchCategoryCounts()
  }
  success('已刷新')
}

const openArchiveFile = async (path) => {
  try {
    const result = await post('/api/open-archive', { path })
    if (result.success) {
      success(`正在用本地软件打开: ${path.split('/').pop()}`)
    } else {
      error(`打开失败: ${result.message}`)
    }
  } catch (e) {
    console.error('打开文件失败:', e)
    error(`打开失败: ${e.message}`)
  }
}

// 文件预览（归档页此前只能"用本地软件打开"，没有站内预览）
const showPreview = ref(false)
const previewTarget = ref({ fileName: '', filePath: '' })

const previewArchiveFile = (item) => {
  previewTarget.value = { fileName: item.name, filePath: item.path }
  showPreview.value = true
}

const deleteFile = async (path) => {
  const fileName = path.split('/').pop()

  const confirmed = await confirm({
    title: '删除文件',
    message: `确定要删除文件 "${fileName}" 吗？此操作不可恢复。`,
    type: 'danger'
  })

  if (!confirmed) return

  try {
    const result = await del(`/api/delete-file?path=${encodeURIComponent(path)}`)

    if (result.success) {
      success('文件已删除')
      await renderBrowserContent(currentPath.value)
      fetchCategoryCounts()
    } else {
      error(`删除失败: ${result.message}`)
    }
  } catch (e) {
    console.error('删除文件失败:', e)
    error('删除失败')
  }
}

const deleteFolder = async (path, name) => {
  const confirmed = await confirm({
    title: '删除文件夹',
    message: `确定要删除文件夹 "${name}" 吗？此操作将删除文件夹及其所有内容，不可恢复。`,
    type: 'danger'
  })

  if (!confirmed) return

  try {
    const result = await del(`/api/delete-folder?path=${encodeURIComponent(path)}`)

    if (result.success) {
      success('文件夹已删除')
      await renderBrowserContent(currentPath.value)
      fetchCategoryCounts()
    } else {
      error(`删除失败: ${result.message || '未知错误'}`)
    }
  } catch (e) {
    console.error('删除文件夹失败:', e)
    error('删除失败')
  }
}

const renameFolder = async (path, oldName) => {
  const newName = await prompt({
    title: '重命名文件夹',
    message: '请输入新的文件夹名称',
    defaultValue: oldName,
    placeholder: '文件夹名称'
  })
  if (!newName) return

  const trimmedName = newName
  if (trimmedName === oldName) return

  try {
    const response = await fetchWithAuth('/api/rename-folder', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        oldPath: path,
        newPath: trimmedName
      })
    })
    const result = await response.json()
    if (result.success) {
      success('重命名成功')
      await renderBrowserContent(currentPath.value)
    } else {
      error(result.message || '重命名失败')
    }
  } catch (e) {
    console.error('重命名失败:', e)
    error('重命名失败')
  }
}

// 重命名文件：手动修正历史「机械名」（含存量文件）—— 给出可读的标题
const renameFile = async (path, oldName) => {
  const newName = await prompt({
    title: '重命名文件',
    message: '建议格式：主体_标题_日期.扩展名（主体与日期可保留原值，重点是标题）',
    defaultValue: oldName,
    placeholder: '新文件名'
  })
  if (!newName || newName === oldName) return

  try {
    const response = await fetchWithAuth('/api/rename-file', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, newName })
    })
    const result = await response.json()
    if (result.success) {
      success('重命名成功')
      await renderBrowserContent(currentPath.value)
    } else {
      error(result.message || '重命名失败')
    }
  } catch (e) {
    console.error('重命名文件失败:', e)
    error('重命名失败')
  }
}

const getFileIconUrl = (fileName) => {
  const lastDot = fileName?.lastIndexOf('.')
  if (!lastDot || lastDot < 1) return '/api/file-icon?ext=default'
  const ext = fileName.slice(lastDot + 1).toLowerCase()
  if (!ext) return '/api/file-icon?ext=default'
  return `/api/file-icon?ext=${encodeURIComponent(ext)}`
}

const getFolderIconUrl = () => {
  return '/api/file-icon?type=folder'
}

const exportAll = async () => {
  try {
    const result = await get('/api/data/load')
    if (result.data) {
      const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `归档备份_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      success('导出成功')
    }
  } catch (e) {
    console.error('导出失败:', e)
    error('导出失败')
  }
}

const triggerUploadFile = () => {
  uploadFileInput.value?.click()
}

const handleUploadFileSelect = (e) => {
  uploadFile.value = e.target.files[0]
  // 预填「文档标题」= 上传文件原名（去扩展名），用户可改成真正能区分的标题
  const f = uploadFile.value
  uploadTitle.value = f ? f.name.replace(/\.[^.]+$/, '') : ''
}

const submitUpload = async () => {
  if (!uploadFile.value) return

  const formData = new FormData()
  formData.append('file', uploadFile.value)
  formData.append('targetPath', currentPath.value)
  // 后端据此组装 主体_标题_日期.ext（主体/日期自动，标题来自这里）
  formData.append('title', uploadTitle.value.trim())

  try {
    const response = await fetchWithAuth('/api/upload', {
      method: 'POST',
      body: formData
    })
    const result = await response.json()
    if (result.success) {
      success('上传成功')
      showUploadModal.value = false
      uploadFile.value = null
      uploadTitle.value = ''
      if (uploadFileInput.value) uploadFileInput.value.value = ''
      await renderBrowserContent(currentPath.value)
      fetchCategoryCounts()
    } else {
      error(result.message || '上传失败')
    }
  } catch (e) {
    console.error('上传失败:', e)
    error('上传失败')
  }
}

const handleNewFolder = () => {
  // 归档根目录的文件夹就是分类：页面头部点"新建文件夹"即新建一个分类（带序号）。
  // 进入分类后点则是该分类内的子文件夹。两种语义不同，在 submitNewFolder 里分流。
  showNewFolderModal.value = true
}

// 依据现有分类目录的序号前缀，算出下一个分类编号（如 01..06 → 07）
const nextCategorySequence = () => {
  let max = 0
  for (const cat of categories.value) {
    const m = /^(\d+)_/.exec(cat.path)
    if (m) max = Math.max(max, parseInt(m[1], 10))
  }
  return String(max + 1).padStart(2, '0')
}

const submitNewFolder = async () => {
  const name = newFolderName.value.trim()
  if (!name) return

  try {
    let folderPath
    let isCategory
    if (browsing.value) {
      // 在某分类内部：新建子文件夹，沿用当前路径，无序号
      folderPath = `${currentPath.value}/${name}`
      isCategory = false
    } else {
      // 在归档根目录：新建即新建一个分类，自动补上序号前缀
      folderPath = `${nextCategorySequence()}_${name}`
      isCategory = true
    }

    const result = await post('/api/create-folder', { path: folderPath })
    if (result.success) {
      success(isCategory ? '创建分类成功' : '创建文件夹成功')
      showNewFolderModal.value = false
      newFolderName.value = ''
      if (isCategory) {
        // 回读磁盘，让新分类卡片立即出现（刷新后也不丢）
        await loadCategories()
        await fetchCategoryCounts()
      } else {
        await renderBrowserContent(currentPath.value)
      }
    } else {
      error(result.message || '创建失败')
    }
  } catch (e) {
    console.error('创建文件夹失败:', e)
    error('创建文件夹失败')
  }
}

onMounted(async () => {
  await loadCategories()
  await fetchCategoryCounts()
})

onActivated(async () => {
  await loadCategories()
  await fetchCategoryCounts()
})

watch(searchKeyword, () => {
  currentPage.value = 1
})
</script>

<template>
  <div class="archive-view">
    <div class="page-header">
      <h2>归档管理</h2>
      <div class="header-actions">
        <input
          v-model="searchKeyword"
          type="text"
          class="form-input"
          :placeholder="browsing ? '搜索该分类下全部文件夹与文件...' : '搜索归档内全部文件夹与文件...'"
          style="width: 240px;"
        />
        <button class="btn-secondary" @click="exportAll">导出备份</button>
        <button
          class="btn-secondary"
          :title="browsing ? `在 /${currentPath} 下新建子文件夹` : '在归档根目录新建一个分类（自动编号）'"
          @click="handleNewFolder"
        >
          新建文件夹
        </button>
      </div>
    </div>

    <!-- 搜索结果：递归匹配所有子目录里的文件夹与文件（像本地搜索） -->
    <div v-if="searchMode" class="search-panel">
      <div class="search-summary">
        <span v-if="searchLoading">搜索中…</span>
        <template v-else>
          <span>找到 <b>{{ searchResults.length }}</b> 项</span>
          <span class="search-scope">范围：{{ browsing ? '/' + currentPath : '全部归档' }}</span>
          <span v-if="searchTruncated" class="search-warn">结果过多，仅显示前 300 项，请缩小关键词</span>
        </template>
      </div>

      <div v-if="!searchLoading && searchResults.length === 0" class="empty-state">
        <p>没有找到匹配的文件夹或文件</p>
      </div>

      <div v-else class="search-list">
        <div
          v-for="item in searchResults"
          :key="item.path"
          class="search-row"
          @click="openSearchResult(item)"
        >
          <div class="search-icon">
            <img
              :src="item.type === 'folder' ? getFolderIconUrl() : getFileIconUrl(item.name)"
              alt=""
              class="native-icon"
            />
          </div>
          <div class="search-main">
            <div class="search-name">
              <span
                v-for="(s, i) in nameSegments(item.name)"
                :key="i"
                :class="{ 'kw-hit': s.hit }"
              >{{ s.text }}</span>
            </div>
            <div class="search-path" :title="item.path">MediaArt_Archives/{{ item.parent ? item.parent + '/' : '' }}</div>
          </div>
          <div class="search-actions" @click.stop>
            <button v-if="item.type === 'file'" class="btn-text" @click="previewArchiveFile(item)">预览</button>
            <button class="btn-text" @click="locateResult(item)">定位</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 归档分类卡片 -->
    <div v-else-if="!browsing" class="archive-categories">
      <div
        v-for="cat in categories"
        :key="cat.id"
        class="archive-category-card"
        :class="{ 'has-files': categoryHasFiles[cat.id] }"
        @click="browseCategory(cat.path)"
      >
        <div class="category-info">
          <div class="category-name">{{ cat.name }}</div>
          <div class="category-desc">{{ cat.description }}</div>
        </div>
        <div class="category-count">
          {{ categoryCounts[cat.id] || '加载中...' }}
        </div>
      </div>
    </div>

    <!-- 文件浏览区域 -->
    <div v-else class="archive-browser-panel">
      <div class="browser-header">
        <button class="btn-secondary" @click="goBack">← 返回上一级</button>
        <div class="browser-path">/{{ currentPath }}</div>
        <div class="browser-header-actions">
          <button class="btn-secondary" @click="handleNewFolder">新建文件夹</button>
          <button class="btn-primary" @click="showUploadModal = true">上传文件</button>
        </div>
      </div>

      <div class="browser-content">
        <div v-if="loading" class="empty-state">加载中...</div>

        <div v-else-if="files.length === 0" class="empty-state">
          <p>该目录为空</p>
          <p style="font-size: 12px; color: var(--text-tertiary); margin-top: 8px;">
            实际路径: MediaArt_Archives/{{ currentPath }}
          </p>
        </div>

        <div v-else>
          <div class="browser-toolbar">
            <span class="browser-stats">
              {{ folders.length }} 个文件夹，{{ fileItems.length }} 个文件
            </span>
            <button class="btn-secondary btn-sm" @click="refresh">刷新</button>
          </div>

          <div class="browser-file-grid">
            <div
              v-for="item in paginatedItems"
              :key="item.path"
              class="browser-file-item"
              :class="{ 'has-files': item.type === 'folder' && item.fileCount > 0, 'file-item': item.type === 'file' }"
              @click="item.type === 'folder' ? openFolder(item.path) : openArchiveFile(item.path)"
            >
              <div class="file-actions">
                <button
                  v-if="item.type === 'folder'"
                  class="folder-action-btn rename"
                  @click.stop="renameFolder(item.path, item.name)"
                  title="重命名"
                >
                  ✎
                </button>
                <button
                  v-if="item.type === 'file'"
                  class="folder-action-btn rename"
                  @click.stop="renameFile(item.path, item.name)"
                  title="重命名文件"
                >
                  ✎
                </button>
                <button
                  v-if="item.type === 'file'"
                  class="folder-action-btn rename"
                  @click.stop="previewArchiveFile(item)"
                  title="预览"
                >
                  🔍
                </button>
                <button
                  v-if="item.type === 'file'"
                  class="folder-action-btn rename"
                  @click.stop="openArchiveFile(item.path)"
                  title="用本地软件打开"
                >
                  👁
                </button>
                <button
                  class="folder-action-btn delete"
                  @click.stop="item.type === 'folder' ? deleteFolder(item.path, item.name) : deleteFile(item.path)"
                  title="删除"
                >
                  ✕
                </button>
              </div>
              <div class="file-icon">
                <img :src="item.type === 'folder' ? getFolderIconUrl() : getFileIconUrl(item.name)" :alt="item.type" class="native-icon" />
              </div>
              <div class="file-name">{{ item.name }}</div>
              <div
                v-if="item.type === 'folder'"
                class="file-meta"
                :class="{
                  'has-files': item.fileCount > 0,
                  'empty': item.fileCount !== undefined && item.fileCount === 0
                }"
              >
                {{ item.fileCount !== undefined ? (item.fileCount > 0 ? `${item.fileCount} 个文件` : '空文件夹') : '统计中...' }}
              </div>
            </div>
          </div>

          <div v-if="totalPages > 1" class="pagination">
            <button
              class="pagination-btn"
              :disabled="currentPage === 1"
              @click="goToPage(currentPage - 1)"
            >‹</button>
            <button
              v-for="page in visiblePages"
              :key="page"
              class="pagination-btn"
              :class="{ active: page === currentPage }"
              @click="goToPage(page)"
            >{{ page }}</button>
            <button
              class="pagination-btn"
              :disabled="currentPage === totalPages"
              @click="goToPage(currentPage + 1)"
            >›</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传文件模态框 -->
    <Modal
      :show="showUploadModal"
      title="上传文件"
      size="medium"
      @close="showUploadModal = false"
    >
      <div class="form-group">
        <label class="form-label">目标路径</label>
        <div class="current-path">{{ currentPath }}</div>
      </div>
      <div class="form-group">
        <label class="form-label">文档标题</label>
        <input
          type="text"
          v-model="uploadTitle"
          class="form-input"
          placeholder="如：春季展演策划方案（用于区分同目录内的文档）"
        />
        <p style="font-size: 12px; color: var(--text-tertiary); margin: 6px 0 0;">
          最终文件名 = 主体_标题_日期.扩展名（主体与日期自动补）
        </p>
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
        <button class="btn-primary" @click="submitUpload" :disabled="!uploadFile">上传</button>
      </template>
    </Modal>

    <!-- 新建文件夹模态框 -->
    <Modal
      :show="showNewFolderModal"
      title="新建文件夹"
      size="small"
      @close="showNewFolderModal = false"
    >
      <div class="form-group">
        <label class="form-label">文件夹名称</label>
        <input
          type="text"
          v-model="newFolderName"
          class="form-input"
          placeholder="请输入文件夹名称"
          @keyup.enter="submitNewFolder"
        />
      </div>
      <template #footer>
        <button class="btn-secondary" @click="showNewFolderModal = false">取消</button>
        <button class="btn-primary" @click="submitNewFolder" :disabled="!newFolderName.trim()">创建</button>
      </template>
    </Modal>

    <!-- 文件预览（归档页此前只能"用本地软件打开"） -->
    <FilePreviewPanel
      v-model="showPreview"
      source="file"
      :file-name="previewTarget.fileName"
      :file-path="previewTarget.filePath"
    />
  </div>
</template>

<style scoped>
.archive-view {
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
  flex-wrap: wrap;
}

/* 搜索结果：递归匹配所有子目录（像本地文件管理器搜索） */
.search-panel { background: var(--surface); border: 1px solid var(--border-light); border-radius: 10px; overflow: hidden; }
.search-summary { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 16px; background: var(--bg-secondary); font-size: 13px; color: var(--text-secondary); }
.search-summary b { color: var(--accent); }
.search-scope { color: var(--text-tertiary); }
.search-warn { color: var(--danger); }
.search-list { display: flex; flex-direction: column; }
.search-row { display: flex; align-items: center; gap: 12px; padding: 10px 16px; cursor: pointer; border-top: 1px solid var(--border-light); transition: background var(--transition-fast); }
.search-row:hover { background: var(--bg-hover); }
.search-icon .native-icon { width: 28px; height: 28px; object-fit: contain; display: block; }
.search-main { flex: 1; min-width: 0; }
.search-name { font-size: 14px; color: var(--text-primary); word-break: break-all; }
.search-name .kw-hit { background: var(--accent-light); color: var(--accent); font-weight: 600; border-radius: 3px; }
.search-path { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; word-break: break-all; }
.search-actions { display: flex; gap: 4px; flex-shrink: 0; }
/* 行内文字按钮：模板里用了 .btn-text，但本组件此前没定义它 ——
   浏览器按默认按钮渲染（灰底方框），和系统其它页面的文字按钮完全不是一个观感。
   这里对齐资源中心 .btn-link 的写法：无边框、主色文字、悬停浅底。 */
.search-actions .btn-text {
  padding: 4px 10px; background: none; border: none; border-radius: var(--radius-sm);
  color: var(--accent); font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all var(--transition-fast);
}
.search-actions .btn-text:hover { background: var(--accent-light); }

.archive-categories {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.archive-category-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  background: var(--surface);
  border-radius: 10px;
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: all 0.2s;
}

.archive-category-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

/* 有文件的分类同样绿色高亮（同理需放在 :hover 之后才能压住悬停样式） */
.archive-category-card.has-files,
.archive-category-card.has-files:hover {
  background: var(--success-light);
  border-color: var(--success);
  box-shadow: inset 3px 0 0 var(--success);
}

.archive-category-card.has-files .category-count {
  color: var(--success);
  font-weight: 600;
}

.category-info {
  flex: 1;
}

.category-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.category-desc {
  font-size: 13px;
  color: var(--text-secondary);
}

.category-count {
  font-size: 13px;
  color: var(--text-tertiary);
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  white-space: nowrap;
}

.archive-browser-panel {
  background: var(--surface);
  border-radius: 10px;
  border: 1px solid var(--border-light);
  overflow: hidden;
}

.browser-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-secondary);
}

/* 操作按钮靠右。此前写在 <template> 的 style 上——<template> 不渲染元素，
   该属性无效（lint 报 vue/no-useless-template-attributes），布局意图也丢了。 */
.browser-header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.browser-path {
  font-size: 14px;
  color: var(--text-secondary);
  font-family: monospace;
}

.browser-content {
  padding: 16px;
  min-height: 300px;
}

.browser-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}

.browser-stats {
  font-size: 13px;
  color: var(--text-secondary);
}

.browser-file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.browser-file-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
  position: relative;
}

.browser-file-item:hover {
  background: var(--bg-tertiary);
  transform: translateY(-2px);
}

.browser-file-item .file-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.native-icon {
  width: 48px;
  height: 48px;
  object-fit: contain;
  image-rendering: auto;
}

.browser-file-item .file-name {
  font-size: 13px;
  color: var(--text-primary);
  word-break: break-all;
  line-height: 1.4;
  padding-right: 8px;
  padding-left: 8px;
}

.browser-file-item .file-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.browser-file-item .file-meta.has-files {
  color: var(--success);
}

.browser-file-item .file-meta.empty {
  color: var(--text-tertiary);
}

/* 有文件的文件夹：绿色高亮，一眼看出哪些目录里已经有内容。
   注意要放在 :hover 之后——两者特异性相同，靠源码顺序决定胜负，
   否则鼠标悬停时会被灰底覆盖掉绿色。 */
.browser-file-item.has-files,
.browser-file-item.has-files:hover {
  background: var(--success-light);
  border-left: 3px solid var(--success);
  box-shadow: inset 0 0 0 1px var(--success);
}

.browser-file-item.has-files .file-name {
  color: var(--success);
  font-weight: 600;
}

/* 有文件的文件夹图标也染一点绿，和整体高亮呼应。
   原本写在全局 style.css 的 .browser-file-item.has-files .file-icon 上，
   现收回组件作用域，避免与深色主题的 !important 规则打架。 */
.browser-file-item.has-files .file-icon {
  filter: hue-rotate(60deg);
}

.browser-file-item.file-item {
  background: var(--surface);
}

.browser-file-item .file-actions {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.browser-file-item:hover .file-actions {
  opacity: 1;
}

.folder-action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all var(--transition-fast);
  color: var(--text-secondary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.folder-action-btn:hover {
  transform: scale(1.1);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

.folder-action-btn.rename:hover {
  background: var(--accent-light);
  color: var(--accent);
}

.folder-action-btn.delete:hover {
  background: #fef2f2;
  color: var(--danger);
}

[data-theme="dark"] .folder-action-btn {
  background: var(--bg-tertiary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
  font-size: 14px;
}

.form-input {
  padding: 8px 12px;
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

.current-path {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-family: monospace;
  font-size: 13px;
  color: var(--text-secondary);
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
  padding: 6px 12px;
  font-size: 13px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
}

.pagination-btn {
  min-width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.pagination-btn:hover:not(:disabled):not(.active) {
  border-color: var(--accent);
  color: var(--accent);
}

.pagination-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.pagination-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
