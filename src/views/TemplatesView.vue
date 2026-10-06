<template>
  <div class="templates-page">
    <div class="page-header">
      <h2>模板管理</h2>
      <div class="header-actions">
        <button v-if="!editor" class="btn-primary btn-sm" @click="newTpl">新建打印模板</button>
        <button v-else class="btn-secondary btn-sm" @click="closeEditor">返回列表</button>
      </div>
    </div>

    <div class="panel-desc intro" v-if="!editor">
      底图承载版式，字段承载数据：先上传设计好的证书底图，再从数据库字段里勾选要打印的内容并拖到正确位置。
      批量打印入口在「证书管理」台账：勾选证书 → 批量打印；打印留痕与归档件在「打印中心」查看。
    </div>

    <!-- ================= 模板列表 ================= -->
    <template v-if="!editor">
      <div v-if="templates.length === 0" class="empty-state">
        还没有打印模板。点击右上角「新建打印模板」，上传底图即可开始。
      </div>
      <div v-else class="tpl-grid">
        <div v-for="t in templates" :key="t.id" class="tpl-card">
          <div class="tpl-thumb" :style="{ aspectRatio: thumbRatio(t) }">
            <img v-if="t.background" :src="'/' + t.background" alt="" />
            <span v-else class="muted">无底图</span>
          </div>
          <div class="tpl-meta">
            <strong>{{ t.name }}</strong>
            <span class="muted">{{ DOC_TYPE_LABELS[t.docType] || t.docType }} · {{ (t.fields || []).length }} 个字段</span>
          </div>
          <div class="tpl-actions">
            <button class="btn-text" @click="editTpl(t)">编辑</button>
            <button class="btn-text danger" @click="removeTpl(t)">删除</button>
          </div>
        </div>
      </div>
    </template>

    <!-- ================= 模板编辑器 ================= -->
    <template v-else>
      <div class="panel">
        <div class="panel-title">{{ isNew ? '新建打印模板' : '编辑打印模板' }}</div>
        <div class="editor-form">
          <label class="field">
            模板名称
            <input v-model="editor.name" class="form-input" style="width: 220px" placeholder="如：2026 省级展演获奖证书" />
          </label>
          <label class="field">
            文档类型
            <CustomSelect v-model="editor.docType" style="width: 120px">
              <option value="certificate">证书</option>
              <option value="roster">名单</option>
              <option value="report">报表</option>
            </CustomSelect>
          </label>
          <label class="field">
            底图
            <FileDropArea
              accept=".png,.jpg,.jpeg"
              :button-text="editor.background ? '重新上传' : '上传底图'"
              hint="或把图片拖到这里"
              @change="onBgChange"
            />
          </label>
          <label class="field">
            纸张
            <CustomSelect v-model="editor.pageSize" style="width: 130px">
              <option v-for="(v, k) in pageSizes" :key="k" :value="k">{{ v.label }}</option>
            </CustomSelect>
          </label>
        </div>
        <div v-if="bgNote" class="bg-note">{{ bgNote }}</div>
        <div v-if="bgRatioWarn" class="bg-note warn">{{ bgRatioWarn }}</div>
      </div>

      <div class="editor-layout">
        <!-- 画布：底图 + 字段框拖拽定位 -->
        <div class="canvas-wrap">
          <div class="canvas-toolbar">
            <button class="btn-text" :disabled="!canUndo" title="Ctrl+Z" @click="undo">撤销</button>
            <button class="btn-text" :disabled="!canRedo" title="Ctrl+Y" @click="redo">重做</button>
            <template v-if="multiSel.length >= 2">
              <span class="tb-sep"></span>
              <span class="muted">已选 {{ multiSel.length }} 个：</span>
              <button class="btn-text" @click="alignLeft">左对齐</button>
              <button class="btn-text" @click="alignCenterX">水平居中</button>
              <button class="btn-text" @click="distributeY">垂直等间距</button>
            </template>
            <span v-else class="muted tb-hint">Ctrl+点击字段可多选批量对齐</span>
          </div>
          <div
            ref="canvasEl"
            class="tpl-canvas"
            :style="{ aspectRatio: canvasRatio }"
            tabindex="0"
            @mousedown.self="clearSelection"
            @keydown="onCanvasKeydown"
          >
            <img v-if="editor.background" :src="'/' + editor.background" class="tpl-bg" alt="" />
            <div v-else class="tpl-bg-empty">请先上传底图</div>
            <div
              v-for="f in editor.fields"
              :key="f.column"
              class="tpl-field"
              :class="{ active: selectedField === f, nodata: !hasPreviewValue(f) }"
              :style="fieldStyle(f)"
              :data-column="f.column"
              :title="hasPreviewValue(f) ? '拖拽调整位置；选中后可用方向键微调；Ctrl+点击多选' : '该字段在台账中暂无数据，打印时将留空'"
              @mousedown.stop="startDrag($event, f)"
              @click.stop="onClickField($event, f)"
            >
              {{ previewText(f) }}
            </div>
            <!-- 对齐辅助线：拖拽贴合画布边缘/中心或其他字段时浮现 -->
            <div v-if="guideV !== null" class="snap-guide guide-v" :style="{ left: guideV + '%' }"></div>
            <div v-if="guideH !== null" class="snap-guide guide-h" :style="{ top: guideH + '%' }"></div>
          </div>
          <div class="muted canvas-tip">拖动字段框定位，贴近画布边缘 / 中心或其他字段会自动吸附并显示辅助线；选中字段后可用方向键微调（Shift + 方向键 = 1% 大步），坐标按百分比保存，换底图不错位。</div>
        </div>

        <!-- 字段勾选 + 选中字段属性 -->
        <div class="editor-side">
          <div class="side-block">
            <div class="side-title">勾选打印字段</div>
            <label
              v-for="f in sortedCatalog"
              :key="f.column"
              class="chk"
              :class="{ zerofill: isZeroFill(f) }"
              :title="isZeroFill(f) ? '台账中暂无该字段数据，打印时将留空' : ''"
            >
              <input
                type="checkbox"
                :checked="hasField(f.column)"
                @change="toggleField(f)"
              />
              <span>{{ f.label }}</span>
              <span v-if="f.fill" class="fill-badge" :class="{ zero: isZeroFill(f) }">{{ f.fill }}</span>
            </label>
          </div>
          <div v-if="selectedField" class="side-block">
            <div class="side-title">字段属性：{{ selectedField.label }}</div>
            <label class="field">
              字号 (pt)
              <input v-model.number="selectedField.fontSize" type="number" min="6" max="96" class="form-input" style="width: 90px" @change="pushUndo" />
            </label>
            <label class="field">
            字体
            <CustomSelect v-model="selectedField.fontFamily" style="width: 150px" @change="pushUndo">
              <option value="">默认字体</option>
              <optgroup v-if="systemFonts.length" label="系统字体">
                <option v-for="s in systemFonts" :key="s.value" :value="s.value">{{ s.label }}</option>
              </optgroup>
              <optgroup v-if="uploadedFonts.length" label="上传字体">
                <option v-for="u in uploadedFonts" :key="u.name" :value="u.name">{{ u.name }}</option>
              </optgroup>
            </CustomSelect>
            </label>
            <label class="field">
            对齐
            <CustomSelect v-model="selectedField.align" style="width: 100px" @change="pushUndo">
              <option value="center">居中</option>
              <option value="left">左对齐</option>
              <option value="right">右对齐</option>
            </CustomSelect>
            </label>
            <label class="field chk-inline">
              加粗
              <input v-model="selectedField.bold" type="checkbox" @change="pushUndo" />
            </label>
            <label class="field">
              颜色
              <input v-model="selectedField.color" type="color" class="form-color" @change="pushUndo" />
            </label>
            <button class="btn-text danger" @click="removeField(selectedField)">移除该字段</button>
          </div>
          <div v-else class="side-block muted">在左侧点击字段框可选中编辑</div>
          <div class="side-block">
            <div class="side-title">字体管理</div>
            <FileDropArea
              accept=".ttf,.otf,.woff,.woff2"
              button-text="上传字体文件"
              hint="或把字体文件拖到这里"
              @change="onFontChange"
            />
            <div v-if="uploadedFonts.length" class="font-list">
              <div v-for="u in uploadedFonts" :key="u.file" class="font-row">
                <span class="font-name" :title="u.file">{{ u.name }}</span>
                <button class="btn-text danger" @click="removeFont(u)">删除</button>
              </div>
            </div>
            <span v-else class="muted">支持 TTF / OTF / WOFF / WOFF2，上传后可在字段属性中选用</span>
          </div>
        </div>
      </div>

      <div class="panel-actions editor-foot">
        <button class="btn-primary" :disabled="savingTpl" @click="saveTpl">{{ savingTpl ? '保存中…' : '保存模板' }}</button>
        <button class="btn-secondary" @click="closeEditor">取消</button>
        <span class="warn-text">保存后到「证书管理」勾选证书即可批量打印</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onActivated, nextTick } from 'vue'
import CustomSelect from '../components/CustomSelect.vue'
import FileDropArea from '../components/FileDropArea.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import * as dataService from '../services/dataService'
import {
  fetchFieldCatalog, uploadBackground, fetchFonts, uploadFont, deleteFont
} from '../services/print'

const { success, error: toastError, warning } = useToast()
const { confirm } = useConfirmDialog()

const DOC_TYPE_LABELS = { certificate: '证书', roster: '名单', report: '报表' }

// ---- 数据 ----
const templates = ref([])
const previewRecord = ref(null)
const catalog = ref([])
const pageSizes = ref({})

// 台账中零填充的字段（如语种 0/3）：灰显 + 沉底，提示打印会留空
const isZeroFill = (f) => !!f.fill && f.fill.startsWith('0/')
const sortedCatalog = computed(() => {
  const list = [...catalog.value]
  return list.sort((a, b) => (isZeroFill(a) ? 1 : 0) - (isZeroFill(b) ? 1 : 0))
})

let templatesRevision = null
let templatesQueue = Promise.resolve()
const enqueueTemplates = (operation) => {
  const result = templatesQueue.then(operation)
  templatesQueue = result.catch(() => {})
  return result
}
const loadTemplates = async () => {
  if (editor.value) return
  try {
    await enqueueTemplates(async () => {
      await dataService.load()
      templates.value = dataService.getData('printTemplates') || []
      templatesRevision = dataService.getRevision('printTemplates')
      previewRecord.value = (dataService.getData('certificates') || [])[0] || null
    })
  } catch (err) {
    toastError('读取模板失败：' + (err.message || err))
  }
}

onMounted(async () => {
  await Promise.all([loadTemplates(), loadFonts()])
  try {
    const res = await fetchFieldCatalog()
    if (res.success) {
      catalog.value = res.fields || []
      pageSizes.value = res.pageSizes || {}
    }
  } catch (e) { toastError('读取字段目录失败：' + (e.message || e)) }
  refreshCanvas()
})
onActivated(async () => { await loadTemplates() })

// ---- 模板编辑 ----
const editor = ref(null)
const isNew = computed(() => editor.value && !templates.value.some(t => t.id === editor.value.id))
const bgNote = ref('')
const savingTpl = ref(false)
const selectedField = ref(null)
const canvasEl = ref(null)
const canvasH = ref(0)

const genId = () => 'pt' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)

const newTpl = () => {
  selectedField.value = null
  multiSel.value = []
  bgNote.value = ''
  bgRatioWarn.value = ''
  resetHistory()
  editor.value = {
    id: genId(), name: '', docType: 'certificate',
    background: '', pageWidth: 0, pageHeight: 0, pageSize: 'A4_L',
    fields: []
  }
  refreshCanvas()
}

const editTpl = (t) => {
  selectedField.value = null
  bgNote.value = ''
  const copy = JSON.parse(JSON.stringify(t))
  // 归一化：旧模板存的可能是历史下划线列名（如 player_name），
  // 统一改写成与当前数据目录一致的记录键（playerName），
  // 否则勾选状态对不上、还会画出重复字段。
  for (const f of copy.fields || []) {
    const hit = catalog.value.find(
      c => c.column === f.column || c.dbColumn === f.column)
    if (hit && f.column !== hit.column) {
      f.column = hit.column
      f.dbColumn = hit.dbColumn
    }
  }
  editor.value = copy
  clearSelection()
  resetHistory()
  refreshCanvas()
  checkBgRatio()
}

const closeEditor = () => {
  editor.value = null
  clearSelection()
  bgNote.value = ''
  bgRatioWarn.value = ''
  resetHistory()
}

const removeTpl = async (t) => {
  const ok = await confirm({
    title: '删除打印模板',
    message: `确定删除模板「${t.name}」吗？已打印的归档件与留痕不受影响。`,
    confirmText: '删除', cancelText: '取消', type: 'danger'
  })
  if (!ok) return
  try {
    await persistTemplates(rows => rows.filter(x => x.id !== t.id))
    success('已删除')
  } catch (err) {
    toastError('删除失败：' + (err.message || err))
  }
}

const persistTemplates = (update) => enqueueTemplates(async () => {
  const next = update(templates.value)
  dataService.setData('printTemplates', next, templatesRevision)
  const result = await dataService.save()
  templates.value = next
  templatesRevision = result._revisions.printTemplates
})

const onBgChange = async (e) => {
  const file = e.target.files && e.target.files[0]
  if (!file || !editor.value) return
  try {
    const res = await uploadBackground(file)
    editor.value.background = res.background
    editor.value.pageWidth = res.pageWidth
    editor.value.pageHeight = res.pageHeight
    if (res.suggestPageSize?.key) editor.value.pageSize = res.suggestPageSize.key
    bgNote.value = res.suggestPageSize?.note ||
      `底图 ${res.pageWidth}×${res.pageHeight}px，建议纸张：${res.suggestPageSize?.label || ''}`
    checkBgRatio()
  } catch (err) {
    toastError('底图上传失败：' + (err.message || err))
  }
}

// 底图比例与所选纸张不一致会静默拉伸变形——提前提示，不阻断
const bgRatioWarn = ref('')
const checkBgRatio = () => {
  const t = editor.value
  bgRatioWarn.value = ''
  if (!t?.pageWidth || !t?.pageHeight || !t?.pageSize) return
  const spec = pageSizes.value[t.pageSize]
  if (!spec) return
  const imgRatio = t.pageWidth / t.pageHeight
  const pageRatio = spec.width_mm / spec.height_mm
  const dev = Math.abs(imgRatio - pageRatio) / pageRatio
  if (dev > 0.02) {
    bgRatioWarn.value = `底图比例与所选纸张相差约 ${(dev * 100).toFixed(1)}%，打印时会被拉伸变形，建议更换纸张或底图`
  }
}
watch(() => editor.value?.pageSize, () => {
  if (editor.value) checkBgRatio()
})

const hasField = (column) => (editor.value?.fields || []).some(f => f.column === column)
const toggleField = (item) => {
  const list = editor.value.fields
  const idx = list.findIndex(f => f.column === item.column)
  if (idx >= 0) {
    pushUndo()
    if (selectedField.value === list[idx]) selectedField.value = null
    multiSel.value = multiSel.value.filter(f => f !== list[idx])
    list.splice(idx, 1)
  } else {
    pushUndo()
    const f = { column: item.column, dbColumn: item.dbColumn || '', label: item.label, x: 50, y: 50, fontSize: 18, fontFamily: '', bold: false, align: 'center', color: '#1a1a1a' }
    list.push(f)
    selectedField.value = f
    multiSel.value = [f]
  }
}
const removeField = (f) => {
  pushUndo()
  editor.value.fields = editor.value.fields.filter(x => x.column !== f.column)
  multiSel.value = multiSel.value.filter(x => x !== f)
  if (selectedField.value === f) selectedField.value = null
}

// 画布比例与尺寸
const canvasRatio = computed(() => {
  if (editor.value?.pageWidth && editor.value?.pageHeight) {
    return `${editor.value.pageWidth} / ${editor.value.pageHeight}`
  }
  const spec = pageSizes.value[editor.value?.pageSize]
  return spec ? `${spec.width_mm} / ${spec.height_mm}` : '297 / 210'
})
const thumbRatio = (t) => (t.pageWidth && t.pageHeight) ? `${t.pageWidth} / ${t.pageHeight}` : '1.414'

// 字段框定位样式（百分比 + 对齐修正，与后端 _field_style 同一规则）
const fieldStyle = (f) => {
  const parts = [`left:${f.x}%;`, `top:${f.y}%;`]
  if (f.align === 'center') parts.push('transform:translate(-50%,-50%);')
  else if (f.align === 'right') parts.push('transform:translate(-100%,-50%);')
  else parts.push('transform:translateY(-50%);')
  if (f.bold) parts.push('font-weight:700;')
  if (f.color) parts.push(`color:${f.color};`)
  if (f.fontFamily) parts.push(`font-family:'${String(f.fontFamily).replace(/'/g, '')}';`)
  parts.push(`font-size:${previewFontPx(f)}px;`)
  return parts.join('')
}

// 预览字号：把 pt 换算成画布上的像素（画布高度 ↔ 纸张 mm 高度）
const previewFontPx = (f) => {
  const mmH = pageSizes.value[editor.value?.pageSize]?.height_mm || 210
  const h = canvasH.value
  if (!h) return 14
  return Math.max(6, Math.round(f.fontSize * 25.4 / 72 / mmH * h))
}

const measureCanvas = () => {
  if (canvasEl.value) canvasH.value = canvasEl.value.getBoundingClientRect().height
}
const refreshCanvas = () => nextTick(measureCanvas)

// 对齐辅助线（% 位置；null = 不显示）
const guideV = ref(null)
const guideH = ref(null)

// ===== 撤销 / 重做 =====
const undoStack = ref([])
const redoStack = ref([])
const canUndo = computed(() => undoStack.value.length > 0 && !!editor.value)
const canRedo = computed(() => redoStack.value.length > 0 && !!editor.value)
const snapshot = () => JSON.parse(JSON.stringify(editor.value))
const commitUndo = (snap) => {
  undoStack.value.push(snap)
  if (undoStack.value.length > 50) undoStack.value.shift()
  redoStack.value = []
}
const pushUndo = () => { if (editor.value) commitUndo(snapshot()) }
const resetHistory = () => { undoStack.value = []; redoStack.value = [] }
const undo = () => {
  if (!canUndo.value) return
  redoStack.value.push(snapshot())
  editor.value = undoStack.value.pop()
  clearSelection()
  refreshCanvas()
}
const redo = () => {
  if (!canRedo.value) return
  undoStack.value.push(snapshot())
  editor.value = redoStack.value.pop()
  clearSelection()
  refreshCanvas()
}

// ===== 多选批量对齐 =====
const multiSel = ref([])
const clearSelection = () => { selectedField.value = null; multiSel.value = [] }
const onClickField = (e, f) => {
  if (e.ctrlKey || e.metaKey) {
    const i = multiSel.value.indexOf(f)
    if (i >= 0) multiSel.value.splice(i, 1)
    else multiSel.value.push(f)
    selectedField.value = multiSel.value[multiSel.value.length - 1] || null
  } else {
    multiSel.value = [f]
    selectedField.value = f
  }
}

// 画布上各字段的渲染矩形（%），含 translate 修正后的真实视觉位置
const fieldRectMap = () => {
  const rect = canvasEl.value.getBoundingClientRect()
  const map = {}
  for (const child of canvasEl.value.children) {
    if (!child.classList?.contains('tpl-field')) continue
    const cr = child.getBoundingClientRect()
    map[child.dataset.column] = {
      left: (cr.left - rect.left) / rect.width * 100,
      width: cr.width / rect.width * 100,
    }
  }
  return map
}

// 把「视觉左边缘」换算回字段的锚点 x（依 align 而不同）
const xForLeftEdge = (f, leftEdge, width) => {
  if (f.align === 'center') return leftEdge + width / 2
  if (f.align === 'right') return leftEdge + width
  return leftEdge
}

const alignLeft = () => {
  const list = multiSel.value.filter(f => editor.value.fields.includes(f))
  if (list.length < 2) return
  pushUndo()
  const rects = fieldRectMap()
  const target = Math.min(...list.map(f => rects[f.column]?.left ?? f.x))
  for (const f of list) {
    const r = rects[f.column]
    if (r) f.x = Math.round(xForLeftEdge(f, target, r.width) * 10) / 10
  }
}
const alignCenterX = () => {
  const list = multiSel.value.filter(f => editor.value.fields.includes(f))
  if (list.length < 2) return
  pushUndo()
  const rects = fieldRectMap()
  for (const f of list) {
    const w = rects[f.column]?.width ?? 0
    // 视觉水平中心统一到画布中线（50%）
    f.x = Math.round((f.align === 'center' ? 50
      : f.align === 'right' ? 50 + w / 2 : 50 - w / 2) * 10) / 10
  }
}
const distributeY = () => {
  const list = multiSel.value.filter(f => editor.value.fields.includes(f))
  if (list.length < 3) return
  pushUndo()
  const sorted = [...list].sort((a, b) => a.y - b.y)
  const minY = sorted[0].y, maxY = sorted[sorted.length - 1].y
  const step = (maxY - minY) / (sorted.length - 1)
  sorted.forEach((f, i) => { f.y = Math.round((minY + step * i) * 10) / 10 })
}

// 拖拽定位（百分比坐标）+ 自动吸附对齐
const startDrag = (e, f) => {
  selectedField.value = f
  canvasEl.value?.focus?.()
  const rect = canvasEl.value.getBoundingClientRect()
  const sx = e.clientX, sy = e.clientY, ox = f.x, oy = f.y
  const clamp = (v) => Math.min(100, Math.max(0, v))

  // 拖拽字段自身尺寸（拖动期间不变，量一次即可）
  const el = e.currentTarget
  const elRect = el.getBoundingClientRect()
  const fw = elRect.width / rect.width * 100
  const fh = elRect.height / rect.height * 100
  let dragPushed = false
  const dragPreSnap = snapshot()

  // 吸附目标线（%）：画布三等分参考线 + 其他字段的左/中/右、上/中/下
  const tv = [0, 50, 100]
  const th = [0, 50, 100]
  for (const child of canvasEl.value.children) {
    if (!child.classList?.contains('tpl-field') || child === el) continue
    const cr = child.getBoundingClientRect()
    tv.push(cr.left / rect.width * 100,
            (cr.left + cr.width / 2) / rect.width * 100,
            (cr.left + cr.width) / rect.width * 100)
    th.push(cr.top / rect.height * 100,
            (cr.top + cr.height / 2) / rect.height * 100,
            (cr.top + cr.height) / rect.height * 100)
  }

  const move = (ev) => {
    // 首次实际位移才入撤销栈，避免点击误记
    if (!dragPushed && (ev.clientX !== sx || ev.clientY !== sy)) {
      dragPushed = true
      commitUndo(dragPreSnap)
    }
    const SNAP = 6 // 吸附阈值（px）
    const nx = clamp(ox + (ev.clientX - sx) / rect.width * 100)
    const ny = clamp(oy + (ev.clientY - sy) / rect.height * 100)
    f.x = nx; f.y = ny

    // 拖拽字段的对齐线（%），与 fieldStyle 的 translate 规则一致：
    // 垂直方向始终居中锚点；水平按 align 决定锚点在哪条边。
    let dv
    if (f.align === 'center') dv = [nx - fw / 2, nx, nx + fw / 2]
    else if (f.align === 'right') dv = [nx - fw, nx - fw / 2, nx]
    else dv = [nx, nx + fw / 2, nx + fw]
    const dh = [ny - fh / 2, ny, ny + fh / 2]

    const snap = (lines, targets, sizePx) => {
      let best = null
      for (const L of lines) {
        for (const T of targets) {
          const dPx = (T - L) / 100 * sizePx
          if (Math.abs(dPx) <= SNAP && (!best || Math.abs(dPx) < Math.abs(best.dPx))) {
            best = { dPx, target: T }
          }
        }
      }
      return best
    }

    const bv = snap(dv, tv, rect.width)
    const bh = snap(dh, th, rect.height)
    if (bv) { f.x = clamp(nx + bv.dPx / rect.width * 100); guideV.value = bv.target }
    else guideV.value = null
    if (bh) { f.y = clamp(ny + bh.dPx / rect.height * 100); guideH.value = bh.target }
    else guideH.value = null
    if (!bv) f.x = Math.round(f.x * 10) / 10
    if (!bh) f.y = Math.round(f.y * 10) / 10
  }
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
    guideV.value = null
    guideH.value = null
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
  e.preventDefault()
}

// 方向键微调选中字段：0.1% 精调，Shift + 方向键 = 1% 大步
// 连续按键合并为一条撤销记录；Ctrl+Z / Ctrl+Y 撤销重做
let nudgeTimer = null
const onCanvasKeydown = (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
    e.preventDefault(); undo(); return
  }
  if ((e.ctrlKey && e.key.toLowerCase() === 'y') ||
      (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'z')) {
    e.preventDefault(); redo(); return
  }
  const f = selectedField.value
  if (!f) return
  const step = e.shiftKey ? 1 : 0.1
  const map = {
    ArrowLeft: [-step, 0], ArrowRight: [step, 0],
    ArrowUp: [0, -step], ArrowDown: [0, step],
  }
  const d = map[e.key]
  if (!d) return
  if (!nudgeTimer) pushUndo()
  clearTimeout(nudgeTimer)
  nudgeTimer = setTimeout(() => { nudgeTimer = null }, 600)
  f.x = Math.round(Math.min(100, Math.max(0, f.x + d[0])) * 10) / 10
  f.y = Math.round(Math.min(100, Math.max(0, f.y + d[1])) * 10) / 10
  e.preventDefault()
}

// 预览文本：优先取第一份证书的真实数据；字段列名兼容驼峰记录键与
// 存量模板的下划线 DB 列名（与后端 _record_value 同一兼容策略），
// 都取不到才回退字段标签。
const previewText = (f) => {
  const rec = previewRecord.value
  const v = rec ? rec[f.column] ?? rec[f.dbColumn] : null
  return (v === null || v === undefined || String(v).trim() === '') ? f.label : String(v)
}

// 该字段在台账里是否有真实数据——没有则画布半透明显示，
// 提示「现在看着有字只是标签回退，打印时会留空」。
const hasPreviewValue = (f) => {
  const rec = previewRecord.value
  if (!rec) return false
  const v = rec[f.column] ?? rec[f.dbColumn]
  return !(v === null || v === undefined || String(v).trim() === '')
}

const saveTpl = async () => {
  if (savingTpl.value || !editor.value) return
  const t = JSON.parse(JSON.stringify(editor.value))
  if (!t.name.trim()) { warning('请填写模板名称'); return }
  if (!t.background) { warning('请先上传底图'); return }
  if (!(t.fields || []).length) { warning('请至少勾选一个打印字段'); return }
  savingTpl.value = true
  try {
    const row = {
      ...t,
      name: t.name.trim(),
      createdAt: templates.value.find(x => x.id === t.id)?.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString()
    }
    await persistTemplates(rows => {
      const next = [...rows]
      const idx = next.findIndex(x => x.id === t.id)
      if (idx >= 0) next[idx] = row
      else next.unshift(row)
      return next
    })
    success('模板已保存')
    editor.value = null
  } catch (err) {
    toastError('保存失败：' + (err.message || err))
  } finally {
    savingTpl.value = false
  }
}

// ---- 字体 ----
const systemFonts = ref([])
const uploadedFonts = ref([])

/** 用 FontFace API 把上传字体加载进页面，画布预览才能按该字体渲染 */
const loadFontFace = (f) => {
  try {
    const Ctor = window.FontFace
    if (typeof Ctor !== 'function') return
    const ff = new Ctor(f.name, `url(${f.url})`)
    ff.load().then(ld => document.fonts.add(ld)).catch(() => {})
  } catch { /* 预览加载失败不影响保存与最终打印 */ }
}

const loadFonts = async () => {
  try {
    const res = await fetchFonts()
    if (!res.success) return
    systemFonts.value = res.system || []
    uploadedFonts.value = res.uploaded || []
    uploadedFonts.value.forEach(loadFontFace)
  } catch (e) { console.warn('读取字体清单失败（可忽略）:', e) }
}

const onFontChange = async (e) => {
  const file = e.target.files && e.target.files[0]
  if (!file) return
  try {
    const res = await uploadFont(file)
    if (!uploadedFonts.value.some(u => u.name === res.font.name)) {
      uploadedFonts.value = [...uploadedFonts.value, res.font]
        .sort((a, b) => a.name.localeCompare(b.name))
    }
    loadFontFace(res.font)
    success('字体已上传，可在字段属性的「字体」中选用')
  } catch (err) {
    toastError('字体上传失败：' + (err.message || err))
  }
}

const removeFont = async (u) => {
  const used = templates.value.some(t => (t.fields || []).some(f => f.fontFamily === u.name))
  const ok = await confirm({
    title: '删除字体',
    message: used
      ? `字体「${u.name}」正被某些模板字段使用，删除后这些字段将回退默认字体（模板数据不变）。确定删除吗？`
      : `确定删除字体「${u.name}」吗？`,
    confirmText: '删除', cancelText: '取消', type: 'danger'
  })
  if (!ok) return
  try {
    await deleteFont(u.name)
    uploadedFonts.value = uploadedFonts.value.filter(x => x.name !== u.name)
    success('字体已删除')
  } catch (err) {
    toastError('删除字体失败：' + (err.message || err))
  }
}
</script>

<style scoped>
.templates-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; gap: 12px; flex-wrap: wrap; }
.page-header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
.header-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.intro { margin-bottom: 16px; }
.muted { color: var(--text-secondary); font-size: 13px; }
.empty-state { padding: 60px 20px; text-align: center; color: var(--text-secondary); }
.warn-text { font-size: 12px; color: var(--text-secondary); }

/* 模板卡片 */
.tpl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.tpl-card { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.tpl-thumb { width: 100%; overflow: hidden; background: var(--bg-primary); display: flex; align-items: center; justify-content: center; }
.tpl-thumb img { width: 100%; height: 100%; object-fit: contain; }
.tpl-meta { padding: 10px 12px 4px; display: flex; flex-direction: column; gap: 2px; }
.tpl-meta strong { font-size: 14px; color: var(--text-primary); }
.tpl-actions { padding: 6px 12px 10px; display: flex; gap: 14px; }

/* 编辑器 */
.panel { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
.panel-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 10px; }
.panel-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.panel-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; }
.editor-form { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end; }
.field { font-size: 13px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 6px; }
/* 加粗等行内开关：横排（覆盖 .field 的纵排） */
.chk-inline { flex-direction: row !important; align-items: center; gap: 10px !important; cursor: pointer; }
.chk-inline input { width: 16px; height: 16px; accent-color: var(--cinnabar, #b0392b); cursor: pointer; }
.bg-note { margin-top: 10px; font-size: 12px; color: var(--cinnabar, #b0392b); }
/* 画布工具栏：撤销重做 + 多选对齐 */
.canvas-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; font-size: 13px; }
.canvas-toolbar .tb-hint { opacity: 0.75; }
.canvas-toolbar .tb-sep { width: 1px; height: 14px; background: var(--border); }
.canvas-toolbar .btn-text:disabled { opacity: 0.4; cursor: default; }
.editor-layout { display: grid; grid-template-columns: 1fr 260px; gap: 16px; align-items: start; }
.canvas-wrap { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
.canvas-tip { margin-top: 8px; }
.tpl-canvas { position: relative; width: 100%; max-width: 720px; margin: 0 auto; overflow: hidden; border: 1px solid var(--border); background: #f0ede6; user-select: none; }
.tpl-bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: fill; pointer-events: none; }
.tpl-bg-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }
.tpl-field { position: absolute; white-space: nowrap; cursor: grab; padding: 1px 3px; border: 1px dashed transparent; border-radius: 4px; }
.tpl-field:hover, .tpl-field.active { border-color: var(--cinnabar, #b0392b); background: rgba(176, 57, 43, 0.08); cursor: move; }
/* 台账中无数据的字段：半透明 + 提示，打印时会留空 */
.tpl-field.nodata { opacity: 0.45; border: 1px dashed var(--cinnabar, #b0392b); }
/* 对齐辅助线（拖拽吸附时浮现） */
.snap-guide { position: absolute; z-index: 10; pointer-events: none; background: var(--cinnabar, #b0392b); opacity: 0.75; }
.guide-v { top: 0; bottom: 0; width: 1px; margin-left: -0.5px; }
.guide-h { left: 0; right: 0; height: 1px; margin-top: -0.5px; }
.tpl-canvas:focus { outline: 1px dashed var(--cinnabar, #b0392b); outline-offset: 2px; }
.editor-side { display: flex; flex-direction: column; gap: 12px; }
.side-block { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.side-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.chk { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-primary); cursor: pointer; }
.chk.zerofill { opacity: 0.55; }
.fill-badge { margin-left: auto; font-size: 11px; color: var(--text-tertiary, #999); font-variant-numeric: tabular-nums; }
.fill-badge.zero { color: var(--cinnabar, #b0392b); }
.form-color { width: 60px; height: 30px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-primary); padding: 2px; cursor: pointer; }
.font-list { display: flex; flex-direction: column; gap: 4px; max-height: 140px; overflow-y: auto; }
.font-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; color: var(--text-primary); }
.font-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.editor-foot { margin-top: 4px; }

.btn-primary { background: var(--cinnabar, #b0392b); color: #fff; border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border); border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn-text { background: none; border: none; color: var(--cinnabar, #b0392b); cursor: pointer; font-size: 13px; padding: 0; }
.btn-text.danger { color: #c0392b; }

@media (max-width: 900px) {
  .editor-layout { grid-template-columns: 1fr; }
}
</style>
