<template>
  <div
    class="fda"
    :class="{ 'is-over': isOver, 'is-disabled': disabled }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <!--
      组件内部持有 input，拖拽时把文件写回 input 再派发 change 事件。
      这样父组件原有的 change 处理函数完全不用改（仍从 e.target.files 取文件），
      只是多了一个「拖进来」的入口。
    -->
    <input
      ref="inputEl"
      type="file"
      :accept="accept"
      :multiple="multiple"
      style="display: none"
      @change="onInputChange"
    />

    <div class="fda-row">
      <button
        type="button"
        class="btn-secondary btn-sm"
        :disabled="disabled"
        @click="openPicker"
      >{{ hasFile ? '重新选择' : buttonText }}</button>
      <span v-if="hasFile" class="fda-name" :title="fileName">{{ fileName }}</span>
      <span v-else-if="!disabled" class="fda-hint">{{ hint }}</span>
    </div>

    <div v-if="isOver" class="fda-mask">松开鼠标即可选择文件</div>
    <div v-if="rejectMsg" class="fda-reject">{{ rejectMsg }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'

/**
 * 文件选择区（支持点击选择 + 拖拽上传）。
 *
 * 设计要点：组件内部持有 `<input type="file">`，拖拽落下时把文件写回 input
 * 并派发一次 `change`，因此**父组件原有的 `@change` 处理函数无需改动**。
 * 选完后会自动清空 input，保证「连续选同一个文件」也能再次触发 change。
 */
const props = defineProps({
  accept: { type: String, default: '' },
  multiple: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  /** 已选文件名（由父组件传入，用于显示"已选 xxx"） */
  fileName: { type: String, default: '' },
  buttonText: { type: String, default: '选择文件' },
  hint: { type: String, default: '或把文件拖到这里' },
})

const emit = defineEmits(['change'])

const inputEl = ref(null)
const isOver = ref(false)
const rejectMsg = ref('')
let depth = 0          // 处理拖拽经过子元素时的 dragleave 闪烁
let rejectTimer = null

const hasFile = computed(() => !!props.fileName)

const openPicker = () => {
  if (!props.disabled) inputEl.value?.click()
}

/** 扩展名是否命中 accept（只做客户端预检，真正校验仍在服务端） */
const matchesAccept = (name) => {
  if (!props.accept) return true
  const lower = (name || '').toLowerCase()
  return props.accept
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean)
    .some((rule) => {
      if (rule.startsWith('.')) return lower.endsWith(rule)
      if (rule.endsWith('/*')) return lower.startsWith('')  // 形如 image/* 无法按名判断，放行
      return true
    })
}

const showReject = (count) => {
  rejectMsg.value = `已忽略 ${count} 个类型不符的文件`
  if (rejectTimer) clearTimeout(rejectTimer)
  rejectTimer = setTimeout(() => { rejectMsg.value = '' }, 3000)
}

/** 把文件写回 input 并派发 change —— 父组件的 @change 因此照常工作 */
const fireChange = (files) => {
  const list = Array.from(files || [])
  if (!list.length || !inputEl.value) return
  const dt = new DataTransfer()
  list.forEach((f) => dt.items.add(f))
  inputEl.value.files = dt.files
  inputEl.value.dispatchEvent(new Event('change', { bubbles: true }))
  // 派发后清空，保证下次选同一个文件仍能触发 change（原来各页面自己做的重置）
  setTimeout(() => { if (inputEl.value) inputEl.value.value = '' }, 0)
}

const onInputChange = (e) => {
  emit('change', e)
}

const onDragEnter = () => {
  if (props.disabled) return
  depth += 1
  isOver.value = true
}

const onDragOver = () => {
  if (props.disabled) return
  if (!isOver.value) isOver.value = true
}

const onDragLeave = () => {
  if (props.disabled) return
  depth -= 1
  if (depth <= 0) {
    depth = 0
    isOver.value = false
  }
}

const onDrop = (e) => {
  depth = 0
  isOver.value = false
  if (props.disabled) return

  const all = Array.from(e.dataTransfer?.files || [])
  if (!all.length) return

  const ok = all.filter((f) => matchesAccept(f.name))
  if (!ok.length) {
    showReject(all.length)
    return
  }
  if (ok.length < all.length) showReject(all.length - ok.length)

  fireChange(props.multiple ? ok : ok.slice(0, 1))
}

onBeforeUnmount(() => {
  if (rejectTimer) clearTimeout(rejectTimer)
})
</script>

<style scoped>
.fda {
  position: relative;
  display: inline-block;
  max-width: 100%;
}

.fda-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.fda-name {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.fda-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.fda.is-over .fda-row {
  outline: 2px dashed var(--accent);
  outline-offset: 6px;
  border-radius: 6px;
}

.fda-mask {
  position: absolute;
  inset: -8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-light, rgba(59, 130, 246, 0.1));
  border: 2px dashed var(--accent);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--accent);
  pointer-events: none;
  z-index: 2;
}

.fda-reject {
  margin-top: 6px;
  font-size: 12px;
  color: var(--danger, #d9534f);
}

.fda.is-disabled {
  opacity: 0.6;
}
</style>
