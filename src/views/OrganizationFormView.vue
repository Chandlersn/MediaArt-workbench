<template>
  <div class="organization-form-page">
    <div class="page-header">
      <h2>{{ isEdit ? '编辑机构' : '添加机构' }}</h2>
      <button class="btn-secondary" @click="$router.push('/organizations')">
        返回列表
      </button>
    </div>
    <div class="form-page-content">
      <div class="form-section">
        <h3>基本信息</h3>
        <div class="form-grid">
          <div class="form-group">
            <label>机构名称 *</label>
            <input v-model="formData.name" type="text" class="form-input" placeholder="请输入机构名称" />
          </div>
          <div class="form-group">
            <label>机构类型</label>
            <CustomSelect v-model="formData.type" style="width:100%">
              <option value="培训机构">培训机构</option>
              <option value="艺术团体">艺术团体</option>
              <option value="设备供应商">设备供应商</option>
              <option value="媒体合作">媒体合作</option>
              <option value="场地提供">场地提供</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>合作等级</label>
            <CustomSelect v-model="formData.level" style="width:100%">
              <option value="待评估">待评估</option>
              <option value="潜在合作">潜在合作</option>
              <option value="普通合作">普通合作</option>
              <option value="核心伙伴">核心伙伴</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>联系人</label>
            <input v-model="formData.contact" type="text" class="form-input" placeholder="请输入联系人姓名" />
          </div>
          <div class="form-group">
            <label>联系电话</label>
            <input v-model="formData.phone" type="tel" class="form-input" placeholder="手机号或座机，如 13800138000 / 010-88886666" />
          </div>
          <div class="form-group">
            <label>机构地址</label>
            <input v-model="formData.address" type="text" class="form-input" placeholder="请输入机构地址" />
          </div>
        </div>
      </div>
      <div class="form-section">
        <h3>备注信息</h3>
        <div class="form-group">
          <textarea v-model="formData.note" class="form-input" placeholder="请输入备注信息" rows="4"></textarea>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn-secondary" @click="$router.push('/organizations')">取消</button>
        <button class="btn-primary" @click="handleSave" :disabled="!formData.name">
          {{ isEdit ? '保存修改' : '添加机构' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useOrganizationStore } from '../stores'
import { required, phone, validate } from '../utils/formValidator'
import { useMessage } from '../composables/useMessage'
import CustomSelect from '../components/CustomSelect.vue'

// 修复：下面用的是 warning(...)，但 Message 从未导入，校验失败时会抛
// ReferenceError（用户看不到任何提示）。改用项目里的 useMessage 组合式函数。
const { warning } = useMessage()

const route = useRoute()
const router = useRouter()
const orgStore = useOrganizationStore()

const isEdit = computed(() => !!route.params.id)

const formData = ref({
  name: '',
  type: '培训机构',
  level: '普通合作',
  contact: '',
  phone: '',
  address: '',
  note: ''
})

onMounted(async () => {
  if (isEdit.value) {
    await orgStore.loadOrganizations()
    const org = orgStore.organizations.find(o => o.id == route.params.id)
    if (org) {
      formData.value = { ...org }
    }
  }
})

const handleSave = async () => {
  const { valid, errors } = validate({
    name: [() => required(formData.value.name, '机构名称')],
    type: [() => required(formData.value.type, '机构类型')],
    phone: [() => phone(formData.value.phone)]
  })

  if (!valid) {
    const firstError = Object.values(errors)[0]
    warning(firstError)
    return
  }

  try {
    if (isEdit.value) {
      await orgStore.updateOrganization(route.params.id, formData.value)
    } else {
      await orgStore.addOrganization(formData.value)
    }
    router.push('/organizations')
  } catch (e) {
    console.error('保存机构失败:', e)
  }
}
</script>

<style scoped>
.organization-form-page {
  padding: 24px;
}

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

.form-section { margin-bottom: 32px; }

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

.form-group { display: flex; flex-direction: column; gap: 6px; }

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
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn-secondary {
  padding: 10px 24px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
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
</style>
