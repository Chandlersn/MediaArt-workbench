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
const facets = ref({ modules: {}, types: {} })
let timer = null

// 维度筛选状态
const ALL_MODULES = ['projects', 'players', 'organizations', 'finances', 'knowledge', 'files']
const modules = ref([...ALL_MODULES])
const typeFilter = ref('')
const entityFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')

const TYPE_LABELS = {
  projects: '项目', players: '选手', organizations: '机构',
  finances: '财务', knowledge: '知识', files: '文件',
}

const hasAnyFilter = () =>
  !!typeFilter.value.trim() || !!entityFilter.value.trim() ||
  !!dateFrom.value || !!dateTo.value || modules.value.length < ALL_MODULES.length

const search = async () => {
  const q = keyword.value.trim()
  if (!q && !hasAnyFilter()) {
    results.value = {}; total.value = 0; open.value = false; return
  }
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (modules.value.length < ALL_MODULES.length) params.set('modules', modules.value.join(','))
    if (typeFilter.value.trim()) params.set('type', typeFilter.value.trim())
    if (entityFilter.value.trim()) params.set('entity', entityFilter.value.trim())
    if (dateFrom.value) params.set('dateFrom', dateFrom.value)
    if (dateTo.value) params.set('dateTo', dateTo.value)
    const data = await get(`/api/search?${params.toString()}`)
    results.value = (data && data.results) || {}
    total.value = (data && data.total) || 0
    facets.value = (data && data.facets) || { modules: {}, types: {} }
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

const toggleModule = (m) => {
  const i = modules.value.indexOf(m)
  if (i >= 0) modules.value.splice(i, 1)
  else modules.value.push(m)
  if (open.value) search()
}

const onFilterChange = () => {
  if (open.value) search()
}

const highlight = (text) => {
  const q = keyword.value.trim()
  const s = text == null ? '' : String(text)
  if (!q) return escapeHtml(s)
  const idx = s.toLowerCase().indexOf(q.toLowerCase())
  if (idx < 0) return escapeHtml(s)
  return escapeHtml(s.slice(0, idx)) + '<mark>' + escapeHtml(s.slice(idx, idx + q.length)) + '</mark>' + escapeHtml(s.slice(idx + q.length))
}

const formatSize = (n) => {
  if (!n) return ''
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

const go = (item) => {
  if (item && item.route) router.push(item.route)
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
      placeholder="全局搜索 项目 / 选手 / 机构 / 财务 / 知识 / 文件"
      @input="onInput"
      @focus="onInput"
    />
    <div v-if="open" class="gs-panel">
      <!-- 多维筛选 -->
      <div class="gs-filters">
        <div class="gs-filter-row">
          <button
            v-for="m in ALL_MODULES"
            :key="m"
            class="gs-chip"
            :class="{ active: modules.includes(m) }"
            @click="toggleModule(m)"
          >{{ TYPE_LABELS[m] }}<span v-if="facets.modules[m]" class="gs-chip-count">{{ facets.modules[m] }}</span></button>
        </div>
        <div class="gs-filter-row">
          <input v-model="typeFilter" class="gs-field" type="text" placeholder="类型" @input="onFilterChange" />
          <input v-model="entityFilter" class="gs-field" type="text" placeholder="归属实体" @input="onFilterChange" />
        </div>
        <div class="gs-filter-row">
          <input v-model="dateFrom" class="gs-field" type="date" @change="onFilterChange" />
          <span class="gs-tilde">~</span>
          <input v-model="dateTo" class="gs-field" type="date" @change="onFilterChange" />
        </div>
      </div>

      <div v-if="loading" class="gs-empty">搜索中…</div>
      <template v-else-if="total > 0">
        <div v-for="(list, type) in results" :key="type" class="gs-group">
          <div class="gs-group-title">{{ TYPE_LABELS[type] || type }}（{{ list.length }}）</div>
          <div
            v-for="item in list.slice(0, 6)"
            :key="type + item.id"
            class="gs-item"
            @click="go(item)"
          >
            <span v-html="highlight(item.title)"></span>
            <span class="gs-sub" v-if="item.sub">{{ item.sub }}</span>
            <span class="gs-meta" v-if="item.kind === 'file' && item.size">{{ formatSize(item.size) }}</span>
          </div>
        </div>
      </template>
      <div v-else class="gs-empty">未找到相关结果</div>
    </div>
  </div>
</template>

<style scoped>
.global-search { position: relative; }
.gs-input {
  width: 260px; padding: 8px 14px; border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface); color: var(--text-primary); font-size: 13px;
}
.gs-input:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--accent-light); }
.gs-panel {
  position: absolute; top: calc(100% + 8px); right: 0; width: 440px; max-height: 540px; overflow-y: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md);
  box-shadow: var(--shadow-md); z-index: 1000; padding: 10px;
}
.gs-filters { border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 8px; }
.gs-filter-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 6px; }
.gs-filter-row:last-child { margin-bottom: 0; }
.gs-chip {
  padding: 4px 10px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--surface); color: var(--text-tertiary); font-size: 12px; cursor: pointer;
  transition: all var(--transition-fast);
}
.gs-chip.active { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
.gs-chip-count { margin-left: 4px; font-size: 11px; opacity: 0.8; }
.gs-field {
  flex: 1; min-width: 90px; padding: 5px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--text-primary); font-size: 12px;
}
.gs-field:focus { outline: none; border-color: var(--border-focus); }
.gs-tilde { color: var(--text-tertiary); }
.gs-group { margin-bottom: 8px; }
.gs-group-title { font-size: 12px; color: var(--text-tertiary); padding: 4px 8px; }
.gs-item {
  display: flex; align-items: baseline; gap: 8px; padding: 8px 10px; border-radius: var(--radius-sm);
  font-size: 14px; color: var(--text-primary); cursor: pointer; transition: background var(--transition-fast);
}
.gs-item:hover { background: var(--bg-hover); }
.gs-item :deep(mark) { background: var(--accent-light); color: var(--accent); padding: 0 2px; border-radius: 2px; }
.gs-sub { font-size: 12px; color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gs-meta { margin-left: auto; font-size: 11px; color: var(--text-tertiary); }
.gs-empty { padding: 16px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
</style>
