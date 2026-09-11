<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { useChecklistStore } from '../stores/checklist'
import { useProjectStore } from '../stores/project'
import PageHeader from '../components/PageHeader.vue'
import CustomSelect from '../components/CustomSelect.vue'

const checklistStore = useChecklistStore()
const projectStore = useProjectStore()

const newItems = ref({})  // cardId -> input text
const showResetConfirm = ref(false)
const resetTarget = ref(null)  // null = all, or tab key

// 项目筛选
const selectedProject = ref('')

// 当前 Tab 的清单
const activeChecklist = computed(() => checklistStore.activeChecklist)
const tabOptions = computed(() => checklistStore.tabOptions)
const activeTab = computed(() => checklistStore.activeTab)

// 项目列表
const projectList = computed(() => projectStore.projects || [])

// 获取卡片的进度
const getCardProgress = (cardId) => checklistStore.getProgress(cardId)

// 获取 Tab 的进度
const getTabProgress = (tabKey) => checklistStore.getTabProgress(tabKey)

// 进度条颜色
const progressColor = (percent) => {
  if (percent === 100) return 'var(--success, #52c41a)'
  if (percent >= 50) return 'var(--warning, #faad14)'
  return 'var(--primary, #1890ff)'
}

// 切换 Tab
const handleSwitchTab = (tab) => {
  checklistStore.switchTab(tab)
}

// 切换检查项
const handleToggle = async (cardId, itemIndex) => {
  await checklistStore.toggleItem(cardId, itemIndex)
}

// 添加自定义项
const handleAddItem = async (cardId) => {
  const text = newItems.value[cardId]?.trim()
  if (!text) return
  const ok = await checklistStore.addItem(cardId, text)
  if (ok) {
    newItems.value[cardId] = ''
  }
}

// 回车添加
const handleAddItemKeydown = (e, cardId) => {
  if (e.key === 'Enter') {
    handleAddItem(cardId)
  }
}

// 删除任意项（默认项与新加项均可删）
const handleRemoveItem = async (cardId, itemIndex) => {
  const ok = await checklistStore.removeItem(cardId, itemIndex)
  if (!ok) {
    alert('删除失败，请重试')
  }
}

// 重置清单
const handleReset = (tabKey = null) => {
  resetTarget.value = tabKey
  showResetConfirm.value = true
}

const confirmReset = async () => {
  await checklistStore.resetChecklist(resetTarget.value)
  showResetConfirm.value = false
  resetTarget.value = null
}

const cancelReset = () => {
  showResetConfirm.value = false
  resetTarget.value = null
}

// 项目筛选
const handleProjectChange = (projectId) => {
  selectedProject.value = projectId
  checklistStore.setProject(projectId)
}

onMounted(async () => {
  await Promise.all([
    checklistStore.loadChecklists(),
    projectStore.loadProjects()
  ])
  // 下拉框与 store 当前项目保持同步（store 跨页面保活）
  selectedProject.value = checklistStore.currentProject
})

onActivated(async () => {
  await Promise.all([
    checklistStore.loadChecklists(),
    projectStore.loadProjects()
  ])
  selectedProject.value = checklistStore.currentProject
})
</script>

<template>
  <div class="checklists-view">
    <PageHeader title="清单" description="赛事全流程清单管理，确保每个环节不遗漏">
      <template #actions>
        <CustomSelect
          v-model="selectedProject"
          @change="handleProjectChange(selectedProject)"
        >
          <option value="">全部项目</option>
          <option v-for="proj in projectList" :key="proj.id" :value="proj.id">
            {{ proj.name }}
          </option>
        </CustomSelect>
        <button class="btn btn-secondary" @click="handleReset()">
          重置清单
        </button>
      </template>
    </PageHeader>

    <!-- Tab 切换 -->
    <div class="checklist-tabs">
      <button
        v-for="tab in tabOptions"
        :key="tab.key"
        :class="['tab-btn', { active: activeTab === tab.key }]"
        @click="handleSwitchTab(tab.key)"
      >
        {{ tab.label }}
        <span class="tab-progress">{{ getTabProgress(tab.key).percent }}%</span>
      </button>
    </div>

    <!-- 清单内容 -->
    <div class="checklist-content">
      <div class="checklist-grid">
        <div
          v-for="card in activeChecklist.cards"
          :key="card.id"
          class="checklist-card"
        >
          <!-- 卡片头部 -->
          <div class="card-header">
            <h3 class="card-title">{{ card.title }}</h3>
            <span
              class="card-progress"
              :style="{ color: progressColor(getCardProgress(card.id).percent) }"
            >
              {{ getCardProgress(card.id).checked }}/{{ getCardProgress(card.id).total }} 完成
            </span>
          </div>

          <!-- 进度条 -->
          <div class="progress-bar-wrapper">
            <div
              class="progress-bar-fill"
              :style="{
                width: getCardProgress(card.id).percent + '%',
                background: progressColor(getCardProgress(card.id).percent)
              }"
            />
          </div>

          <!-- 检查项列表 -->
          <div class="card-items">
            <label
              v-for="(item, index) in card.items"
              :key="index"
              :class="['checklist-item', { checked: item.checked }]"
            >
              <input
                type="checkbox"
                :checked="item.checked"
                @change="handleToggle(card.id, index)"
              />
              <span class="item-text">{{ item.text }}</span>
              <button
                class="item-delete-btn"
                title="删除此项"
                @click.prevent="handleRemoveItem(card.id, index)"
              >
                &times;
              </button>
            </label>
          </div>

          <!-- 添加自定义项 -->
          <div class="card-add-item">
            <input
              v-model="newItems[card.id]"
              type="text"
              class="add-item-input"
              placeholder="添加新项..."
              @keydown="handleAddItemKeydown($event, card.id)"
            />
            <button
              class="add-item-btn"
              @click="handleAddItem(card.id)"
            >
              +
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 重置确认弹窗 -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showResetConfirm" class="modal-overlay" @click.self="cancelReset">
          <div class="confirm-modal">
            <div class="modal-header">
              <span class="modal-icon">&#9888;</span>
              <h3>重置清单</h3>
            </div>
            <div class="modal-body">
              确定要重置{{ resetTarget ? '当前清单' : '所有清单' }}吗？此操作不可撤销。
            </div>
            <div class="modal-footer">
              <button class="btn-secondary" @click="cancelReset">取消</button>
              <button class="btn-danger" @click="confirmReset">确认重置</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.checklists-view {
  max-width: 900px;
  margin: 0 auto;
}

/* ===== Tab 切换 ===== */
.checklist-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 24px;
  border-bottom: 2px solid var(--border-color, #e8e8e8);
  overflow-x: auto;
}

.tab-btn {
  position: relative;
  padding: 10px 20px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #666);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.2s, border-color 0.2s;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}

.tab-btn:hover {
  color: var(--primary, #1890ff);
}

.tab-btn.active {
  color: var(--primary, #1890ff);
  border-bottom-color: var(--primary, #1890ff);
}

.tab-progress {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--bg-tertiary, #f0f0f0);
  color: var(--text-tertiary, #999);
}

.tab-btn.active .tab-progress {
  background: rgba(24, 144, 255, 0.1);
  color: var(--primary, #1890ff);
}

/* ===== 清单网格 ===== */
.checklist-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

@media (max-width: 480px) {
  .checklist-grid {
    grid-template-columns: 1fr;
  }
}

/* ===== 清单卡片 ===== */
.checklist-card {
  background: var(--bg-secondary, #fff);
  border: 1px solid var(--border-color, #e8e8e8);
  border-radius: 12px;
  padding: 20px;
  transition: box-shadow 0.2s;
}

.checklist-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.card-progress {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary, #999);
}

/* ===== 进度条 ===== */
.progress-bar-wrapper {
  height: 4px;
  background: var(--bg-tertiary, #f0f0f0);
  border-radius: 2px;
  margin-bottom: 16px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease, background 0.3s ease;
}

/* ===== 检查项 ===== */
.card-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.checklist-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  user-select: none;
}

.checklist-item:hover {
  background: var(--bg-tertiary, #f5f5f5);
}

.checklist-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary, #1890ff);
  cursor: pointer;
  flex-shrink: 0;
}

.checklist-item .item-text {
  flex: 1;
  font-size: 14px;
  color: var(--text-primary, #333);
  line-height: 1.5;
  transition: color 0.2s, text-decoration 0.2s;
}

.checklist-item.checked .item-text {
  color: var(--text-tertiary, #999);
  text-decoration: line-through;
}

.item-delete-btn {
  display: none;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--text-tertiary, #999);
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
  line-height: 1;
  flex-shrink: 0;
  transition: color 0.15s, background 0.15s;
}

.checklist-item:hover .item-delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
}

.item-delete-btn:hover {
  color: var(--danger, #ff4d4f);
  background: rgba(255, 77, 79, 0.1);
}

/* ===== 添加项 ===== */
.card-add-item {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.add-item-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border-color, #d9d9d9);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  outline: none;
  transition: border-color 0.2s;
}

.add-item-input:focus {
  border-color: var(--primary, #1890ff);
}

.add-item-input::placeholder {
  color: var(--text-quaternary, #bfbfbf);
}

.add-item-btn {
  width: 36px;
  height: 36px;
  border: 1px dashed var(--border-color, #d9d9d9);
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary, #999);
  font-size: 18px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.add-item-btn:hover {
  border-color: var(--primary, #1890ff);
  color: var(--primary, #1890ff);
  background: rgba(24, 144, 255, 0.05);
}

/* ===== 弹窗 ===== */
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
  z-index: 9998;
}

.confirm-modal {
  background: var(--bg-secondary, #fff);
  border-radius: 12px;
  width: 90%;
  max-width: 400px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
}

.modal-icon {
  font-size: 24px;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.modal-body {
  padding: 20px;
  font-size: 14px;
  color: var(--text-primary, #333);
  line-height: 1.6;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light, #f0f0f0);
}

/* ===== 按钮样式 ===== */
.btn-secondary {
  padding: 6px 16px;
  border: 1px solid var(--border-color, #d9d9d9);
  border-radius: 6px;
  background: var(--bg-secondary, #fff);
  color: var(--text-primary, #333);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  border-color: var(--primary, #1890ff);
  color: var(--primary, #1890ff);
}

.btn-danger {
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  background: var(--danger, #ff4d4f);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-danger:hover {
  opacity: 0.85;
}

/* ===== 动画 ===== */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: all 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .confirm-modal,
.modal-fade-leave-to .confirm-modal {
  transform: scale(0.9);
}
</style>
