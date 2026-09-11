<template>
  <div class="finance-form-page">
    <div class="page-header">
      <h2>{{ isEdit ? '编辑财务记录' : '添加财务记录' }}</h2>
    </div>

    <form class="form-container" @submit.prevent="handleSave">
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">类型 <span class="required">*</span></label>
          <CustomSelect v-model="formData.type" style="width:100%">
            <option value="收入">收入</option>
            <option value="支出">支出</option>
          </CustomSelect>
        </div>
        <div class="form-group">
          <label class="form-label">分类 <span class="required">*</span></label>
          <CustomSelect v-model="formData.category" style="width:100%">
            <option value="">请选择分类</option>
            <option value="培训费">培训费</option>
            <option value="场地费">场地费</option>
            <option value="设备费">设备费</option>
            <option value="宣传费">宣传费</option>
            <option value="差旅费">差旅费</option>
            <option value="餐饮费">餐饮费</option>
            <option value="培训收入">培训收入</option>
            <option value="演出收入">演出收入</option>
            <option value="门票收入">门票收入</option>
            <option value="赞助收入">赞助收入</option>
            <option value="其他">其他</option>
          </CustomSelect>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label class="form-label">金额 <span class="required">*</span></label>
          <input
            v-model.number="formData.amount"
            type="number"
            class="form-input"
            placeholder="请输入金额"
            required
            min="0"
            step="0.01"
          />
        </div>
        <div class="form-group">
          <label class="form-label">日期 <span class="required">*</span></label>
          <input
            v-model="formData.date"
            type="date"
            class="form-input"
            required
            :max="today"
          />
          <small class="form-hint">日期不能超过今天</small>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label class="form-label">关联机构</label>
          <CustomSelect v-model="formData.orgId" style="width:100%">
            <option value="">请选择机构</option>
            <option v-for="org in organizations" :key="org.id" :value="org.id">
              {{ org.name }}
            </option>
          </CustomSelect>
        </div>
        <div class="form-group">
          <label class="form-label">关联项目</label>
          <CustomSelect v-model="formData.projectId" style="width:100%">
            <option value="">请选择项目</option>
            <option v-for="project in projects" :key="project.id" :value="project.id">
              {{ project.name }}
            </option>
          </CustomSelect>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">摘要</label>
        <input
          v-model="formData.title"
          type="text"
          class="form-input"
          placeholder="请输入摘要"
        />
      </div>

      <div class="form-group">
        <label class="form-label">备注</label>
        <textarea
          v-model="formData.note"
          class="form-input"
          rows="3"
          placeholder="请输入备注"
        ></textarea>
      </div>

      <div class="form-actions">
        <button type="button" class="btn-secondary" @click="$router.push('/finance')">取消</button>
        <button type="submit" class="btn-primary" :disabled="!isValid">{{ isEdit ? '保存修改' : '保存记录' }}</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFinanceStore } from '../stores/finance'
import { useProjectStore } from '../stores/project'
import { useOrganizationStore } from '../stores/organization'
import { required, positiveNumber, validate } from '../utils/formValidator'
import { useMessage } from '../composables/useMessage'
import CustomSelect from '../components/CustomSelect.vue'

// 修复：下面用的是 Message.xxx(...)，但 Message 从未导入，校验失败/保存出错时
// 会抛 ReferenceError（用户看不到任何提示）。改用项目里的 useMessage 组合式函数。
const { warning, success, error } = useMessage()

const route = useRoute()
const router = useRouter()
const financeStore = useFinanceStore()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()

const isEdit = computed(() => !!route.params.id)

const today = new Date().toISOString().split('T')[0]

const formData = ref({
  type: '收入',
  category: '',
  amount: '',
  date: today,
  orgId: '',
  projectId: '',
  title: '',
  note: ''
})

const isValid = computed(() => {
  return formData.value.type && formData.value.category && formData.value.amount > 0 && formData.value.date
})

const projects = computed(() => projectStore.projects)
const organizations = computed(() => orgStore.organizations)

onMounted(async () => {
  await projectStore.loadProjects()
  await orgStore.loadOrganizations()

  if (isEdit.value) {
    await financeStore.loadRecords()
    const record = financeStore.financeRecords.find(r => r.id == route.params.id)
    if (record) {
      formData.value = { ...record }
    }
  }
})

const handleSave = async () => {
  const { valid, errors } = validate({
    type: [() => required(formData.value.type, '类型')],
    category: [() => required(formData.value.category, '分类')],
    amount: [
      () => required(formData.value.amount, '金额'),
      () => positiveNumber(formData.value.amount, '金额')
    ],
    date: [() => required(formData.value.date, '日期')]
  })

  if (!valid) {
    const firstError = Object.values(errors)[0]
    warning(firstError)
    return
  }

  try {
    if (isEdit.value) {
      await financeStore.updateRecord(route.params.id, formData.value)
    } else {
      await financeStore.addRecord(formData.value)
    }
    success('保存成功')
    router.push('/finance')
  } catch (e) {
    console.error('保存失败:', e)
    error(`保存失败：${e.message}`)
  }
}
</script>

<style scoped>
.finance-form-page {
  padding: 0;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 24px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.form-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.required {
  color: #ef4444;
}

.form-input {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 14px;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  transition: all 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-light);
}

.form-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 24px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
}

@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}

[data-theme="dark"] .required { color: var(--danger); }
</style>
