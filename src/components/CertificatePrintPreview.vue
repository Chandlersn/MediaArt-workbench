<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { previewPrint } from '../services/print'

const props = defineProps({
  templateId: { type: String, default: '' },
  references: { type: Array, default: () => [] },
  check: { type: Object, default: null },
  disabled: Boolean,
})
const emit = defineEmits(['ready', 'recheck'])
const pageIndex = ref(0)
const zoom = ref('fit')
const viewport = ref(null)
const availableWidth = ref(580)
const result = ref(null)
const busy = ref(false)
const error = ref('')
let sequence = 0
let observer
const width = computed(() => (result.value?.page.width_mm || 297) * 96 / 25.4)
const height = computed(() => (result.value?.page.height_mm || 210) * 96 / 25.4)
const scale = computed(() => zoom.value === 'fit' ? Math.min(1, Math.max(0.1, (availableWidth.value - 40) / width.value)) : Number(zoom.value))
const scope = computed(() => JSON.stringify([props.templateId, props.references]))

async function load() {
  const id = ++sequence
  result.value = null
  error.value = ''
  busy.value = false
  emit('ready', '')
  if (!props.check?.canGenerate) return
  busy.value = true
  try {
    const response = await previewPrint({ templateId: props.templateId, certNumbers: props.references,
      validationToken: props.check.validationToken, pageIndex: pageIndex.value })
    if (id !== sequence) return
    if (!response.success || !response.html || response.validationToken !== props.check?.validationToken) {
      throw new Error(response.message || '预览已过期，请重新检查')
    }
    result.value = response
    // Wait for iframe load (including images/fonts) before enabling the print action.
  } catch (err) {
    if (id === sequence) error.value = err.message || '预览加载失败'
  } finally {
    if (id === sequence) busy.value = false
  }
}
watch(scope, () => { pageIndex.value = 0 }, { flush: 'sync' })
watch([scope, () => props.check?.validationToken, () => props.check?.canGenerate, pageIndex], load, { immediate: true })
const frameLoaded = () => {
  if (result.value?.validationToken === props.check?.validationToken) emit('ready', result.value.validationToken)
}
onMounted(() => {
  observer = new ResizeObserver(entries => { availableWidth.value = entries[0].contentRect.width })
  if (viewport.value) observer.observe(viewport.value)
})
onBeforeUnmount(() => { sequence++; observer?.disconnect() })
</script>

<template>
  <section class="certificate-preview" aria-label="证书效果预览" :aria-busy="busy">
    <div class="preview-toolbar">
      <strong>打印效果</strong>
      <label>缩放
        <select v-model="zoom" aria-label="预览缩放">
          <option value="fit">适合窗口</option><option value="0.5">50%</option>
          <option value="0.75">75%</option><option value="1">100%</option><option value="1.25">125%</option>
        </select>
      </label>
    </div>
    <div ref="viewport" class="preview-viewport">
      <div v-if="busy" class="preview-placeholder">正在排版…</div>
      <div v-else-if="error" class="preview-placeholder preview-error" role="alert">
        <span>{{ error }}</span><button :disabled="disabled" @click="emit('recheck')">重新检查并预览</button>
      </div>
      <div v-else-if="result" class="preview-paper" :style="{ width: width * scale + 'px', height: height * scale + 'px' }">
        <iframe :key="`${result.validationToken}:${result.pageIndex}`" title="证书打印效果" sandbox="allow-same-origin"
          :srcdoc="result.html" :style="{ width: width + 'px', height: height + 'px', transform: `scale(${scale})` }" @load="frameLoaded" />
      </div>
      <div v-else class="preview-placeholder">{{ check && !check.canGenerate ? '修正模板问题后显示预览' : '检查完成后显示预览' }}</div>
    </div>
    <div class="preview-pagination">
      <button :disabled="disabled || busy || pageIndex === 0" @click="pageIndex--">上一份</button>
      <span>第 {{ pageIndex + 1 }} / {{ references.length }} 份</span>
      <button :disabled="disabled || busy || pageIndex >= references.length - 1" @click="pageIndex++">下一份</button>
    </div>
    <div class="preview-caption" aria-live="polite">
      <template v-if="result">{{ result.reference.certNumber }} · {{ result.playerName }} · {{ result.page.label }}（{{ result.page.width_mm }} × {{ result.page.height_mm }} mm）</template>
      <template v-else>预览范围与本次勾选的证书一致</template>
    </div>
    <p class="preview-note">此处缩放仅方便查看。正式打印请选择实际大小（100%），并关闭页眉页脚。</p>
  </section>
</template>

<style scoped>
.certificate-preview { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--bg-secondary); }
.preview-toolbar, .preview-pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; font-size: 13px; }
.preview-toolbar label { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); }
select, button { font: inherit; color: var(--text-primary); background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; }
button { cursor: pointer; } button:disabled { opacity: .45; cursor: not-allowed; }
.preview-viewport { flex: 1; min-height: 280px; overflow: auto; padding: 20px; background: #e8e5df; }
.preview-paper { position: relative; margin: 0 auto; background: white; box-shadow: 0 4px 18px #0002; }
iframe { position: absolute; inset: 0; border: 0; transform-origin: top left; background: white; }
.preview-placeholder { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; color: var(--text-secondary); padding: 20px; text-align: center; font-size: 13px; }
.preview-error { color: var(--danger, #b0392b); }
.preview-pagination { justify-content: center; padding-bottom: 8px; }
.preview-caption, .preview-note { text-align: center; color: var(--text-secondary); font-size: 12px; padding: 0 18px; }
.preview-note { line-height: 1.6; margin: 8px 0 14px; }
</style>
