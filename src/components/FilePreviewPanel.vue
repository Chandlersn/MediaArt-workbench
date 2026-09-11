<template>
  <Transition name="preview-slide">
    <div v-if="modelValue" class="preview-panel-overlay" @click.self="close">
      <div class="preview-panel">
        <div class="preview-header">
          <div class="preview-title-row">
            <span class="preview-file-icon">{{ fileIcon }}</span>
            <h3>{{ displayName }}</h3>
          </div>
          <div class="preview-header-actions">
            <button
              v-if="showDownloadButton"
              class="btn-download-sm"
              title="下载"
              @click="handleDownload"
            >⬇</button>
            <button class="btn-close" title="关闭（Esc）" @click="close">×</button>
          </div>
        </div>

        <div class="preview-body">
          <div v-if="loading" class="preview-status">正在加载…</div>

          <div v-else-if="error" class="preview-fallback">
            <div class="fallback-icon">⚠</div>
            <p>{{ error }}</p>
            <p class="file-meta">{{ displayName }}（{{ extLabel }}）</p>
            <button class="btn-download" @click="handleDownload">下载文件</button>
          </div>

          <img
            v-else-if="kind === 'image'"
            :src="objectUrl"
            :class="['preview-image', { zoomed }]"
            :title="zoomed ? '点击缩小' : '点击放大'"
            alt="预览图片"
            @click="zoomed = !zoomed"
          />
          <iframe v-else-if="kind === 'pdf'" :src="objectUrl" class="preview-iframe"></iframe>
          <video v-else-if="kind === 'video'" :src="objectUrl" controls class="preview-video"></video>
          <audio v-else-if="kind === 'audio'" :src="objectUrl" controls class="preview-audio"></audio>
          <pre v-else-if="kind === 'text'" class="preview-text">{{ text }}</pre>

          <div v-else class="preview-fallback">
            <div class="fallback-icon">📄</div>
            <p>{{ notPreviewableMessage }}</p>
            <p class="file-meta">{{ displayName }}（{{ extLabel }}）</p>
            <button class="btn-download" @click="handleDownload">下载文件</button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { get, getBlob } from '../services/http.js'

/**
 * 通用文件预览面板（侧边滑入）
 *
 * 三处详情页与归档/素材库共用同一份实现——此前这段 UI 在三处各复制了一份，
 * 且各自的接口 URL 构造不一致，直接导致"选手/项目预览恒 404"。
 *
 * 关键点：媒体文件不能用 <img src="/api/..."> 直接加载——元素级请求浏览器
 * 不带 Authorization 头，而下载类接口都要求 JWT，会拿到 401。这里统一用
 * getBlob() 取回二进制再 createObjectURL，关闭时 revoke。
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 'player' | 'project' | 'org' | 'file'
  // file 用于归档页/素材库，按相对路径取文件
  source: { type: String, required: true },
  ownerName: { type: String, default: '' },
  fileName: { type: String, default: '' },
  materialType: { type: String, default: '' },
  filePath: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue'])

const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico']
const PDF_EXTS = ['pdf']
const VIDEO_EXTS = ['mp4', 'webm', 'mov', 'avi', 'mkv']
const AUDIO_EXTS = ['mp3', 'wav', 'ogg', 'm4a', 'flac']
const TEXT_EXTS = [
  'txt', 'md', 'markdown', 'json', 'xml', 'csv', 'tsv', 'log',
  'html', 'htm', 'css', 'js', 'ts', 'yml', 'yaml', 'ini', 'cfg',
  'conf', 'py', 'java', 'sql', 'sh', 'bat', 'ps1', 'srt', 'vtt'
]
const OFFICE_EXTS = ['doc', 'docx', 'docm', 'xls', 'xlsx', 'xlsm', 'ppt', 'pptx', 'pptm']

const ICON_MAP = {
  pdf: '📕', doc: '📘', docx: '📘', docm: '📘',
  xls: '📗', xlsx: '📗', xlsm: '📗', ppt: '📙', pptx: '📙', pptm: '📙',
  txt: '📝', md: '📝', markdown: '📝', csv: '📊', tsv: '📊', json: '📋',
  xml: '📋', yml: '📋', yaml: '📋', log: '📜',
  zip: '📦', rar: '📦', '7z': '📦',
  mp4: '🎬', webm: '🎬', mov: '🎬', avi: '🎬', mkv: '🎬',
  mp3: '🎵', wav: '🎵', ogg: '🎵', m4a: '🎵', flac: '🎵',
  jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', svg: '🖼️',
  webp: '🖼️', bmp: '🖼️', ico: '🖼️'
}

const loading = ref(false)
const error = ref('')
const text = ref('')
const objectUrl = ref('')
const zoomed = ref(false)

const displayName = computed(() =>
  props.fileName || props.filePath.split('/').pop() || '未命名文件'
)

const ext = computed(() => {
  const name = displayName.value
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : ''
})

const extLabel = computed(() => ext.value.toUpperCase() || '未知')

const fileIcon = computed(() => ICON_MAP[ext.value] || '📄')

const kind = computed(() => {
  const e = ext.value
  if (IMAGE_EXTS.includes(e)) return 'image'
  if (PDF_EXTS.includes(e)) return 'pdf'
  if (VIDEO_EXTS.includes(e)) return 'video'
  if (AUDIO_EXTS.includes(e)) return 'audio'
  if (TEXT_EXTS.includes(e) || OFFICE_EXTS.includes(e)) return 'text'
  return 'unknown'
})

// 与原有面板保持一致：图片/视频不显示下载按钮（可用右键或播放器另存）
const showDownloadButton = computed(() => kind.value !== 'image' && kind.value !== 'video')

const notPreviewableMessage = computed(() =>
  text.value || '此文件类型暂不支持在线预览'
)

const mediaEndpoint = computed(() => {
  if (props.source === 'file') return 'get-file'
  if (props.source === 'org') return 'get-org-material'
  if (props.source === 'player') return 'download-player-material'
  return 'download-project-material'
})

/** 统一构造媒体地址——所有页面共用同一套参数，杜绝各页各写一套 */
const mediaUrl = computed(() => {
  const p = new URLSearchParams()
  if (props.source === 'file') {
    p.set('path', props.filePath)
  } else if (props.source === 'org') {
    p.set('orgName', props.ownerName)
    p.set('fileName', props.fileName)
    p.set('materialType', props.materialType)
  } else if (props.source === 'player') {
    p.set('playerName', props.ownerName)
    p.set('fileName', props.fileName)
    p.set('materialType', props.materialType)
    p.set('preview', 'true')
  } else {
    p.set('projectName', props.ownerName)
    p.set('fileName', props.fileName)
    p.set('materialType', props.materialType)
    p.set('preview', 'true')
  }
  return `/api/${mediaEndpoint.value}?${p.toString()}`
})

const textUrl = computed(() => {
  const p = new URLSearchParams()
  p.set('source', props.source)
  p.set('fileName', props.fileName)
  if (props.source === 'file') {
    p.set('path', props.filePath)
  } else {
    p.set('name', props.ownerName)
    p.set('materialType', props.materialType)
  }
  return `/api/preview-text?${p.toString()}`
})

const revokeObjectUrl = () => {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = ''
  }
}

// 已加载的"来源+文件"签名，避免打开面板时两个 watcher 各触发一次重复请求
const loadedSignature = ref('')
const currentSignature = computed(() =>
  `${props.source}|${props.ownerName}|${props.filePath}|${props.fileName}`
)

const load = async () => {
  revokeObjectUrl()
  error.value = ''
  text.value = ''
  zoomed.value = false
  loadedSignature.value = currentSignature.value

  const k = kind.value
  if (k === 'unknown') return

  // 兜底分支没有可加载的内容，直接展示提示
  loading.value = true
  try {
    if (k === 'text') {
      const res = await get(textUrl.value)
      if (res && res.success) {
        text.value = res.text + (res.truncated ? '\n\n--- 内容过长，仅显示前 100000 字符 ---' : '')
      } else {
        text.value = res && res.message ? res.message : '无法提取文件内容'
      }
    } else {
      const blob = await getBlob(mediaUrl.value)
      objectUrl.value = URL.createObjectURL(blob)
    }
  } catch (e) {
    console.warn('预览加载失败:', e)
    error.value = e && e.message ? `加载失败：${e.message}` : '加载失败，请重试或下载后查看'
  } finally {
    loading.value = false
  }
}

const close = () => {
  emit('update:modelValue', false)
}

const handleDownload = async () => {
  try {
    const blob = objectUrl.value
      ? await fetch(objectUrl.value).then(r => r.blob())
      : await getBlob(mediaUrl.value)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = displayName.value
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.warn('下载失败:', e)
    error.value = e && e.message ? `下载失败：${e.message}` : '下载失败'
  }
}

const handleKeydown = (event) => {
  if (!props.modelValue) return
  if (event.key === 'Escape') close()
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      load()
    } else {
      revokeObjectUrl()
      text.value = ''
      error.value = ''
      loadedSignature.value = ''
    }
  }
)

// 面板已打开时切换到另一个文件才重新加载
watch(
  () => currentSignature.value,
  () => {
    if (props.modelValue && currentSignature.value !== loadedSignature.value) load()
  }
)

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  revokeObjectUrl()
})
</script>

<style scoped>
.preview-panel-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: flex-start;
  z-index: 9999;
  padding: 40px 20px 40px 40px;
}

.preview-panel {
  background: var(--surface, #fff);
  border-radius: 12px;
  width: 65vw;
  max-width: 900px;
  min-width: 400px;
  height: calc(100vh - 80px);
  max-height: calc(100vh - 80px);
  display: flex;
  flex-direction: column;
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.35);
  overflow: hidden;
  animation: panelSlideIn 0.25s ease-out;
}

@keyframes panelSlideIn {
  from { transform: translateX(-30px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

[data-theme="dark"] .preview-panel {
  background: var(--surface, #1e293b);
  border: 1px solid var(--border, #334155);
}

.preview-panel .preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border, #e2e8f0);
  flex-shrink: 0;
  gap: 12px;
}

[data-theme="dark"] .preview-panel .preview-header {
  border-bottom-color: var(--border, #334155);
}

.preview-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.preview-file-icon {
  font-size: 22px;
  flex-shrink: 0;
}

.preview-panel .preview-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.btn-download-sm {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-light, #e2e8f0);
  background: var(--bg-secondary, #f8fafc);
  color: var(--text-primary, #0f172a);
  font-size: 16px;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-download-sm:hover {
  background: var(--bg-tertiary, #e2e8f0);
  border-color: var(--text-tertiary, #94a3b8);
}

.preview-panel .btn-close {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-tertiary, #94a3b8);
  transition: all 0.15s;
}

.preview-panel .btn-close:hover {
  background: var(--bg-tertiary, #e2e8f0);
  color: var(--text-primary, #0f172a);
}

.preview-body {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  min-height: 0;
}

.preview-status {
  color: var(--text-secondary, #64748b);
  font-size: 14px;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  cursor: zoom-in;
  transition: transform 0.2s ease;
}

.preview-image.zoomed {
  max-width: none;
  max-height: none;
  width: auto;
  cursor: zoom-out;
}

.preview-iframe {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 4px;
}

.preview-video {
  max-width: 100%;
  max-height: 100%;
  border-radius: 8px;
}

.preview-audio {
  width: 100%;
  outline: none;
}

.preview-text {
  width: 100%;
  margin: 0;
  padding: 24px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.7;
  background: var(--bg-secondary, #f8fafc);
  color: var(--text-primary, #0f172a);
  white-space: pre-wrap;
  word-break: break-all;
  border-radius: 6px;
  overflow: auto;
}

[data-theme="dark"] .preview-text {
  background: var(--bg-tertiary, #334155);
  color: #e2e8f0;
}

.preview-fallback {
  text-align: center;
  padding: 48px 24px;
  color: var(--text-secondary, #64748b);
}

.fallback-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.preview-fallback p {
  margin: 8px 0;
  font-size: 14px;
}

.file-meta {
  font-size: 13px !important;
  color: var(--text-tertiary, #94a3b8) !important;
  margin-top: 4px !important;
}

.preview-fallback .btn-download {
  display: inline-block;
  margin-top: 20px;
  padding: 10px 24px;
  background: var(--primary, #3b82f6);
  color: #fff;
  border-radius: 8px;
  border: none;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}

.preview-fallback .btn-download:hover {
  opacity: 0.9;
}

.preview-slide-enter-active {
  transition: opacity 0.2s ease;
}
.preview-slide-leave-active {
  transition: opacity 0.15s ease;
}
.preview-slide-enter-from,
.preview-slide-leave-to {
  opacity: 0;
}
</style>
