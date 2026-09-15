<template>
  <div class="project-form-page">
    <div class="page-header">
      <h2>{{ isEdit ? '编辑项目' : '新建项目' }}</h2>
      <button class="btn-secondary" @click="$router.push('/projects')">
        返回列表
      </button>
    </div>

    <div class="form-page-content">
      <div class="form-section">
        <h3>基本信息</h3>
        <div class="form-grid">
          <div class="form-group">
            <label>项目名称 *</label>
            <input
              v-model="formData.name"
              type="text"
              class="form-input"
              placeholder="请输入项目名称"
            />
          </div>
          <div class="form-group">
            <label>项目类型</label>
            <CustomSelect v-model="formData.type" style="width:100%">
              <option value="">请选择</option>
              <option value="艺术展演">艺术展演</option>
              <option value="比赛活动">比赛活动</option>
              <option value="培训活动">培训活动</option>
              <option value="展览活动">展览活动</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>项目状态</label>
            <CustomSelect v-model="formData.status" style="width:100%">
              <option value="筹备中">筹备中</option>
              <option value="进行中">进行中</option>
              <option value="已结束">已结束</option>
              <option value="已归档">已归档</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>合作机构</label>
            <CustomSelect
              v-model="formData.orgIds"
              multiple
              :options="orgOptions"
              placeholder="请选择合作机构"
              style="width:100%"
            />
          </div>
          <div class="form-group">
            <label>项目负责人</label>
            <input
              v-model="formData.manager"
              type="text"
              class="form-input"
              placeholder="请输入负责人姓名"
            />
          </div>
          <div class="form-group">
            <label>开始日期</label>
            <input
              v-model="formData.startDate"
              type="date"
              class="form-input"
            />
          </div>
          <div class="form-group">
            <label>结束日期</label>
            <input
              v-model="formData.endDate"
              type="date"
              class="form-input"
            />
          </div>
          <div class="form-group">
            <label>预算</label>
            <input
              v-model="formData.budget"
              type="number"
              class="form-input"
              placeholder="请输入项目预算"
            />
          </div>
        </div>
      </div>

      <div class="form-section">
        <h3>项目描述</h3>
        <div class="form-group">
          <textarea
            v-model="formData.description"
            class="form-input"
            placeholder="请输入项目描述"
            rows="4"
          ></textarea>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn-secondary" @click="$router.push('/projects')">
          取消
        </button>
        <button class="btn-primary" @click="handleSave" :disabled="!formData.name">
          {{ isEdit ? '保存修改' : '创建项目' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useProjectStore, useOrganizationStore } from '../stores'
import { required, validate } from '../utils/formValidator'
import { useToast } from '../composables/useToast'
import CustomSelect from '../components/CustomSelect.vue'

const { success, error, warning } = useToast()

const router = useRouter()
const route = useRoute()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()

const isEdit = computed(() => !!route.params.id)

const formData = ref({
  name: '',
  type: '',
  status: '筹备中',
  orgIds: [],
  manager: '',
  startDate: '',
  endDate: '',
  budget: '',
  description: ''
})

const orgOptions = computed(() =>
  (orgStore.organizations || []).map(o => ({ value: o.id, label: o.name }))
)

onMounted(async () => {
  orgStore.loadOrganizations()
  projectStore.loadProjects()

  if (isEdit.value) {
    const project = projectStore.getProjectById(route.params.id)
    if (project) {
      formData.value = {
        name: project.name || '',
        type: project.type || '',
        status: project.status || '筹备中',
        orgIds: Array.isArray(project.orgIds) ? project.orgIds : (typeof project.orgIds === 'string' ? (() => { try { const p = JSON.parse(project.orgIds); return Array.isArray(p) ? p : [] } catch { return [] } })() : []),
        manager: project.manager || '',
        startDate: project.startDate || '',
        endDate: project.endDate || '',
        budget: project.budget || '',
        description: project.description || ''
      }
    }
  }
})

const handleSave = async () => {
  const { valid, errors } = validate({
    name: [() => required(formData.value.name, '项目名称')],
    type: [() => required(formData.value.type, '项目类型')]
  })

  if (!valid) {
    const firstError = Object.values(errors)[0]
    warning(firstError)
    return
  }

  try {
    await projectStore.saveProject(formData.value)
    success('保存成功')
    router.push('/projects')
  } catch (e) {
    console.error('保存失败:', e)
    error(`保存失败：${e.message}`)
  }
}
</script>

<style scoped>
/* 注：原此处有 `.page { padding: 24px }`，本组件无任何元素使用 `page` 类，属死 CSS，已移除。 */

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.form-page-content {
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.form-section {
  margin-bottom: 32px;
}

.form-section:last-of-type {
  margin-bottom: 0;
}

.form-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-light);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #333);
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  background-color: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
}

.form-input:disabled {
  background: var(--bg-secondary, #f5f5f5);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid var(--border-light);
  margin-top: 24px;
}

.btn-primary {
  padding: 10px 24px;
  background: var(--primary-color, #1890ff);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #40a9ff;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 24px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
}

[data-theme="dark"] .btn-primary:hover { background: var(--accent-hover); }
</style>
