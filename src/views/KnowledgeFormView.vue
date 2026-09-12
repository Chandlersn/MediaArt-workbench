<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useKnowledgeStore, KNOWLEDGE_TYPES, KNOWLEDGE_TYPE_ORDER } from '../stores'
import { useProjectStore } from '../stores'
import { usePlayerStore } from '../stores'
import { useOrganizationStore } from '../stores'
import PageHeader from '../components/PageHeader.vue'
import { useToast } from '../composables/useToast'
import CustomSelect from '../components/CustomSelect.vue'

const { success, error, warning } = useToast()
const route = useRoute()
const router = useRouter()
const knowledgeStore = useKnowledgeStore()
const projectStore = useProjectStore()
const playerStore = usePlayerStore()
const organizationStore = useOrganizationStore()

const isEdit = computed(() => !!route.params.id)
const fieldDefs = computed(() => KNOWLEDGE_TYPES[formData.value.type]?.fields || [])

const formData = ref({
  title: '',
  type: route.query.type || 'guide',
  description: '',
  author: '',
  tags: '',
  fields: {},
  links: []
})

const linkType = ref('project')
const linkTarget = ref('')
const linkOptions = computed(() => {
  if (linkType.value === 'project') return (projectStore.projects || []).map(p => ({ id: p.id, name: p.name }))
  if (linkType.value === 'player') return (playerStore.players || []).map(p => ({ id: p.id, name: p.name }))
  return (organizationStore.organizations || []).map(o => ({ id: o.id, name: o.name }))
})
const linkLabel = { project: '项目', player: '选手', org: '机构' }
const linkTargetOptions = computed(() =>
  (linkOptions.value || []).map(o => ({ value: o.id, label: o.name }))
)

const addLink = () => {
  const opt = linkOptions.value.find(o => o.id === linkTarget.value)
  if (!opt) return
  if (formData.value.links.some(l => l.id === opt.id && l.type === linkType.value)) { warning('已关联'); return }
  formData.value.links.push({ type: linkType.value, id: opt.id, name: opt.name })
  linkTarget.value = ''
}
const removeLink = (i) => formData.value.links.splice(i, 1)

// 切换类型时清理不属于当前类型的结构化字段
watch(() => formData.value.type, () => {
  const keep = {}
  fieldDefs.value.forEach(f => { if (formData.value.fields[f.key] != null) keep[f.key] = formData.value.fields[f.key] })
  formData.value.fields = keep
})

onMounted(async () => {
  await knowledgeStore.loadItems()
  await Promise.all([projectStore.loadItems?.(), playerStore.loadItems?.(), organizationStore.loadItems?.()].filter(Boolean))
  if (isEdit.value) {
    const item = knowledgeStore.getItemById(route.params.id)
    if (item) {
      formData.value = {
        title: item.title || '',
        type: item.type || item.kind || 'guide',
        description: item.description || '',
        author: item.author || '',
        tags: Array.isArray(item.tags) ? item.tags.join(', ') : (item.tags || ''),
        fields: { ...(item.fields || {}) },
        links: Array.isArray(item.links) ? item.links : []
      }
    }
  }
})

const handleSave = async () => {
  if (!formData.value.title.trim()) { warning('请输入标题'); return }
  const tagsArray = formData.value.tags
    ? formData.value.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean)
    : []
  // 只保留当前类型的结构化字段
  const fields = {}
  fieldDefs.value.forEach(f => { if (formData.value.fields[f.key]) fields[f.key] = formData.value.fields[f.key] })

  const data = {
    title: formData.value.title.trim(),
    type: formData.value.type,
    description: formData.value.description,
    author: formData.value.author,
    tags: tagsArray,
    fields,
    links: formData.value.links
  }

  try {
    const saved = isEdit.value
      ? await knowledgeStore.updateItem(route.params.id, data)
      : await knowledgeStore.saveItem(data)
    success(isEdit.value ? '保存成功' : '创建成功')
    router.push(`/knowledge/${saved.id}`)
  } catch (err) {
    console.error('保存失败:', err)
    error(`保存失败：${err.message}`)
  }
}

const handleCancel = () => {
  router.push(isEdit.value ? `/knowledge/${route.params.id}` : '/knowledge')
}
</script>

<template>
  <div class="knowledge-form-page">
    <PageHeader
      :title="isEdit ? '编辑知识' : '新建知识'"
      :description="isEdit ? '修改知识库内容' : '添加新的知识库内容'"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="handleCancel">取消</button>
        <button class="btn btn-primary" @click="handleSave" :disabled="!formData.title.trim()">
          {{ isEdit ? '保存修改' : '创建' }}
        </button>
      </template>
    </PageHeader>

    <div class="form-content">
      <!-- 标题：页面主位，placeholder 兼作标签 -->
      <input
        v-model="formData.title"
        type="text"
        class="form-input title-input"
        placeholder="标题（必填）"
      />

      <!-- 次要属性收成一行，弱化存在感 -->
      <div class="meta-row">
        <CustomSelect v-model="formData.type" style="width:100%">
          <option v-for="t in KNOWLEDGE_TYPE_ORDER" :key="t" :value="t">{{ KNOWLEDGE_TYPES[t].name }}</option>
        </CustomSelect>
        <input v-model="formData.author" type="text" class="form-input" placeholder="记录人（选填）" />
        <input v-model="formData.tags" type="text" class="form-input" placeholder="标签，逗号分隔（选填）" />
      </div>
      <p class="type-desc">{{ KNOWLEDGE_TYPES[formData.type]?.desc }}</p>

      <!-- 结构化内容：随分类变化，是这张表单的主体 -->
      <div class="field-block">
        <div class="form-group" v-for="f in fieldDefs" :key="f.key">
          <label>{{ f.label }}</label>
          <textarea
            v-model="formData.fields[f.key]"
            class="form-input form-textarea"
            :placeholder="f.placeholder"
            :rows="f.rows || 2"
          ></textarea>
        </div>
      </div>

      <textarea
        v-model="formData.description"
        class="form-input form-textarea"
        placeholder="补充说明、背景或备注（选填）"
        rows="3"
      ></textarea>

      <!-- 关联业务不是每次都填，默认折叠 -->
      <details class="link-block">
        <summary>
          关联项目 / 选手 / 机构（选填）
          <span v-if="formData.links.length" class="link-count">{{ formData.links.length }}</span>
        </summary>
        <div class="link-editor">
          <div class="link-row">
            <CustomSelect v-model="linkType" style="width:120px">
              <option value="project">项目</option>
              <option value="player">选手</option>
              <option value="org">机构</option>
            </CustomSelect>
            <CustomSelect
              v-model="linkTarget"
              :options="linkTargetOptions"
              :placeholder="`选择${linkLabel[linkType]}…`"
              style="flex:1;min-width:160px"
            />
            <button class="btn-secondary btn-sm" @click="addLink">添加</button>
          </div>
          <div class="link-chips" v-if="formData.links.length">
            <span v-for="(l, i) in formData.links" :key="i" class="link-chip">
              {{ linkLabel[l.type] }}：{{ l.name }}
              <button class="link-chip-x" @click="removeLink(i)">移除</button>
            </span>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>

<style scoped>
.knowledge-form-page { padding: 24px; }
.form-content {
  max-width: 720px; background: var(--bg-primary); border-radius: 12px;
  padding: 24px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  display: flex; flex-direction: column; gap: 18px;
}

/* 标题占主位，靠字号和字重区分层级，不额外加标签 */
.title-input {
  font-size: 18px; font-weight: 600; padding: 12px 14px;
}

/* 次要属性挤在一行，弱化存在感 */
.meta-row { display: grid; grid-template-columns: 120px 1fr 1fr; gap: 10px; }
.type-desc { font-size: 12px; color: var(--text-tertiary); margin: -8px 0 0; }

.field-block { display: flex; flex-direction: column; gap: 14px; }

.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }

.form-input {
  width: 100%; padding: 10px 12px; font-size: 14px;
  border: 1px solid var(--border-color); border-radius: 6px;
  background-color: var(--bg-primary); color: var(--text-primary); transition: border-color 0.2s;
}
.form-input:focus { outline: none; border-color: var(--accent); }
.form-textarea { resize: vertical; min-height: 72px; line-height: 1.6; }

/* 关联业务默认收起，展开后才占空间 */
.link-block { border-top: 1px solid var(--border-light); padding-top: 14px; }
.link-block summary {
  cursor: pointer; font-size: 13px; color: var(--text-secondary);
  list-style: none; display: flex; align-items: center; gap: 6px;
}
.link-block summary::-webkit-details-marker { display: none; }
.link-block summary::before { content: '›'; color: var(--text-tertiary); transition: transform 0.2s; }
.link-block[open] summary::before { transform: rotate(90deg); }
.link-count {
  background: var(--accent-light); color: var(--accent);
  border-radius: 10px; padding: 0 7px; font-size: 12px;
}
.link-editor { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.link-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.link-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.link-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; background: var(--bg-secondary); border: 1px solid var(--border-light);
  border-radius: 20px; font-size: 13px; color: var(--text-primary);
}
.link-chip-x { border: none; background: none; color: var(--text-tertiary); cursor: pointer; font-size: 12px; }
.link-chip-x:hover { color: var(--danger); }

.btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 10px 16px;
  border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; border: none; transition: all 0.2s;
}
.btn-primary { background: var(--accent); color: white; }
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg-tertiary); color: var(--text-primary); border: 1px solid var(--border-color); }
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
.btn-sm { padding: 6px 12px; font-size: 13px; }

@media (max-width: 640px) { .meta-row { grid-template-columns: 1fr; } }
</style>
