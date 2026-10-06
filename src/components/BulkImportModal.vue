<template>
  <Modal :show="show" :title="`批量导入${entityLabel}`" size="medium" @close="handleClose">
    <!-- 第一步：下载模板 -->
    <div v-if="step === 1">
      <p class="bi-lead">第一步：下载导入模板，按表头填写后另存为 CSV</p>
      <button class="btn-secondary" @click="downloadTemplate">下载 CSV 模板</button>
      <p class="bi-hint">
        表头必须保留，列顺序可调整。导入时按<strong>表头名称</strong>识别字段，不看列位置。
      </p>
    </div>

    <!-- 第二步：选择文件 -->
    <div v-if="step === 2">
      <p class="bi-lead">第二步：选择填好的 CSV 文件</p>
      <FileDropArea accept=".csv" :file-name="file?.name" @change="onFileSelect" />
      <p class="bi-hint">支持 UTF-8 与 GBK 编码；同名的{{
        entityLabel }}会自动跳过，不会重复创建。</p>
    </div>

    <!-- 第三步：预览 -->
    <div v-if="step === 3">
      <p class="bi-lead">
        第三步：预览前 {{ previewRows.length }} 行<span v-if="rows.length > previewRows.length">
          （共 {{ rows.length }} 行）</span>
      </p>
      <div v-if="previewRows.length" class="bi-table-wrap">
        <table class="bi-table">
          <thead>
            <tr><th v-for="h in headers" :key="h">{{ h }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in previewRows" :key="i">
              <td v-for="h in headers" :key="h">{{ row[h] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="bi-empty">文件里没有可导入的数据行（只有表头？）</p>
    </div>

    <!-- 第四步：结果 -->
    <div v-if="step === 4">
      <p class="bi-lead">导入结果</p>
      <p class="bi-result-ok">成功导入：{{ result.imported }} 条</p>
      <p v-if="result.failed > 0" class="bi-result-fail">跳过 / 失败：{{ result.failed }} 条</p>
      <div v-if="result.errors?.length" class="bi-errors">
        <p class="bi-errors-title">未导入明细：</p>
        <ul>
          <li v-for="(err, i) in result.errors.slice(0, 30)" :key="i">{{ err }}</li>
        </ul>
        <p v-if="result.errors.length > 30" class="bi-hint">
          还有 {{ result.errors.length - 30 }} 条未列出
        </p>
      </div>
    </div>

    <template #footer>
      <template v-if="step === 1">
        <button class="btn-secondary" @click="handleClose">取消</button>
        <button class="btn-secondary" @click="step = 2">我已填好，去上传</button>
      </template>
      <template v-else-if="step === 2">
        <button class="btn-secondary" @click="step = 1">上一步</button>
        <button class="btn-primary" :disabled="!file" @click="goPreview">预览</button>
      </template>
      <template v-else-if="step === 3">
        <button class="btn-secondary" @click="step = 2">上一步</button>
        <button class="btn-primary" :disabled="!rows.length || busy" @click="submit">
          {{ busy ? '导入中…' : `确认导入 ${rows.length} 条` }}
        </button>
      </template>
      <template v-else>
        <button class="btn-primary" @click="handleClose">完成</button>
      </template>
    </template>
  </Modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import Modal from './Modal.vue'
import FileDropArea from './FileDropArea.vue'
import { fetchWithAuth } from '../services/http.js'
import { useToast } from '../composables/useToast'

/**
 * 通用批量导入弹窗（下载模板 → 上传 CSV → 预览 → 导入结果）。
 *
 * 抽成组件而非在各列表页各写一遍：四步流程 + CSV 解析 + 结果展示有 100+ 行，
 * 复制三份意味着以后改一处要改三处（本项目已有「两套实现会漂移」的教训）。
 *
 * 父组件只负责：`v-model:show` 控制显隐、`entity` 描述实体、
 * `@imported` 收到成功回调后刷新自己的列表。
 */
const props = defineProps({
  show: { type: Boolean, default: false },
  /** 实体配置：label 中文名 / endpoint 接口路径 / payloadKey 请求体字段名 / template 模板表头 */
  entity: { type: Object, required: true }
})

const emit = defineEmits(['update:show', 'imported'])

const { error: toastError } = useToast()

const step = ref(1)
const file = ref(null)
const headers = ref([])
const rows = ref([])
const result = ref({ imported: 0, failed: 0, errors: [] })
const busy = ref(false)

const entityLabel = computed(() => props.entity?.label || '数据')
const previewRows = computed(() => rows.value.slice(0, 5))

// 每次打开都回到第一步，避免上次的结果/文件残留
watch(() => props.show, (open) => {
  if (open) reset()
})

const reset = () => {
  step.value = 1
  file.value = null
  headers.value = []
  rows.value = []
  result.value = { imported: 0, failed: 0, errors: [] }
  busy.value = false
}

const handleClose = () => {
  emit('update:show', false)
}

const downloadTemplate = () => {
  const text = props.entity.template || ''
  // BOM 前置：Excel 打开无 BOM 的 UTF-8 CSV 会把中文显示成乱码
  const blob = new Blob([`\uFEFF${text}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${entityLabel.value}导入模板.csv`
  a.click()
  URL.revokeObjectURL(url)
}

const onFileSelect = (e) => {
  file.value = e.target.files?.[0] || null
}

/**
 * 解析 CSV。
 *
 * ⚠️ 必须自己处理引号：机构名/项目名里出现英文逗号是常事
 * （如 `机构A,分院`），简单 split(',') 会把一个字段切成两列，
 * 后面所有列都错位 —— 这类错误在预览里往往看不出，直到落库才发现。
 */
const parseCsv = (text) => {
  const lines = text.replace(/\r\n?/g, '\n').split('\n').filter((l) => l.trim() !== '')
  if (lines.length < 2) return { headers: [], rows: [] }

  const splitLine = (line) => {
    const out = []
    let cur = ''
    let inQuotes = false
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i]
      if (inQuotes) {
        if (ch === '"') {
          if (line[i + 1] === '"') { cur += '"'; i += 1 } // 转义的双引号
          else inQuotes = false
        } else cur += ch
      } else if (ch === '"') {
        inQuotes = true
      } else if (ch === ',') {
        out.push(cur)
        cur = ''
      } else {
        cur += ch
      }
    }
    out.push(cur)
    return out.map((v) => v.trim())
  }

  const head = splitLine(lines[0])
  const data = []
  for (let i = 1; i < lines.length; i += 1) {
    const values = splitLine(lines[i])
    // 整行全空则跳过（尾部多余空行）
    if (values.every((v) => v === '')) continue
    const row = {}
    head.forEach((h, j) => { row[h] = values[j] || '' })
    data.push(row)
  }
  return { headers: head, rows: data }
}

const goPreview = () => {
  if (!file.value) return
  const reader = new FileReader()
  reader.onload = (e) => {
    const parsed = parseCsv(String(e.target.result || ''))
    headers.value = parsed.headers
    rows.value = parsed.rows
    step.value = 3
  }
  reader.onerror = () => toastError('文件读取失败，请重新选择')
  reader.readAsText(file.value, 'utf-8')
}

const submit = async () => {
  if (!rows.value.length || busy.value) return
  busy.value = true
  try {
    const response = await fetchWithAuth(props.entity.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [props.entity.payloadKey]: rows.value })
    })
    const data = await response.json()
    if (data.success) {
      result.value = data
      step.value = 4
      if (data.imported > 0) emit('imported', data)
    } else {
      toastError(data.message || data.error || '导入失败')
    }
  } catch (e) {
    console.error('导入失败:', e)
    result.value = { imported: 0, failed: rows.value.length, errors: [e.message] }
    step.value = 4
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.bi-lead {
  margin-bottom: 12px;
  font-size: 14px;
  color: var(--text-primary);
}
.bi-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.6;
}
.bi-table-wrap {
  max-height: 260px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.bi-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.bi-table th,
.bi-table td {
  padding: 7px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border-light, var(--border));
  white-space: nowrap;
}
.bi-table th {
  position: sticky;
  top: 0;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 500;
}
.bi-empty {
  font-size: 13px;
  color: var(--text-tertiary);
}
.bi-result-ok {
  font-size: 14px;
  color: var(--text-primary);
}
.bi-result-fail {
  margin-top: 6px;
  font-size: 14px;
  color: var(--danger, #d9534f);
}
.bi-errors {
  margin-top: 12px;
}
.bi-errors-title {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.bi-errors ul {
  margin: 0;
  padding-left: 18px;
  max-height: 200px;
  overflow: auto;
  font-size: 13px;
  color: var(--danger, #d9534f);
  line-height: 1.7;
}
</style>
