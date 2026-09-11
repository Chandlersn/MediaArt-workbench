<template>
  <div class="material-config-page">
    <div class="page-header">
      <h2>资料配置管理</h2>
    </div>

    <div class="material-config-grid">
      <!-- 左侧：选手资料配置 -->
      <div class="config-column">
        <!-- 选手资料类型 -->
        <div class="config-section compact">
          <div class="section-header-with-action">
            <h3>选手资料类型</h3>
            <button class="btn-primary btn-sm" @click="openAddTypeModal">+ 添加</button>
          </div>
          <div class="material-types-list" id="materialTypesList">
            <div v-if="materialTypes.length === 0" class="empty-state">暂无资料类型，请点击上方按钮添加</div>
            <div v-for="type in materialTypes" :key="type.id" class="material-type-item">
              <div class="material-type-icon">{{ type.icon || '📄' }}</div>
              <div class="material-type-info">
                <div class="material-type-name">{{ type.name }}</div>
                <div class="material-type-category">{{ getCategoryLabel(type.category) }}</div>
              </div>
              <span
                :class="['material-type-badge', type.required ? 'required' : 'optional']"
                @click="toggleRequired(type.id)"
                title="点击切换必填/选填"
                style="cursor: pointer;"
              >
                {{ type.required ? '必填' : '选填' }}
              </span>
              <button class="icon-btn danger" @click="deleteMaterialType(type.id)" title="删除">✕</button>
            </div>
          </div>
        </div>

        <!-- 阶段资料配置 -->
        <div class="config-section compact">
          <h3>阶段资料配置</h3>
          <div class="stage-config-list">
            <div v-for="stage in stages" :key="stage" class="stage-config-item">
              <div class="stage-config-header">
                <span class="stage-config-title">{{ stage }}</span>
                <span class="badge">{{ getStageMaterials(stage).length }} 项资料</span>
              </div>
              <div class="stage-materials-tags">
                <span
                  v-for="typeName in getStageMaterials(stage)"
                  :key="typeName"
                  class="stage-material-tag"
                  @click="removeMaterialFromStage(stage, typeName)"
                  title="点击移除"
                >
                  {{ typeName }}
                  <span class="remove-icon">✕</span>
                </span>
                <span v-if="getStageMaterials(stage).length === 0" class="text-muted">未配置资料</span>
              </div>
              <div class="add-material-to-stage">
                <CustomSelect @change="addMaterialToStage(stage, $event)" style="width:100%">
                  <option value="">+ 添加资料类型</option>
                  <option
                    v-for="mt in getAvailableMaterials(stage)"
                    :key="mt.id"
                    :value="mt.name"
                  >
                    {{ mt.icon }} {{ mt.name }}
                  </option>
                </CustomSelect>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：项目与机构资料配置 -->
      <div class="config-column">
        <!-- 项目资料类型 -->
        <div class="config-section compact">
          <div class="section-header-with-action">
            <h3>项目资料类型</h3>
            <button class="btn-primary btn-sm" @click="addEntityMaterialType('projects')">+ 添加</button>
          </div>
          <div class="material-types-config" id="projectMaterialTypesConfig">
            <div v-for="type in projectMaterialTypes" :key="type.id" class="material-type-item">
              <div class="material-type-icon">{{ type.icon || '📄' }}</div>
              <div class="material-type-info">
                <input
                  v-model="type.name"
                  type="text"
                  class="inline-input"
                  @blur="saveConfig"
                  @keyup.enter="saveConfig"
                />
              </div>
              <button class="icon-btn danger" @click="deleteProjectMaterialType(type.id)" title="删除">✕</button>
            </div>
            <div v-if="projectMaterialTypes.length === 0" class="empty-state">暂无资料类型，请点击上方按钮添加</div>
          </div>
        </div>

        <!-- 机构资料类型 -->
        <div class="config-section compact">
          <div class="section-header-with-action">
            <h3>机构资料类型</h3>
            <button class="btn-primary btn-sm" @click="addEntityMaterialType('organizations')">+ 添加</button>
          </div>
          <div class="material-types-config" id="orgMaterialTypesConfig">
            <div v-for="type in orgMaterialTypes" :key="type.id" class="material-type-item">
              <div class="material-type-icon">{{ type.icon || '📄' }}</div>
              <div class="material-type-info">
                <input
                  v-model="type.name"
                  type="text"
                  class="inline-input"
                  @blur="saveConfig"
                  @keyup.enter="saveConfig"
                />
              </div>
              <button class="icon-btn danger" @click="deleteOrgMaterialType(type.id)" title="删除">✕</button>
            </div>
            <div v-if="orgMaterialTypes.length === 0" class="empty-state">暂无资料类型，请点击上方按钮添加</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加资料类型模态框 -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="closeAddTypeModal">
      <div class="modal">
        <div class="modal-header">
          <h3>添加资料类型</h3>
          <button class="modal-close" @click="closeAddTypeModal">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>类型名称</label>
            <input v-model="newMaterialType.name" type="text" class="form-input" placeholder="请输入类型名称" />
          </div>
          <div class="form-group">
            <label>分类</label>
            <CustomSelect v-model="newMaterialType.category" style="width:100%">
              <option value="document">📄 文档</option>
              <option value="image">🖼️ 图片</option>
              <option value="video">🎬 视频</option>
              <option value="audio">🎵 音频</option>
              <option value="other">📎 其他</option>
            </CustomSelect>
          </div>
          <div class="form-group">
            <label>图标（按分类自动匹配，可点选更换）</label>
            <div class="icon-picker">
              <button
                v-for="opt in currentIconOptions"
                :key="opt"
                type="button"
                class="icon-option"
                :class="{ active: newMaterialType.icon === opt }"
                @click="newMaterialType.icon = opt"
              >{{ opt }}</button>
            </div>
          </div>
          <div class="form-group checkbox">
            <label>
              <input v-model="newMaterialType.required" type="checkbox" />
              设为必填
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="closeAddTypeModal">取消</button>
          <button class="btn-primary" @click="saveMaterialType">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onActivated } from 'vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { get, post } from '../services/http.js'
import CustomSelect from '../components/CustomSelect.vue'
const { success, error, warning } = useToast()
const { confirm } = useConfirmDialog()

// 数据
const materialTypes = ref([])
const projectMaterialTypes = ref([])
const orgMaterialTypes = ref([])
const stages = ref(['初赛', '复赛', '半决赛', '决赛'])
const stageMaterialsConfig = ref({})
const showAddModal = ref(false)
const newMaterialType = ref({
  name: '',
  category: 'document',
  icon: '📄',
  required: false
})

// 图标按分类自动生成：每种分类有默认图标 + 一组可选预设，无需手动输入 emoji
const categoryIconMeta = {
  document: { default: '📄', options: ['📄', '📝', '📋', '📚', '📁', '🗂️', '📖'] },
  image:    { default: '🖼️', options: ['🖼️', '🎨', '📷', '🖌️', '✏️', '🖇️'] },
  video:    { default: '🎬', options: ['🎬', '🎥', '📹', '📺', '🍿', '🎞️'] },
  audio:    { default: '🎵', options: ['🎵', '🎧', '🎤', '🎙️', '🎶', '📻'] },
  other:    { default: '📎', options: ['📎', '📌', '📦', '🔖', '📦', '⭐'] }
}

const currentIconOptions = computed(() =>
  categoryIconMeta[newMaterialType.value.category]?.options || categoryIconMeta.document.options
)

// 切换分类时自动套用该分类的默认图标
watch(
  () => newMaterialType.value.category,
  (cat) => {
    newMaterialType.value.icon = categoryIconMeta[cat]?.default || '📎'
  }
)

// 方法
const getCategoryLabel = (category) => {
  const labels = {
    document: '📄 文档',
    image: '🖼️ 图片',
    video: '🎬 视频',
    audio: '🎵 音频',
    other: '📎 其他'
  }
  return labels[category] || '📎 其他'
}

const getStageMaterials = (stage) => {
  return stageMaterialsConfig.value[stage] || []
}

const getAvailableMaterials = (stage) => {
  const usedMaterials = getStageMaterials(stage)
  return materialTypes.value.filter(mt => !usedMaterials.includes(mt.name))
}

const openAddTypeModal = () => {
  newMaterialType.value = {
    name: '',
    category: 'document',
    icon: '📄',
    required: false
  }
  showAddModal.value = true
}

const closeAddTypeModal = () => {
  showAddModal.value = false
}

const saveMaterialType = async () => {
  if (!newMaterialType.value.name) {
    warning('请输入类型名称')
    return
  }

  // 检查是否已存在
  const existing = materialTypes.value.find(t => t.name === newMaterialType.value.name)
  if (existing) {
    warning('该资料类型已存在')
    return
  }

  const newType = {
    id: `mt${Date.now()}`,
    ...newMaterialType.value
  }

  materialTypes.value.push(newType)
  await saveConfig()
  success('资料类型已添加')
  closeAddTypeModal()
}

const toggleRequired = async (id) => {
  const type = materialTypes.value.find(t => t.id === id)
  if (type) {
    type.required = !type.required
    await saveConfig()
    success('已切换必填/选填状态')
  }
}

const deleteMaterialType = async (id) => {
  const confirmed = await confirm({
    title: '删除确认',
    message: '确定要删除这个资料类型吗？已配置的阶段关联也会被移除。',
    type: 'warning'
  })
  if (!confirmed) return

  const type = materialTypes.value.find(t => t.id === id)
  if (!type) return

  // 从所有阶段配置中移除
  stages.value.forEach(stage => {
    const materials = stageMaterialsConfig.value[stage] || []
    const index = materials.indexOf(type.name)
    if (index > -1) {
      materials.splice(index, 1)
    }
  })

  materialTypes.value = materialTypes.value.filter(t => t.id !== id)
  await saveConfig()
  success('资料类型已删除')
}

const addMaterialToStage = async (stage, typeName) => {
  if (!typeName) return

  const materials = getStageMaterials(stage)
  if (materials.includes(typeName)) {
    warning('该资料类型已存在')
    return
  }

  materials.push(typeName)
  await saveConfig()
  success(`已为 ${stage} 添加 ${typeName}`)
}

const removeMaterialFromStage = async (stage, typeName) => {
  const materials = getStageMaterials(stage)
  const index = materials.indexOf(typeName)
  if (index > -1) {
    materials.splice(index, 1)
    await saveConfig()
    success('已移除资料类型')
  }
}

const addEntityMaterialType = async (entityType) => {
  const newType = {
    id: `mt${Date.now()}`,
    name: '新类型',
    icon: '📄'
  }

  if (entityType === 'projects') {
    projectMaterialTypes.value.push(newType)
  } else if (entityType === 'organizations') {
    orgMaterialTypes.value.push(newType)
  }

  await saveConfig()
  success('资料类型已添加，请点击名称编辑')
}

const deleteProjectMaterialType = async (id) => {
  const confirmed = await confirm({
    title: '删除确认',
    message: '确定要删除这个项目资料类型吗？',
    type: 'warning'
  })
  if (!confirmed) return

  projectMaterialTypes.value = projectMaterialTypes.value.filter(t => t.id !== id)
  await saveConfig()
  success('项目资料类型已删除')
}

const deleteOrgMaterialType = async (id) => {
  const confirmed = await confirm({
    title: '删除确认',
    message: '确定要删除这个机构资料类型吗？',
    type: 'warning'
  })
  if (!confirmed) return

  orgMaterialTypes.value = orgMaterialTypes.value.filter(t => t.id !== id)
  await saveConfig()
  success('机构资料类型已删除')
}

const saveConfig = async () => {
  try {
    const result = await post('/api/save-stage-materials', {
      stageMaterials: stageMaterialsConfig.value,
      materialTypes: materialTypes.value,
      archiveConfig: {
        projects: { materialTypes: projectMaterialTypes.value },
        organizations: { materialTypes: orgMaterialTypes.value }
      }
    })
    if (result.success) {
      success('配置已保存')
    } else {
      error(`保存失败：${result.message}`)
    }
  } catch (e) {
    console.error('保存失败:', e)
    error(`保存失败：${e.message}`)
  }
}

const loadConfig = async () => {
  try {
    const result = await get('/api/data/load')

    if (result.data) {
      if (result.data.materialTypes) {
        materialTypes.value = result.data.materialTypes
      }
      if (result.data.config && result.data.config.stageMaterials) {
        stageMaterialsConfig.value = result.data.config.stageMaterials
      }
      if (result.data.archiveConfig) {
        if (result.data.archiveConfig.projects && result.data.archiveConfig.projects.materialTypes) {
          projectMaterialTypes.value = result.data.archiveConfig.projects.materialTypes
        }
        if (result.data.archiveConfig.organizations && result.data.archiveConfig.organizations.materialTypes) {
          orgMaterialTypes.value = result.data.archiveConfig.organizations.materialTypes
        }
      }
    }
  } catch (e) {
    console.error('加载配置失败:', e)
  }
}

onMounted(() => {
  loadConfig()
})

onActivated(() => {
  loadConfig()
})
</script>

<style scoped>
.material-config-page {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}

.material-config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

@media (max-width: 768px) {
  .material-config-grid {
    grid-template-columns: 1fr;
  }
}

.config-column {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.config-section {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.config-section.compact {
  padding: 16px;
}

.section-header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header-with-action h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.config-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.material-types-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.material-type-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  flex-wrap: wrap;
}

.material-type-icon {
  font-size: 20px;
}

.icon-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.icon-option {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.icon-option:hover {
  border-color: var(--border-focus);
  background: var(--bg-hover);
}

.icon-option.active {
  border-color: var(--accent);
  background: var(--accent-light);
  box-shadow: 0 0 0 3px var(--accent-light);
}

.material-type-info {
  flex: 1;
}

.material-type-name {
  font-weight: 500;
  color: var(--text-primary);
}

.material-type-category {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.material-type-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.material-type-badge.required {
  background: #ff4d4f;
  color: #fff;
}

.material-type-badge.optional {
  background: #f5f5f5;
  color: #666;
}

.icon-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.2s;
}

.icon-btn.danger {
  color: #ff4d4f;
}

.icon-btn:hover {
  background: var(--bg-hover);
}

.stage-config-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stage-config-item {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
}

.stage-config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stage-config-title {
  font-weight: 500;
  color: var(--text-primary);
}

.badge {
  background: var(--accent);
  color: #fff;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
}

.stage-materials-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.stage-material-tag {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  padding: 4px 12px;
  border-radius: 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.stage-material-tag:hover {
  border-color: #ff4d4f;
  color: #ff4d4f;
}

.remove-icon {
  margin-left: 4px;
  font-size: 12px;
}

.text-muted {
  color: var(--text-secondary);
  font-size: 13px;
}

.add-material-to-stage {
  margin-top: 8px;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  font-size: 14px;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
}

.inline-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-weight: 500;
  transition: all 0.2s;
}

.inline-input:hover {
  border-color: var(--accent);
  background: var(--bg-primary);
}

.inline-input:focus {
  outline: none;
  border-color: var(--accent);
  background: var(--bg-primary);
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.1);
}

.material-types-config {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}

/* 模态框样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.modal {
  background: var(--bg-secondary);
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: transparent;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.2s;
}

.modal-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.form-group.checkbox label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.form-group.checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light);
}

[data-theme="dark"] .material-type-badge.required { background: var(--danger-light); color: var(--danger); border-color: rgba(248, 113, 113, 0.3); }
[data-theme="dark"] .material-type-badge.optional { background: var(--bg-tertiary); color: var(--text-secondary); border-color: var(--border); }
[data-theme="dark"] .icon-btn.danger { color: var(--danger); }
[data-theme="dark"] .stage-material-tag:hover { border-color: var(--danger); color: var(--danger); }
</style>
