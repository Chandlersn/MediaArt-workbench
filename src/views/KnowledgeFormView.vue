<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useKnowledgeStore } from '../stores'
import PageHeader from '../components/PageHeader.vue'
import { useToast } from '../composables/useToast'
import CustomSelect from '../components/CustomSelect.vue'
const { success, error, warning } = useToast()

const route = useRoute()
const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const isEdit = computed(() => !!route.params.id)

const categoryOptions = [
  { key: 'solutions', label: '解决方案' },
  { key: 'practices', label: '最佳实践' },
  { key: 'training', label: '培训资料' }
]

const formData = ref({
  title: '',
  category: route.query.category || 'solutions',
  content: '',
  tags: ''
})

onMounted(async () => {
  await knowledgeStore.loadItems()

  if (isEdit.value) {
    const item = knowledgeStore.getItemById(route.params.id)
    if (item) {
      formData.value = {
        title: item.title || '',
        category: item.category || item.type || 'solutions',
        content: item.content || '',
        tags: Array.isArray(item.tags) ? item.tags.join(', ') : (item.tags || '')
      }
    }
  }
})

const handleSave = async () => {
  if (!formData.value.title.trim()) {
    warning('请输入标题')
    return
  }

  try {
    const tagsArray = formData.value.tags
      ? formData.value.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean)
      : []

    const data = {
      title: formData.value.title.trim(),
      category: formData.value.category,
      type: formData.value.category,
      content: formData.value.content,
      tags: tagsArray
    }

    let savedItem
    if (isEdit.value) {
      savedItem = await knowledgeStore.updateItem(route.params.id, data)
    } else {
      savedItem = await knowledgeStore.saveItem(data)
    }

    success(isEdit.value ? '保存成功' : '创建成功')
    router.push(`/knowledge/${savedItem.id}`)
  } catch (err) {
    console.error('保存失败:', err)
    error(`保存失败：${err.message}`)
  }
}

const handleCancel = () => {
  if (isEdit.value) {
    router.push(`/knowledge/${route.params.id}`)
  } else {
    router.push('/knowledge')
  }
}
</script>

<template>
  <div class="knowledge-form-page">
    <PageHeader
      :title="isEdit ? '编辑知识' : '新建知识'"
      :description="isEdit ? '修改知识库内容' : '添加新的知识库内容'"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="handleCancel">
          取消
        </button>
        <button class="btn btn-primary" @click="handleSave" :disabled="!formData.title.trim()">
          {{ isEdit ? '保存修改' : '创建' }}
        </button>
      </template>
    </PageHeader>

    <div class="form-content">
      <div class="form-section">
        <h3>基本信息</h3>
        <div class="form-grid">
          <div class="form-group full-width">
            <label>标题 <span class="required">*</span></label>
            <input
              v-model="formData.title"
              type="text"
              class="form-input"
              placeholder="请输入标题"
            />
          </div>
          <div class="form-group">
            <label>分类</label>
            <CustomSelect v-model="formData.category" style="width:100%">
              <option v-for="opt in categoryOptions" :key="opt.key" :value="opt.key">
                {{ opt.label }}
              </option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>标签</label>
            <input
              v-model="formData.tags"
              type="text"
              class="form-input"
              placeholder="多个标签用逗号分隔"
            />
          </div>
        </div>
      </div>

      <div class="form-section">
        <h3>内容</h3>
        <div class="form-group">
          <textarea
            v-model="formData.content"
            class="form-input form-textarea"
            placeholder="请输入内容"
            rows="12"
          ></textarea>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-secondary" @click="handleCancel">
          取消
        </button>
        <button class="btn btn-primary" @click="handleSave" :disabled="!formData.title.trim()">
          {{ isEdit ? '保存修改' : '创建' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-form-page {
  padding: 24px;
}

.form-content {
  max-width: 800px;
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.form-section {
  margin-bottom: 28px;
}

.form-section:last-of-type {
  margin-bottom: 0;
}

.form-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-light);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.required {
  color: var(--danger-color);
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
}

.form-textarea {
  resize: vertical;
  min-height: 240px;
  line-height: 1.6;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid var(--border-light);
  margin-top: 24px;
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

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
</style>
