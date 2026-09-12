<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useKnowledgeStore, KNOWLEDGE_TYPES } from '../stores'
import PageHeader from '../components/PageHeader.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'

const { success, error } = useToast()
const { confirm } = useConfirmDialog()
const route = useRoute()
const router = useRouter()
const knowledgeStore = useKnowledgeStore()
const { knowledge } = storeToRefs(knowledgeStore)

const item = computed(() => knowledgeStore.getItemById(route.params.id))

const typeDef = computed(() => item.value ? KNOWLEDGE_TYPES[item.value.kind] : null)
const typeLabel = computed(() => typeDef.value?.name || item.value?.kind || '')
const typeColor = computed(() => typeDef.value?.color || 'var(--accent)')

// 仅展示已填写的结构化字段
const filledFields = computed(() => {
  if (!item.value || !typeDef.value) return []
  return typeDef.value.fields
    .filter(f => item.value.fields && item.value.fields[f.key] != null && String(item.value.fields[f.key]).trim())
    .map(f => ({ ...f, value: item.value.fields[f.key] }))
})

const related = computed(() => (item.value ? knowledgeStore.recommendFor({ ...item.value, name: item.value.title }) : []))

const linkRoute = (l) => {
  if (l.type === 'project') return `/projects/${l.id}`
  if (l.type === 'player') return `/players/${l.id}`
  if (l.type === 'org') return `/organizations/${l.id}`
  return null
}

const formatDate = (s) => s ? new Date(s).toLocaleString('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) : '-'

const handleEdit = () => router.push(`/knowledge/${route.params.id}/edit`)
const handleDelete = async () => {
  const result = await confirm({ title: '确认删除', message: `确定要删除「${item.value?.title}」吗？此操作不可撤销。`, type: 'danger' })
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
const handleBack = () => router.push('/knowledge')
const openRelated = (id) => router.push(`/knowledge/${id}`)

onMounted(() => knowledgeStore.loadItems())
</script>

<template>
  <div class="knowledge-detail-page">
    <PageHeader
      :title="item?.title || '知识详情'"
      :description="item ? typeLabel : ''"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="handleBack">返回列表</button>
        <button class="btn btn-primary" @click="handleEdit" v-if="item">编辑</button>
        <button class="btn btn-danger" @click="handleDelete" v-if="item">删除</button>
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
              <span class="category-badge" :style="{ background: typeColor + '22', color: typeColor }">{{ typeLabel }}</span>
            </span>
          </div>
          <div class="detail-item" v-if="item.author">
            <span class="detail-label">记录人</span>
            <span class="detail-value">{{ item.author }}</span>
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

      <div class="detail-section" v-if="filledFields.length">
        <h3>{{ typeLabel }} · 结构化内容</h3>
        <div class="field-list">
          <div v-for="f in filledFields" :key="f.key" class="field-row">
            <div class="field-label">{{ f.label }}</div>
            <div class="field-value">
              <a v-if="f.key === 'url'" :href="f.value" target="_blank" rel="noopener">{{ f.value }}</a>
              <span v-else style="white-space: pre-wrap; word-break: break-word;">{{ f.value }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="detail-section" v-if="item.description">
        <h3>详细描述</h3>
        <div class="detail-body">{{ item.description }}</div>
      </div>

      <div class="detail-section" v-if="item.tags && item.tags.length">
        <h3>标签</h3>
        <div class="tags-list">
          <span v-for="tag in item.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>

      <div class="detail-section" v-if="item.links && item.links.length">
        <h3>关联业务</h3>
        <div class="tags-list">
          <span
            v-for="(l, i) in item.links"
            :key="i"
            class="tag link-tag"
            @click="router.push(linkRoute(l))"
          >{{ { project:'项目', player:'选手', org:'机构' }[l.type] }}：{{ l.name }}</span>
        </div>
      </div>

      <div class="detail-section" v-if="related.length">
        <h3>相关知识</h3>
        <div class="related-list">
          <div v-for="r in related" :key="r.id" class="related-item" @click="openRelated(r.id)">
            <span class="rel-badge" :style="{ background: (KNOWLEDGE_TYPES[r.kind]?.color || 'var(--accent)') + '22', color: (KNOWLEDGE_TYPES[r.kind]?.color || 'var(--accent)') }">{{ KNOWLEDGE_TYPES[r.kind]?.name }}</span>
            <span class="rel-title">{{ r.title }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-detail-page { padding: 24px; }
.detail-content {
  max-width: 800px; background: var(--bg-primary); border-radius: 12px;
  padding: 24px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.detail-section { margin-bottom: 28px; }
.detail-section:last-child { margin-bottom: 0; }
.detail-section h3 {
  font-size: 16px; font-weight: 600; color: var(--text-primary);
  margin: 0 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border-light);
}
.detail-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.detail-item { display: flex; flex-direction: column; gap: 4px; }
.detail-label { font-size: 12px; color: var(--text-secondary); }
.detail-value { font-size: 14px; color: var(--text-primary); font-weight: 500; }
.category-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; }

.field-list { display: flex; flex-direction: column; gap: 12px; }
.field-row { display: grid; grid-template-columns: 96px 1fr; gap: 12px; align-items: start; }
.field-label { font-size: 13px; color: var(--text-secondary); padding-top: 2px; }
.field-value { font-size: 14px; color: var(--text-primary); line-height: 1.7; }
.field-value a { color: var(--accent); }

.detail-body { font-size: 14px; color: var(--text-primary); line-height: 1.8; white-space: pre-wrap; word-break: break-word; }

.tags-list { display: flex; flex-wrap: wrap; gap: 8px; }
.tag {
  padding: 4px 12px; background: var(--bg-tertiary); border-radius: 4px;
  font-size: 12px; color: var(--text-secondary);
}
.link-tag { cursor: pointer; }
.link-tag:hover { color: var(--accent); background: var(--accent-light); }

.related-list { display: flex; flex-direction: column; gap: 8px; }
.related-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md);
  cursor: pointer; transition: all var(--transition-fast);
}
.related-item:hover { border-color: var(--accent); box-shadow: var(--shadow-sm); }
.rel-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; flex-shrink: 0; }
.rel-title { font-size: 14px; color: var(--text-primary); }

.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px;
  padding: 60px 20px; color: var(--text-secondary);
}
.empty-icon { font-size: 48px; opacity: 0.5; }
.empty-text { font-size: 14px; }

.btn { display: inline-flex; align-items: center; gap: 6px; padding: 10px 16px; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; border: none; transition: all 0.2s; }
.btn-primary { background: var(--accent); color: white; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-secondary { background: var(--bg-tertiary); color: var(--text-primary); border: 1px solid var(--border-color); }
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
.btn-danger { background: var(--danger-color); color: white; }
.btn-danger:hover { opacity: 0.9; }

[data-theme="dark"] .detail-content { box-shadow: 0 2px 8px rgba(0,0,0,0.4); }

@media (max-width: 640px) { .detail-grid { grid-template-columns: 1fr; } .field-row { grid-template-columns: 1fr; } }
</style>
