<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useKnowledgeStore, KNOWLEDGE_TYPES, KNOWLEDGE_TYPE_ORDER } from '../stores'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()
const { knowledge } = storeToRefs(knowledgeStore)

const activeType = ref('all')
const activeTag = ref('')
const searchKeyword = ref('')
const view = ref('grid')
const showDeleteModal = ref(false)
const deleteId = ref(null)

const stats = computed(() => knowledgeStore.getKnowledgeStats())
const tags = computed(() => knowledgeStore.getTags())
const recent = computed(() => knowledgeStore.getRecent(6))

const typeNav = computed(() => [
  { key: 'all', label: '全部', count: knowledgeStore.getAllFlat().length, color: 'var(--accent)' },
  ...KNOWLEDGE_TYPE_ORDER.map(t => ({
    key: t, label: KNOWLEDGE_TYPES[t].name, count: stats.value[t] || 0, color: KNOWLEDGE_TYPES[t].color
  }))
])

const results = computed(() => {
  let items = knowledgeStore.search(searchKeyword.value, { tag: activeTag.value, type: activeType.value })
  if (!searchKeyword.value) {
    items = items.slice().sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))
  }
  return items
})

// 结构化摘要：取已填写的第一个字段，作为卡片正文预览
const structPreview = (item) => {
  const def = KNOWLEDGE_TYPES[item.kind]
  if (!def) return item.description || ''
  for (const f of def.fields) {
    const v = item.fields && item.fields[f.key]
    if (v && String(v).trim()) return String(v).slice(0, 120)
  }
  return item.description || ''
}

const timelineGroups = computed(() => {
  const groups = {}
  results.value.forEach(it => {
    const d = (it.date || it.updatedAt || '未知日期').slice(0, 10)
    ;(groups[d] = groups[d] || []).push(it)
  })
  return Object.keys(groups).sort((a, b) => b.localeCompare(a)).map(d => ({ date: d, items: groups[d] }))
})

const typeLabel = (k) => KNOWLEDGE_TYPES[k]?.name || k
const typeColor = (k) => KNOWLEDGE_TYPES[k]?.color || 'var(--accent)'
const formatDate = (s) => s ? new Date(s).toLocaleDateString('zh-CN') : ''

const setType = (t) => { activeType.value = t; activeTag.value = '' }
const setTag = (t) => { activeTag.value = activeTag.value === t ? '' : t }
const clearFilters = () => { activeType.value = 'all'; activeTag.value = ''; searchKeyword.value = '' }

const handleAdd = () => router.push('/knowledge/new')
const handleEdit = (id) => router.push(`/knowledge/${id}/edit`)
const handleView = (id) => router.push(`/knowledge/${id}`)
const handleDelete = (id) => { deleteId.value = id; showDeleteModal.value = true }
const confirmDelete = async () => {
  if (deleteId.value) {
    await knowledgeStore.deleteItem(deleteId.value)
    showDeleteModal.value = false
    deleteId.value = null
  }
}

onMounted(() => knowledgeStore.loadItems())
onActivated(() => knowledgeStore.loadItems())
</script>

<template>
  <div class="knowledge-view">
    <PageHeader
      title="知识库"
      description="沉淀解决方案、排障经验、案例、心得与外部资料"
    >
      <template #actions>
        <button class="btn-primary" @click="handleAdd">新增内容</button>
      </template>
    </PageHeader>

    <!-- 总览：分类统计 + 最近更新 -->
    <div class="kb-overview">
      <div class="kb-stats">
        <button
          v-for="t in typeNav"
          :key="t.key"
          class="kb-stat"
          :class="{ active: activeType === t.key }"
          :style="{ '--c': t.color }"
          @click="setType(t.key)"
        >
          <span class="kb-stat-name">{{ t.label }}</span>
          <b>{{ t.count }}</b>
        </button>
      </div>
      <div class="kb-recent">
        <span class="kb-recent-label">最近更新</span>
        <span
          v-for="it in recent"
          :key="it.id"
          class="kb-recent-item"
          @click="handleView(it.id)"
        >
          <span class="kb-mini-badge" :style="{ background: typeColor(it.kind) + '22', color: typeColor(it.kind) }">{{ typeLabel(it.kind) }}</span>
          {{ it.title }}
        </span>
        <span v-if="!recent.length" class="kb-recent-empty">暂无</span>
      </div>
    </div>

    <!-- 类型导航 + 标签云 + 搜索 + 视图切换 -->
    <div class="filter-bar">
      <div class="category-tabs" role="tablist">
        <button
          v-for="t in typeNav"
          :key="t.key"
          class="category-tab"
          :class="{ active: activeType === t.key }"
          role="tab"
          :aria-selected="activeType === t.key"
          @click="setType(t.key)"
        >
          {{ t.label }}
          <span class="tab-count">{{ t.count }}</span>
        </button>
      </div>

      <input
        v-model="searchKeyword"
        type="text"
        class="search-input"
        placeholder="搜索标题、内容、标签或结构化字段..."
      />

      <div class="view-toggle">
        <button class="view-btn" :class="{ active: view === 'grid' }" @click="view = 'grid'">网格</button>
        <button class="view-btn" :class="{ active: view === 'list' }" @click="view = 'list'">列表</button>
        <button class="view-btn" :class="{ active: view === 'timeline' }" @click="view = 'timeline'">时间线</button>
      </div>
    </div>

    <div v-if="tags.length" class="tag-cloud">
      <button
        v-for="t in tags"
        :key="t"
        class="cloud-tag"
        :class="{ active: activeTag === t }"
        @click="setTag(t)"
      >{{ t }}</button>
      <button v-if="activeType !== 'all' || activeTag || searchKeyword" class="cloud-clear" @click="clearFilters">清除筛选</button>
    </div>

    <!-- 网格 / 列表 -->
    <div v-if="results.length && view !== 'timeline'" class="kb-results" :class="'view-' + view">
      <article
        v-for="item in results"
        :key="item.id"
        class="knowledge-card"
        @click="handleView(item.id)"
      >
        <div class="card-header">
          <span class="category-badge" :style="{ background: typeColor(item.kind) + '22', color: typeColor(item.kind) }">
            {{ typeLabel(item.kind) }}
          </span>
          <span class="card-date">{{ formatDate(item.updatedAt || item.createdAt) }}</span>
        </div>
        <h3 class="card-title">{{ item.title }}</h3>
        <p class="card-excerpt">{{ structPreview(item) }}</p>
        <div class="card-tags" v-if="item.tags?.length">
          <span
            v-for="tag in item.tags.slice(0, 4)"
            :key="tag"
            class="tag"
            :class="{ active: activeTag === tag }"
            @click.stop="setTag(tag)"
          >{{ tag }}</span>
        </div>
        <div class="card-actions" @click.stop>
          <button class="btn-link" @click="handleEdit(item.id)">编辑</button>
          <button class="btn-link danger" @click="handleDelete(item.id)">删除</button>
        </div>
      </article>
    </div>

    <!-- 时间线 -->
    <div v-else-if="results.length && view === 'timeline'" class="kb-results view-timeline">
      <div v-for="g in timelineGroups" :key="g.date" class="kb-tl-group">
        <div class="kb-tl-date">{{ g.date }}</div>
        <article
          v-for="item in g.items"
          :key="item.id"
          class="knowledge-card"
          @click="handleView(item.id)"
        >
          <div class="card-header">
            <span class="category-badge" :style="{ background: typeColor(item.kind) + '22', color: typeColor(item.kind) }">
              {{ typeLabel(item.kind) }}
            </span>
            <span class="card-date">{{ formatDate(item.updatedAt || item.createdAt) }}</span>
          </div>
          <h3 class="card-title">{{ item.title }}</h3>
          <p class="card-excerpt">{{ structPreview(item) }}</p>
          <div class="card-tags" v-if="item.tags?.length">
            <span v-for="tag in item.tags.slice(0, 4)" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </article>
      </div>
    </div>

    <div v-else class="empty-state">
      <span class="empty-icon"></span>
      <span class="empty-text">没有匹配的知识，换个关键词或筛选条件试试</span>
      <button class="btn-secondary" @click="handleAdd">新增第一条</button>
    </div>

    <Modal :show="showDeleteModal" title="确认删除" size="small" @close="showDeleteModal = false">
      <p>确定要删除这篇内容吗？此操作不可撤销。</p>
      <template #footer>
        <button class="btn-secondary" @click="showDeleteModal = false">取消</button>
        <button class="btn-danger" @click="confirmDelete">确认删除</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.knowledge-view { padding: 24px; max-width: 1100px; width: 100%; }

.kb-overview { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 20px; align-items: stretch; }
.kb-stats { display: flex; flex-wrap: wrap; gap: 8px; flex: 1; min-width: 280px; }
.kb-stat {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  min-width: 76px; padding: 10px 14px; border: 1px solid var(--border);
  border-left: 3px solid var(--c); border-radius: var(--radius-md);
  background: var(--surface); color: var(--text-primary); cursor: pointer;
  transition: all var(--transition-fast);
}
.kb-stat:hover { box-shadow: var(--shadow-sm); }
.kb-stat.active { background: var(--accent-light); }
.kb-stat-name { font-size: 13px; color: var(--text-secondary); }
.kb-stat b { font-size: 18px; color: var(--c); }

.kb-recent {
  flex: 1; min-width: 240px; padding: 12px 14px; border: 1px solid var(--border);
  border-radius: var(--radius-md); background: var(--bg-secondary);
  display: flex; flex-direction: column; gap: 6px;
}
.kb-recent-label { font-size: 12px; color: var(--text-tertiary); }
.kb-recent-item {
  font-size: 13px; color: var(--text-primary); cursor: pointer;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kb-recent-item:hover { color: var(--accent); }
.kb-mini-badge { font-size: 11px; padding: 1px 6px; border-radius: 10px; margin-right: 4px; }
.kb-recent-empty { font-size: 13px; color: var(--text-tertiary); }

.filter-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 12px; }
.category-tabs {
  display: inline-flex; gap: 4px; padding: 4px;
  background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-md);
}
.category-tab {
  display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px; border: none;
  border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary);
  font-size: 14px; font-weight: 500; cursor: pointer; transition: all var(--transition-fast);
}
.category-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.category-tab.active { background: var(--surface); color: var(--text-primary); box-shadow: var(--shadow-sm); }
.tab-count { min-width: 20px; padding: 1px 6px; border-radius: 10px; background: var(--bg-tertiary); color: var(--text-secondary); font-size: 12px; font-weight: 500; text-align: center; }
.category-tab.active .tab-count { background: var(--accent-light); color: var(--accent); }

.search-input {
  flex: 1; min-width: 220px; padding: 10px 16px; border: 1px solid var(--border);
  border-radius: var(--radius-md); font-size: 14px; background: var(--surface); color: var(--text-primary);
}
.search-input:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--accent-light); }

.view-toggle {
  display: flex; padding: 3px; gap: 2px; background: var(--bg-secondary);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
}
.view-btn {
  padding: 7px 14px; border: none; border-radius: 4px; background: transparent;
  color: var(--text-secondary); font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all var(--transition-fast);
}
.view-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.view-btn.active { background: var(--surface); color: var(--accent); box-shadow: var(--shadow-sm); }

.tag-cloud { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }
.cloud-tag {
  padding: 4px 12px; border: 1px solid var(--border); border-radius: 20px;
  background: var(--surface); color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: all var(--transition-fast);
}
.cloud-tag:hover { border-color: var(--accent); color: var(--accent); }
.cloud-tag.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.cloud-clear { padding: 4px 12px; border: none; background: none; color: var(--text-tertiary); font-size: 13px; cursor: pointer; }

.kb-results.view-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.kb-results.view-list { display: flex; flex-direction: column; gap: 12px; }
.kb-results.view-timeline { display: flex; flex-direction: column; gap: 20px; }
.kb-tl-group { display: flex; flex-direction: column; gap: 12px; }
.kb-tl-date { font-size: 13px; font-weight: 600; color: var(--text-secondary); padding-bottom: 6px; border-bottom: 1px solid var(--border); }

.knowledge-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 20px; cursor: pointer; transition: all var(--transition-base);
}
.knowledge-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.category-badge { padding: 3px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }
.card-date { font-size: 13px; color: var(--text-tertiary); }
.card-title { margin: 0 0 8px; font-size: 17px; font-weight: 600; color: var(--text-primary); }
.card-excerpt {
  margin: 0 0 12px; font-size: 14px; color: var(--text-secondary); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.card-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.tag { padding: 3px 10px; background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: var(--radius-sm); font-size: 12px; color: var(--text-secondary); cursor: pointer; }
.tag.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.card-actions { display: flex; gap: 8px; padding-top: 14px; border-top: 1px solid var(--border-light); }
.btn-link {
  padding: 4px 10px; background: none; border: none; border-radius: var(--radius-sm);
  color: var(--accent); font-size: 13px; font-weight: 500; cursor: pointer; transition: all var(--transition-fast);
}
.btn-link:hover { background: var(--accent-light); }
.btn-link.danger { color: var(--danger); }
.btn-link.danger:hover { background: var(--danger-light); }

.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
  padding: 72px 20px; color: var(--text-secondary); background: var(--surface);
  border: 1px dashed var(--border); border-radius: var(--radius-lg);
}
.empty-icon { width: 48px; height: 48px; border-radius: 50%; background: var(--bg-secondary); }
.empty-text { font-size: 14px; color: var(--text-tertiary); }

@media (max-width: 640px) {
  .filter-bar { flex-direction: column; align-items: stretch; }
  .category-tabs { width: 100%; }
  .category-tab { flex: 1; justify-content: center; }
}
</style>
