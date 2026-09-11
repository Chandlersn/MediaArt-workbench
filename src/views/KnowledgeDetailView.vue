<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useKnowledgeStore } from '../stores'
import PageHeader from '../components/PageHeader.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
const { success, error } = useToast()
const { confirm } = useConfirmDialog()

const route = useRoute()
const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const categories = [
  { key: 'solutions', label: '解决方案', icon: '💡' },
  { key: 'practices', label: '最佳实践', icon: '⭐' },
  { key: 'training', label: '培训资料', icon: '📚' }
]

const item = computed(() => knowledgeStore.getItemById(route.params.id))

const categoryLabel = computed(() => {
  if (!item.value) return ''
  return categories.find(c => c.key === item.value.category)?.label || item.value.category
})

const categoryIcon = computed(() => {
  if (!item.value) return ''
  return categories.find(c => c.key === item.value.category)?.icon || ''
})

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const handleEdit = () => {
  router.push(`/knowledge/${route.params.id}/edit`)
}

const handleDelete = async () => {
  const result = await confirm({
    title: '确认删除',
    message: `确定要删除「${item.value?.title}」吗？此操作不可撤销。`,
    type: 'danger'
  })
  if (!result) return

  try {
    await knowledgeStore.deleteItem(route.params.id)
    success('删除成功')
    router.push('/knowledge')
  } catch (err) {
    console.error('删除失败:', err)
    error('删除失败')
  }
}

const handleBack = () => {
  router.push('/knowledge')
}

onMounted(() => {
  knowledgeStore.loadItems()
})
</script>

<template>
  <div class="knowledge-detail-page">
    <PageHeader
      :title="item?.title || '知识详情'"
      :description="item ? `${categoryIcon} ${categoryLabel}` : ''"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="handleBack">
          返回列表
        </button>
        <button class="btn btn-primary" @click="handleEdit" v-if="item">
          编辑
        </button>
        <button class="btn btn-danger" @click="handleDelete" v-if="item">
          删除
        </button>
      </template>
    </PageHeader>

    <div v-if="!item" class="empty-state">
      <span class="empty-icon">📄</span>
      <span class="empty-text">内容不存在或已删除</span>
      <button class="btn btn-secondary" @click="handleBack">返回知识库</button>
    </div>

    <div v-else class="detail-content">
      <div class="detail-section">
        <h3>基本信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">分类</span>
            <span class="detail-value">
              <span class="category-badge" :class="'category-' + item.category">
                {{ categoryIcon }} {{ categoryLabel }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">创建时间</span>
            <span class="detail-value">{{ formatDate(item.createdAt) }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">更新时间</span>
            <span class="detail-value">{{ formatDate(item.updatedAt) }}</span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>内容</h3>
        <div class="detail-body">{{ item.content || '暂无内容' }}</div>
      </div>

      <div class="detail-section" v-if="item.tags?.length">
        <h3>标签</h3>
        <div class="tags-list">
          <span v-for="tag in item.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>
    </div>


  </div>
</template>

<style scoped>
.knowledge-detail-page {
  padding: 24px;
}

.detail-content {
  max-width: 800px;
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.detail-section {
  margin-bottom: 28px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-light);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.category-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.category-solutions {
  background: #e6f7ff;
  color: #1890ff;
}

.category-practices {
  background: #fff7e6;
  color: #fa8c16;
}

.category-training {
  background: #f6ffed;
  color: #52c41a;
}

.detail-body {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  padding: 4px 12px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 48px;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--accent);
  color: white;
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
}

.btn-danger {
  background: var(--danger-color);
  color: white;
}

.btn-danger:hover {
  opacity: 0.9;
}

[data-theme="dark"] .category-solutions { background: rgba(96, 165, 250, 0.15); color: #60a5fa; }
[data-theme="dark"] .category-practices { background: rgba(251, 146, 60, 0.15); color: #fb923c; }
[data-theme="dark"] .category-training { background: rgba(52, 211, 153, 0.15); color: #34d399; }
</style>
