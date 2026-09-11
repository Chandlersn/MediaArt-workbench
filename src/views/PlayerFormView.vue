<template>
  <div class="player-form-page">
    <div class="page-header">
      <h2>{{ isEdit ? '编辑选手' : '添加选手' }}</h2>
      <button class="btn-secondary" @click="$router.push('/players')">
        返回列表
      </button>
    </div>

    <div class="form-page-content">
      <div class="form-section">
        <h3>基本信息</h3>
        <div class="form-grid">
          <div class="form-group">
            <label>姓名 *</label>
            <input v-model="formData.name" type="text" class="form-input" placeholder="请输入姓名" />
          </div>
          <div class="form-group">
            <label>性别</label>
            <CustomSelect v-model="formData.gender" style="width:100%">
              <option value="男">男</option>
              <option value="女">女</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>艺术类别</label>
            <CustomSelect v-model="formData.category" style="width:100%">
              <option value="">请选择</option>
              <option value="音乐">音乐</option>
              <option value="舞蹈">舞蹈</option>
              <option value="美术">美术</option>
              <option value="戏剧">戏剧</option>
              <option value="其他">其他</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>专业等级</label>
            <input v-model="formData.level" type="text" class="form-input" placeholder="请输入专业等级" />
          </div>
          <div class="form-group">
            <label>所属项目</label>
            <CustomSelect v-model="formData.projectId" style="width:100%">
              <option value="">请选择项目</option>
              <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>所属机构</label>
            <CustomSelect v-model="formData.orgId" style="width:100%">
              <option value="">请选择机构</option>
              <option v-for="o in organizations" :key="o.id" :value="o.id">{{ o.name }}</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>联系电话</label>
            <input v-model="formData.phone" type="text" class="form-input" placeholder="请输入联系电话" />
          </div>
          <div class="form-group">
            <label>身份证</label>
            <input v-model="formData.idCard" type="text" class="form-input" placeholder="请输入身份证号" />
          </div>
          <div class="form-group">
            <label>当前阶段</label>
            <CustomSelect v-model="formData.stage" style="width:100%">
              <option value="">请选择阶段</option>
              <option value="初赛">初赛</option>
              <option value="市赛">市赛</option>
              <option value="省赛">省赛</option>
              <option value="决赛">决赛</option>
            </CustomSelect>
          </div>
        </div>
      </div>

      <div class="form-section">
        <h3>备注信息</h3>
        <div class="form-group">
          <textarea v-model="formData.note" class="form-input" placeholder="请输入备注" rows="4"></textarea>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn-secondary" @click="$router.push('/players')">取消</button>
        <button class="btn-primary" @click="handleSave" :disabled="!formData.name">
          {{ isEdit ? '保存修改' : '添加选手' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { usePlayerStore, useProjectStore, useOrganizationStore } from '../stores'
import { required, phone, idCard, validate } from '../utils/formValidator'
import { useToast } from '../composables/useToast'
import CustomSelect from '../components/CustomSelect.vue'
const { success, error, warning } = useToast()

const router = useRouter()
const route = useRoute()
const playerStore = usePlayerStore()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()

const isEdit = computed(() => !!route.params.id)

const formData = ref({
  name: '',
  gender: '男',
  category: '',
  level: '',
  projectId: '',
  orgId: '',
  phone: '',
  idCard: '',
  stage: '',
  note: ''
})

const projects = computed(() => projectStore.projects)
const organizations = computed(() => orgStore.organizations)

onMounted(async () => {
  await Promise.all([
    projectStore.loadProjects(),
    orgStore.loadOrganizations(),
    playerStore.loadPlayers()
  ])

  if (isEdit.value) {
    const player = playerStore.getPlayerById(route.params.id)
    if (player) {
      formData.value = {
        name: player.name || '',
        gender: player.gender || '男',
        category: player.category || '',
        level: player.level || '',
        projectId: player.projectId || '',
        orgId: player.orgId || '',
        phone: player.phone || '',
        idCard: player.idCard || '',
        stage: player.stage || '',
        note: player.note || ''
      }
    }
  }
})

const handleSave = async () => {
  const { valid, errors } = validate({
    name: [() => required(formData.value.name, '姓名')],
    gender: [() => required(formData.value.gender, '性别')],
    category: [() => required(formData.value.category, '艺术类别')],
    phone: [() => phone(formData.value.phone)],
    idCard: [() => idCard(formData.value.idCard)]
  })

  if (!valid) {
    const firstError = Object.values(errors)[0]
    warning(firstError)
    return
  }

  try {
    await playerStore.savePlayer(formData.value)
    success('保存成功')
    router.push('/players')
  } catch (e) {
    console.error('保存失败:', e)
    error(`保存失败：${e.message}`)
  }
}
</script>

<style scoped>
.player-form-page {
  padding: 24px;
}

.form-content {
  max-width: 1200px;
  margin: 0 auto;
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
