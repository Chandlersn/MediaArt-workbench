<script setup>
import { ref, onMounted, onBeforeUnmount, onDeactivated } from 'vue'

const props = defineProps({ selected: { type: Number, default: 0 }, filtered: { type: Number, default: 0 }, total: { type: Number, default: 0 }, disabled: Boolean, printBusy: Boolean })
const emit = defineEmits(['sync', 'import', 'export-filtered', 'export-batch', 'rules', 'templates', 'history', 'print', 'bulk-edit', 'bulk-delete'])
const root = ref(null)
const close = () => root.value?.querySelectorAll('details[open]').forEach(menu => { menu.open = false })
const outside = event => { if (!root.value?.contains(event.target)) close() }
const act = name => { close(); emit(name) }
const blockMenu = (event, unavailable) => { if (unavailable) event.preventDefault() }
const openExport = event => blockMenu(event, props.disabled || !props.total)
const openMore = event => blockMenu(event, props.disabled)
// 批量操作菜单：没有勾选任何证书时不允许展开
const openBulk = event => blockMenu(event, props.disabled || !props.selected)
const menuOpened = event => {
  if (event.target.open) root.value?.querySelectorAll('details[open]').forEach(menu => {
    if (menu !== event.target) menu.open = false
  })
}
onMounted(() => document.addEventListener('pointerdown', outside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', outside))
onDeactivated(close)
</script>

<template>
  <div ref="root" class="certificate-actions" @keydown.esc="close">
    <button class="action" :disabled="disabled" @click="act('import')">导入台账</button>
    <button class="action" :disabled="disabled" @click="act('sync')">从选手同步</button>
    <details class="action-menu" @toggle="menuOpened">
      <summary :aria-disabled="disabled || !total" @click="openExport">导出台账 <span aria-hidden="true">⌄</span></summary>
      <div class="menu-items">
        <button :disabled="disabled || !filtered" @click="act('export-filtered')">当前筛选结果 <span>{{ filtered }} 份</span></button>
        <button :disabled="disabled || !total" @click="act('export-batch')">当前整个批次 <span>{{ total }} 份</span></button>
      </div>
    </details>
    <details class="action-menu" @toggle="menuOpened">
      <summary :aria-disabled="disabled" @click="openMore">更多 <span aria-hidden="true">⌄</span></summary>
      <div class="menu-items">
        <button :disabled="disabled" @click="act('rules')">编号规则</button>
        <button :disabled="disabled" @click="act('templates')">模板管理</button>
        <button :disabled="disabled" @click="act('history')">打印记录</button>
      </div>
    </details>
    <button class="action primary" :disabled="disabled || !selected || printBusy" @click="act('print')">批量打印{{ selected ? `（${selected}）` : '' }}</button>
    <details class="action-menu" @toggle="menuOpened">
      <summary :aria-disabled="disabled || !selected" @click="openBulk">批量操作{{ selected ? `（${selected}）` : '' }} <span aria-hidden="true">⌄</span></summary>
      <div class="menu-items">
        <button :disabled="disabled || !selected" @click="act('bulk-edit')">批量修改字段 <span>{{ selected }} 份</span></button>
        <button class="danger" :disabled="disabled || !selected" @click="act('bulk-delete')">批量删除 <span>{{ selected }} 份</span></button>
      </div>
    </details>
  </div>
</template>

<style scoped>
.certificate-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.action, summary { border: 1px solid var(--border); border-radius: 7px; background: var(--bg-primary); color: var(--text-primary); padding: 7px 12px; font-size: 13px; cursor: pointer; line-height: 1.4; }
.primary { background: var(--cinnabar, #b0392b); border-color: var(--cinnabar, #b0392b); color: white; }
button:disabled, summary[aria-disabled=true] { opacity: .5; cursor: not-allowed; }
.action-menu { position: relative; }
summary { list-style: none; display: flex; align-items: center; gap: 10px; }
summary::-webkit-details-marker { display: none; }
.menu-items { position: absolute; right: 0; top: calc(100% + 6px); z-index: 30; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 9px; padding: 5px; min-width: 210px; box-shadow: 0 6px 24px #0002; }
.menu-items button { border: 0; background: transparent; color: var(--text-primary); display: flex; justify-content: space-between; gap: 16px; padding: 10px; width: 100%; text-align: left; cursor: pointer; border-radius: 5px; font-size: 13px; }
.menu-items button:hover, .menu-items button:focus-visible { background: var(--bg-secondary); }
.menu-items span { color: var(--text-secondary); }
.menu-items button.danger { color: var(--danger, #d9534f); }
.menu-items button.danger:hover, .menu-items button.danger:focus-visible { background: var(--danger-light, rgba(217, 83, 79, 0.08)); }
</style>
