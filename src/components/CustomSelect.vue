<template>
  <div class="custom-select" ref="selectRef">
    <div
      class="custom-select-trigger"
      :class="{ 'is-active': isOpen, 'is-disabled': disabled }"
      @click="toggle"
    >
      <span class="custom-select-value" :class="{ 'is-placeholder': !modelValue }">
        {{ displayValue || placeholder }}
      </span>
      <span class="custom-select-arrow">
        <svg v-if="!isOpen" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
        <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="18 9 12 3 6 9"></polyline>
        </svg>
      </span>
    </div>
    <Teleport to="body">
      <transition name="select-fade">
        <div
          v-if="isOpen"
          class="custom-select-dropdown"
          :style="dropdownStyle"
          ref="dropdownRef"
        >
          <div
            v-for="option in effectiveOptions"
            :key="option.value"
            class="custom-select-option"
            :class="{ 'is-selected': isOptionSelected(option.value) }"
            @click.stop="selectOption(option)"
          >
            <span class="option-check" v-if="isOptionSelected(option.value)">✓</span>
            <span class="option-label">{{ option.label }}</span>
          </div>
          <div v-if="effectiveOptions.length === 0" class="custom-select-empty">
            暂无选项
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, useSlots } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, Array], default: '' },
  placeholder: { type: String, default: '请选择' },
  options: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  // 多选：modelValue 为数组，选项可连续勾选、不自动收起
  multiple: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'change'])

const slots = useSlots()

// 支持把原生 <option> 作为默认插槽传入（全局替换 <select> 时无需逐个改写选项数组）：
// 解析插槽里的 <option value=..>label</option> 节点，动态 v-for 展开后的选项同样生效。
const extractText = (node) => {
  if (node == null) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (node.children) return extractText(node.children)
  return ''
}

const slotOptions = computed(() => {
  const def = slots.default
  if (!def) return []
  let nodes = def()
  if (!Array.isArray(nodes)) nodes = [nodes]
  const out = []
  const walk = (list) => {
    for (const n of list) {
      if (!n) continue
      if (Array.isArray(n)) { walk(n); continue }
      if (typeof n === 'string' || typeof n === 'number') continue
      if (n.type === 'option') {
        const p = n.props || {}
        let label = ''
        const c = n.children
        if (typeof c === 'string') label = c
        else if (c && typeof c === 'object' && typeof c.default === 'function') {
          label = extractText(c.default())
        } else if (Array.isArray(c)) {
          label = c.map(extractText).join('')
        }
        out.push({ value: p.value, label: String(label == null ? '' : label).trim() })
      } else if (n.children && Array.isArray(n.children)) {
        walk(n.children)
      } else if (n.children && typeof n.children === 'object' && typeof n.children.default === 'function') {
        const r = n.children.default()
        if (Array.isArray(r)) walk(r)
      }
    }
  }
  walk(nodes)
  return out
})

// 优先用显式传入的 options，否则回退到插槽解析出的 option
const effectiveOptions = computed(() =>
  (props.options && props.options.length) ? props.options : slotOptions.value
)

const isOpen = ref(false)
const selectRef = ref(null)
const dropdownRef = ref(null)
const dropdownStyle = ref({})

const selectedValues = computed(() =>
  props.multiple ? (Array.isArray(props.modelValue) ? props.modelValue : []) : []
)

const isOptionSelected = (value) =>
  props.multiple ? selectedValues.value.includes(value) : value === props.modelValue

const displayValue = computed(() => {
  if (props.multiple) {
    const chosen = effectiveOptions.value.filter(o => selectedValues.value.includes(o.value))
    if (chosen.length === 0) return ''
    if (chosen.length === 1) return chosen[0].label
    return `已选 ${chosen.length} 项`
  }
  const selected = effectiveOptions.value.find(o => o.value === props.modelValue)
  return selected ? selected.label : ''
})

const updateDropdownPosition = () => {
  if (!selectRef.value) return
  const rect = selectRef.value.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  const spaceBelow = viewportHeight - rect.bottom
  const spaceAbove = rect.top
  const estimatedHeight = Math.min(effectiveOptions.value.length * 36 + 8, 240)

  let top
  if (spaceBelow >= estimatedHeight + 4 || spaceBelow >= spaceAbove) {
    top = rect.bottom + 4
  } else {
    top = rect.top - estimatedHeight - 4
  }

  dropdownStyle.value = {
    position: 'fixed',
    top: `${top}px`,
    left: `${rect.left}px`,
    minWidth: `${rect.width}px`
  }
}

const toggle = async () => {
  if (props.disabled) return
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    await nextTick()
    updateDropdownPosition()
  }
}

const selectOption = (option) => {
  if (props.multiple) {
    const next = [...selectedValues.value]
    const idx = next.indexOf(option.value)
    if (idx >= 0) next.splice(idx, 1)
    else next.push(option.value)
    emit('update:modelValue', next)
    emit('change', next)
    // 多选不自动收起，便于连续勾选；点击外部再关闭
    return
  }
  emit('update:modelValue', option.value)
  emit('change', option.value)
  isOpen.value = false
}

const handleClickOutside = (e) => {
  if (isOpen.value) {
    const clickedSelect = selectRef.value && selectRef.value.contains(e.target)
    const clickedDropdown = dropdownRef.value && dropdownRef.value.contains(e.target)
    if (!clickedSelect && !clickedDropdown) {
      isOpen.value = false
    }
  }
}

const handleScroll = () => {
  if (isOpen.value) {
    updateDropdownPosition()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside, true)
  window.addEventListener('scroll', handleScroll, true)
  window.addEventListener('resize', handleScroll)
})
onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside, true)
  window.removeEventListener('scroll', handleScroll, true)
  window.removeEventListener('resize', handleScroll)
})
</script>

<style scoped>
.custom-select {
  position: relative;
  display: inline-block;
  min-width: 120px;
}

.custom-select-trigger {
  display: flex;
  align-items: center;
  padding: 8px 36px 8px 14px;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 10px;
  background: var(--surface, #fff);
  color: var(--text-primary, #0f172a);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  height: 36px;
  box-sizing: border-box;
  position: relative;
  font-family: inherit;
}

.custom-select-trigger:hover {
  border-color: var(--accent, #3b82f6);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.08);
}

.custom-select-trigger.is-active {
  border-color: var(--accent, #3b82f6);
  box-shadow: 0 0 0 3px var(--accent-light, rgba(59, 130, 246, 0.15));
}

.custom-select-trigger.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.custom-select-value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
}

.custom-select-value.is-placeholder {
  color: var(--text-tertiary, #94a3b8);
}

.custom-select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary, #94a3b8);
  pointer-events: none;
  transition: color 0.2s;
}

.custom-select-trigger:hover .custom-select-arrow,
.custom-select-trigger.is-active .custom-select-arrow {
  color: var(--accent, #3b82f6);
}

.custom-select-arrow svg {
  width: 14px;
  height: 14px;
  display: block;
}

.custom-select-dropdown {
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
  z-index: 9999;
  max-height: 240px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px;
}

.custom-select-dropdown::-webkit-scrollbar {
  width: 6px;
}

.custom-select-dropdown::-webkit-scrollbar-track {
  background: transparent;
}

.custom-select-dropdown::-webkit-scrollbar-thumb {
  background: var(--border, #e2e8f0);
  border-radius: 3px;
}

.custom-select-dropdown::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary, #94a3b8);
}

.custom-select-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary, #0f172a);
  transition: all 0.15s ease;
  white-space: nowrap;
}

.custom-select-option:hover {
  background: var(--bg-tertiary, #e2e8f0);
}

.custom-select-option.is-selected {
  background: var(--accent-light, rgba(59, 130, 246, 0.1));
  color: var(--accent, #3b82f6);
  font-weight: 500;
}

.option-check {
  font-size: 12px;
  color: var(--accent, #3b82f6);
  font-weight: 600;
}

.option-label {
  flex: 1;
}

.custom-select-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-tertiary, #94a3b8);
  font-size: 13px;
}

.select-fade-enter-active,
.select-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.select-fade-enter-from,
.select-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

[data-theme="dark"] .custom-select-trigger {
  background: var(--surface, #1e293b);
  border-color: var(--border, #334155);
  color: var(--text-primary, #f8fafc);
}

[data-theme="dark"] .custom-select-trigger:hover {
  box-shadow: 0 2px 8px rgba(96, 165, 250, 0.1);
}

[data-theme="dark"] .custom-select-dropdown {
  background: var(--surface, #1e293b);
  border-color: var(--border, #334155);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2);
}

[data-theme="dark"] .custom-select-option:hover {
  background: var(--bg-tertiary, #334155);
}

[data-theme="dark"] .custom-select-option.is-selected {
  background: var(--accent-light, rgba(96, 165, 250, 0.2));
  color: var(--accent, #60a5fa);
}

[data-theme="dark"] .option-check {
  color: var(--accent, #60a5fa);
}

[data-theme="dark"] .custom-select-arrow {
  color: var(--text-tertiary, #64748b);
}

[data-theme="dark"] .custom-select-trigger:hover .custom-select-arrow,
[data-theme="dark"] .custom-select-trigger.is-active .custom-select-arrow {
  color: var(--accent, #60a5fa);
}

[data-theme="dark"] .custom-select-dropdown::-webkit-scrollbar-thumb {
  background: var(--border, #334155);
}

[data-theme="dark"] .custom-select-dropdown::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary, #64748b);
}
</style>
