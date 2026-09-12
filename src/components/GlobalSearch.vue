<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '../services/http.js'

const router = useRouter()
const keyword = ref('')
const results = ref({})
const total = ref(0)
const open = ref(false)
const loading = ref(false)
let timer = null

const TYPE_LABELS = { projects: '项目', players: '选手', organizations: '机构', finances: '财务', knowledge: '知识' }

const search = async () => {
  const q = keyword.value.trim()
  if (!q) { results.value = {}; total.value = 0; open.value = false; return }
  loading.value = true
  try {
    const data = await get(`/api/search?q=${encodeURIComponent(q)}`)
    results.value = (data && data.results) || {}
    total.value = (data && data.total) || 0
    open.value = true
  } catch (e) {
    console.error('全局搜索失败:', e)
    results.value = {}
    total.value = 0
  } finally {
    loading.value = false
  }
}

const onInput = () => {
  clearTimeout(timer)
  timer = setTimeout(search, 180)
}

const highlight = (text) => {
  const q = keyword.value.trim()
  const s = text == null ? '' : String(text)
  if (!q) return escapeHtml(s)
  const idx = s.toLowerCase().indexOf(q.toLowerCase())
  if (idx < 0) return escapeHtml(s)
  return escapeHtml(s.slice(0, idx)) + '<mark>' + escapeHtml(s.slice(idx, idx + q.length)) + '</mark>' + escapeHtml(s.slice(idx + q.length))
}

const go = (route) => {
  if (route) router.push(route)
  open.value = false
  keyword.value = ''
}

const onClickOutside = (e) => {
  if (!e.target.closest('.global-search')) open.value = false
}

const escapeHtml = (s) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  clearTimeout(timer)
})
</script>

<template>
  <div class="global-search">
    <input
      v-model="keyword"
      type="text"
      class="gs-input"
      placeholder="全局搜索 项目 / 选手 / 机构 / 财务 / 知识"
      @input="onInput"
      @focus="onInput"
    />
    <div v-if="open" class="gs-panel">
      <div v-if="loading" class="gs-empty">搜索中…</div>
      <template v-else-if="total > 0">
        <div v-for="(list, type) in results" :key="type" class="gs-group">
          <div class="gs-group-title">{{ TYPE_LABELS[type] || type }}（{{ list.length }}）</div>
          <div
            v-for="item in list.slice(0, 5)"
            :key="type + item.id"
            class="gs-item"
            @click="go(item.route)"
            v-html="highlight(item.title)"
          ></div>
        </div>
      </template>
      <div v-else class="gs-empty">未找到相关结果</div>
    </div>
  </div>
</template>

<style scoped>
.global-search { position: relative; }
.gs-input {
  width: 240px; padding: 8px 14px; border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface); color: var(--text-primary); font-size: 13px;
}
.gs-input:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--accent-light); }
.gs-panel {
  position: absolute; top: calc(100% + 8px); right: 0; width: 320px; max-height: 420px; overflow-y: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md);
  box-shadow: var(--shadow-md); z-index: 1000; padding: 8px;
}
.gs-group { margin-bottom: 8px; }
.gs-group-title { font-size: 12px; color: var(--text-tertiary); padding: 4px 8px; }
.gs-item {
  padding: 8px 10px; border-radius: var(--radius-sm); font-size: 14px; color: var(--text-primary);
  cursor: pointer; transition: background var(--transition-fast);
}
.gs-item:hover { background: var(--bg-hover); }
.gs-item :deep(mark) { background: var(--accent-light); color: var(--accent); padding: 0 2px; border-radius: 2px; }
.gs-empty { padding: 16px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
</style>
