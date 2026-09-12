<template>
  <div class="projects-page">
    <div class="page-header">
      <div class="page-header-left">
        <h2>项目管理</h2>
      </div>
      <div class="page-header-right">
        <button class="btn-primary" @click="$router.push('/projects/new')">
          新建项目
        </button>
      </div>
    </div>

    <div class="filter-bar">
      <input
        v-model="searchKeyword"
        type="text"
        class="search-input"
        placeholder="搜索项目..."
      />
      <CustomSelect v-model="filterStatus">
        <option value="all">全部状态</option>
        <option value="筹备中">筹备中</option>
        <option value="进行中">进行中</option>
        <option value="已结束">已结束</option>
        <option value="已归档">已归档</option>
      </CustomSelect>
      <button
        class="btn-secondary"
        @click="toggleSelectAll"
      >
        {{ isAllSelected ? '取消全选' : '全选' }}
      </button>
    </div>

    <div class="project-list">
      <div v-if="filteredProjects.length === 0" class="empty-state">
        {{ searchKeyword || filterStatus !== 'all' ? '没有找到匹配的项目' : '暂无项目' }}
      </div>
      <div
        v-for="project in filteredProjects"
        :key="project.id"
        class="project-card"
        :class="{ 'selected': selectedIds.has(project.id) }"
        @click="$router.push(`/projects/${project.id}`)"
      >
        <div class="project-card-header">
          <div class="project-header-left">
            <input
              type="checkbox"
              class="card-checkbox"
              :checked="selectedIds.has(project.id)"
              @click.stop="toggleSelect(project.id)"
            />
            <h3 class="project-name">{{ project.name }}</h3>
          </div>
          <span class="status-badge" :class="getStatusClass(project.status)">
            {{ project.status }}
          </span>
        </div>
        <div class="project-card-body">
          <div class="project-info">
            <span class="project-type">{{ project.type || '未分类' }}</span>
            <span class="project-date" v-if="project.startDate">
              {{ formatDate(project.startDate) }}
            </span>
          </div>
          <p class="project-desc" v-if="project.description">
            {{ project.description }}
          </p>
        </div>
        <div class="project-card-footer">
          <span class="project-meta">
            机构: {{ getOrgCount(project) }} | 选手: {{ getPlayerCount(project) }}
          </span>
        </div>
      </div>
    </div>

    <Pagination
      :total-items="totalCount"
      :page-size="pageSize"
      :current-page="currentPage"
      @page-change="handlePageChange"
      @page-size-change="handlePageSizeChange"
    />

    <div v-if="selectedIds.size > 0" class="batch-actions">
      <span>已选择 {{ selectedIds.size }} 项</span>
      <button @click="batchDelete" class="danger">批量删除</button>
      <button @click="clearSelection">取消选择</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, onActivated } from 'vue'
import { useProjectStore, useOrganizationStore, usePlayerStore } from '../stores'
import { parseOrgIds } from '../utils/dataHelpers'
import Pagination from '../components/Pagination.vue'
import { get } from '../services/http.js'
import CustomSelect from '../components/CustomSelect.vue'
import { useConfirmDialog } from '../composables/useConfirmDialog'

const projectStore = useProjectStore()
const orgStore = useOrganizationStore()
const playerStore = usePlayerStore()
const { confirm } = useConfirmDialog()

const searchKeyword = ref('')
const filterStatus = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const totalCount = ref(0)
const totalPages = ref(0)
const projects = ref([])
const loading = ref(false)
const selectedIds = ref(new Set())

// 加载分页数据
const loadProjectsPaginated = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: currentPage.value,
      pageSize: pageSize.value,
      search: searchKeyword.value
    })
    const result = await get(`/api/projects/list?${params}`)

    if (result.success) {
      projects.value = result.data
      totalCount.value = result.total
      totalPages.value = result.totalPages
    }
  } catch (e) {
    console.error('加载项目失败:', e)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  loadProjectsPaginated()
}

const handlePageSizeChange = (newPageSize) => {
  pageSize.value = newPageSize
  currentPage.value = 1
  loadProjectsPaginated()
}

onMounted(async () => {
  await loadProjectsPaginated()
  await orgStore.loadOrganizations()
  await playerStore.loadPlayers()
})

onActivated(async () => {
  await loadProjectsPaginated()
  await orgStore.loadOrganizations()
  await playerStore.loadPlayers()
})

// 搜索时重新加载
watch(searchKeyword, () => {
  currentPage.value = 1
  loadProjectsPaginated()
})

// filteredProjects 现在就是 projects（后端已过滤）
const filteredProjects = computed(() => projects.value)

const getStatusClass = (status) => {
  const classMap = {
    '筹备中': 'status-info',
    '进行中': 'status-success',
    '已结束': 'status-warning',
    '已归档': 'status-default'
  }
  return classMap[status] || 'status-default'
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

const getOrgCount = (project) => {
  return parseOrgIds(project.orgIds).length
}

const getPlayerCount = (project) => {
  return playerStore.getPlayersByProject(project.id).length
}

const isAllSelected = computed(() => {
  const pageIds = filteredProjects.value.map(p => p.id)
  return pageIds.length > 0 && pageIds.every(id => selectedIds.value.has(id))
})

const toggleSelect = (id) => {
  const newSet = new Set(selectedIds.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  selectedIds.value = newSet
}

const toggleSelectAll = () => {
  const pageIds = filteredProjects.value.map(p => p.id)
  const newSet = new Set(selectedIds.value)
  if (isAllSelected.value) {
    pageIds.forEach(id => newSet.delete(id))
  } else {
    pageIds.forEach(id => newSet.add(id))
  }
  selectedIds.value = newSet
}

const clearSelection = () => {
  selectedIds.value = new Set()
}

const batchDelete = async () => {
  const count = selectedIds.value.size
  const ok = await confirm({
    title: '删除确认',
    message: `确定要删除选中的 ${count} 个项目吗？此操作不可撤销。`,
    type: 'danger'
  })
  if (!ok) return
  for (const id of selectedIds.value) {
    await projectStore.deleteProject(id)
  }
  selectedIds.value = new Set()
}
</script>

<style scoped>
.projects-page {
  padding: 24px;
  max-width: 900px;
  width: 100%;
  margin: 0;
}

.page-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
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

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
}

.search-input {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
}

.filter-select {
  padding: 10px 16px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  min-width: 140px;
}

.project-list {
  display: grid;
  gap: 16px;
}

.project-card {
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: all 0.2s;
}

.project-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.project-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  min-width: 0;
}

.project-name {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #333);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.status-info { background: #e6f7ff; color: #1890ff; }
.status-success { background: #f6ffed; color: #52c41a; }
.status-warning { background: #fffbe6; color: #faad14; }
.status-default { background: #f5f5f5; color: #666; }

.project-card-body {
  margin-bottom: 12px;
}

.project-info {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
}

.project-type, .project-date {
  font-size: 14px;
  color: var(--text-secondary, #666);
}

.project-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary, #666);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.project-card-footer {
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #eee);
}

.project-meta {
  font-size: 12px;
  color: var(--text-secondary, #999);
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-secondary, #999);
  font-size: 14px;
  background: var(--bg-primary, #fff);
  border-radius: 12px;
}

[data-theme="dark"] .status-info { background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); }
[data-theme="dark"] .status-success { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }
[data-theme="dark"] .status-warning { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }
[data-theme="dark"] .status-default { background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); }

.project-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.card-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--accent);
  flex-shrink: 0;
}

.project-card.selected {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.batch-actions {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--accent);
  color: white;
  padding: 12px 24px;
  border-radius: 12px;
  box-shadow: var(--shadow-lg, 0 8px 24px rgba(0, 0, 0, 0.2));
  display: flex;
  align-items: center;
  gap: 16px;
  z-index: 100;
}

.batch-actions button {
  padding: 6px 16px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.3);
  background: rgba(255,255,255,0.15);
  color: white;
  cursor: pointer;
  font-size: 14px;
}

.batch-actions button:hover {
  background: rgba(255,255,255,0.25);
}

.batch-actions button.danger {
  background: var(--danger, #ff4d4f);
  border-color: var(--danger, #ff4d4f);
}
</style>
