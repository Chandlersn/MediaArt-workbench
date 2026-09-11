<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '../stores'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const activeCategory = ref('solutions')
const searchKeyword = ref('')
const showDeleteModal = ref(false)
const deleteId = ref(null)

const categories = [
  { key: 'solutions', label: '解决方案' },
  { key: 'practices', label: '最佳实践' },
  { key: 'training', label: '培训资料' }
]

const categoryInfo = (key) => categories.find(c => c.key === key) || categories[0]

const filteredItems = computed(() => {
  let items = knowledgeStore.itemsByCategory(activeCategory.value) || []

  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    items = items.filter(item =>
      item.title?.toLowerCase().includes(kw) ||
      item.content?.toLowerCase().includes(kw) ||
      item.tags?.some(tag => tag.toLowerCase().includes(kw))
    )
  }

  return items
})

const handleAdd = () => {
  router.push(`/knowledge/new?category=${activeCategory.value}`)
}

const handleEdit = (id) => {
  router.push(`/knowledge/${id}/edit`)
}

const handleView = (id) => {
  router.push(`/knowledge/${id}`)
}

const handleDelete = (id) => {
  deleteId.value = id
  showDeleteModal.value = true
}

const confirmDelete = async () => {
  if (deleteId.value) {
    await knowledgeStore.deleteItem(deleteId.value)
    showDeleteModal.value = false
    deleteId.value = null
  }
}

const getCategoryCount = (category) => {
  return (knowledgeStore.itemsByCategory(category) || []).length
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

const excerpt = (content) => {
  if (!content) return ''
  return content.length > 120 ? `${content.substring(0, 120)}...` : content
}

const catLabel = (key) => categoryInfo(key).label
const catClass = (key) => `cat-${key}`

onMounted(() => {
  knowledgeStore.loadItems()
})

onActivated(() => {
  knowledgeStore.loadItems()
})
</script>

<template>
  <div class="knowledge-view">
    <PageHeader
      title="知识库"
      description="管理解决方案、最佳实践和培训资料"
    >
      <template #actions>
        <button class="btn-primary" @click="handleAdd">
          新增内容
        </button>
      </template>
    </PageHeader>

    <div class="filter-bar">
      <div class="category-tabs" role="tablist">
        <button
          v-for="cat in categories"
          :key="cat.key"
          class="category-tab"
          :class="{ active: activeCategory === cat.key }"
          role="tab"
          :aria-selected="activeCategory === cat.key"
          @click="activeCategory = cat.key"
        >
          {{ cat.label }}
          <span class="tab-count">{{ getCategoryCount(cat.key) }}</span>
        </button>
      </div>

      <input
        v-model="searchKeyword"
        type="text"
        class="search-input"
        placeholder="搜索标题、内容或标签..."
      />
    </div>

    <div class="knowledge-list" v-if="filteredItems.length > 0">
      <article
        v-for="item in filteredItems"
        :key="item.id"
        class="knowledge-card"
        @click="handleView(item.id)"
      >
        <div class="card-header">
          <span class="category-badge" :class="catClass(item.category)">
            {{ catLabel(item.category) }}
          </span>
          <span class="card-date">{{ formatDate(item.updatedAt || item.createdAt) }}</span>
        </div>
        <h3 class="card-title">{{ item.title }}</h3>
        <p class="card-excerpt">{{ excerpt(item.content) }}</p>
        <div class="card-tags" v-if="item.tags?.length">
          <span v-for="tag in item.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
        </div>
        <div class="card-actions" @click.stop>
          <button class="btn-link" @click="handleEdit(item.id)">编辑</button>
          <button class="btn-link danger" @click="handleDelete(item.id)">删除</button>
        </div>
      </article>
    </div>

    <div v-else class="empty-state">
      <span class="empty-icon"></span>
      <span class="empty-text">暂无{{ catLabel(activeCategory) }}</span>
      <button class="btn-secondary" @click="handleAdd">新增第一条</button>
    </div>

    <Modal
      :show="showDeleteModal"
      title="确认删除"
      size="small"
      @close="showDeleteModal = false"
    >
      <p>确定要删除这篇内容吗？此操作不可撤销。</p>
      <template #footer>
        <button class="btn-secondary" @click="showDeleteModal = false">取消</button>
        <button class="btn-danger" @click="confirmDelete">确认删除</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.knowledge-view {
  padding: 24px;
  max-width: 960px;
  width: 100%;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 24px;
}

.category-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.category-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.category-tab:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.category-tab.active {
  background: var(--surface);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.tab-count {
  min-width: 20px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  text-align: center;
}

.category-tab.active .tab-count {
  background: var(--accent-light);
  color: var(--accent);
}

.search-input {
  flex: 1;
  min-width: 220px;
  padding: 10px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: var(--surface);
  color: var(--text-primary);
}

.search-input:focus {
  outline: none;
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--accent-light);
}

.knowledge-list {
  display: grid;
  gap: 16px;
}

.knowledge-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  cursor: pointer;
  transition: all var(--transition-base);
}

.knowledge-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.category-badge {
  padding: 3px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.cat-solutions { background: #e6f7ff; color: #1890ff; }
.cat-practices { background: #f6ffed; color: #52c41a; }
.cat-training  { background: #fffbe6; color: #d48806; }

[data-theme="dark"] .cat-solutions { background: rgba(96, 165, 250, 0.15); color: #60a5fa; }
[data-theme="dark"] .cat-practices { background: rgba(52, 211, 153, 0.15); color: #34d399; }
[data-theme="dark"] .cat-training  { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }

.card-date {
  font-size: 13px;
  color: var(--text-tertiary);
}

.card-title {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-excerpt {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
}

.tag {
  padding: 3px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-secondary);
}

.card-actions {
  display: flex;
  gap: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
}

.btn-link {
  padding: 4px 10px;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-link:hover {
  background: var(--accent-light);
}

.btn-link.danger {
  color: var(--danger);
}

.btn-link.danger:hover {
  background: var(--danger-light);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 72px 20px;
  color: var(--text-secondary);
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
}

.empty-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--bg-secondary);
}

.empty-text {
  font-size: 14px;
  color: var(--text-tertiary);
}

@media (max-width: 640px) {
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
  .category-tabs {
    width: 100%;
  }
  .category-tab {
    flex: 1;
    justify-content: center;
  }
}
</style>