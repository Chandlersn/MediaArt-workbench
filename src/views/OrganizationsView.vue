<template>
  <div class="organizations-page">
    <div class="page-header">
      <h2>机构管理</h2>
      <button class="btn-primary" @click="$router.push('/organizations/new')">
        添加机构
      </button>
    </div>

    <div class="filter-bar">
      <input
        v-model="searchKeyword"
        type="text"
        class="search-input"
        placeholder="搜索机构..."
      />
      <CustomSelect v-model="filterType">
        <option value="all">全部类型</option>
        <option value="培训机构">培训机构</option>
        <option value="艺术团体">艺术团体</option>
        <option value="设备供应商">设备供应商</option>
        <option value="媒体合作">媒体合作</option>
        <option value="场地提供">场地提供</option>
      </CustomSelect>
      <button
        class="btn-secondary"
        @click="toggleSelectAll"
      >
        {{ isAllSelected ? '取消全选' : '全选' }}
      </button>
    </div>

    <div class="org-list">
      <div v-if="filteredOrgs.length === 0" class="empty-state">
        {{ searchKeyword || filterType !== 'all' ? '没有找到匹配的机构' : '暂无机构' }}
      </div>
      <div
        v-for="org in filteredOrgs"
        :key="org.id"
        class="org-card"
        :class="{ 'selected': selectedIds.has(org.id) }"
        @click="$router.push(`/organizations/${org.id}`)"
      >
        <div class="org-card-header">
          <div class="org-header-left">
            <input
              type="checkbox"
              class="card-checkbox"
              :checked="selectedIds.has(org.id)"
              @click.stop="toggleSelect(org.id)"
            />
            <h3 class="org-name">{{ org.name }}</h3>
          </div>
          <span class="org-level" :class="getLevelClass(org.level)">
            {{ org.level || '待评估' }}
          </span>
        </div>
        <div class="org-card-body">
          <span class="org-type">{{ org.type || '未分类' }}</span>
          <span class="org-contact" v-if="org.contact">{{ org.contact }}</span>
        </div>
        <div class="org-card-footer">
          <span class="org-meta">合作次数: {{ getCoopCount(org) }}</span>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useOrganizationStore, useProjectStore } from '../stores'
import { parseOrgIds } from '../utils/dataHelpers'
import Pagination from '../components/Pagination.vue'
import { get } from '../services/http.js'
import CustomSelect from '../components/CustomSelect.vue'

const orgStore = useOrganizationStore()
const projectStore = useProjectStore()

const searchKeyword = ref('')
const filterType = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const totalCount = ref(0)
const totalPages = ref(0)
const organizations = ref([])
const loading = ref(false)
const selectedIds = ref(new Set())

// 加载分页数据
const loadOrgsPaginated = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: currentPage.value,
      pageSize: pageSize.value,
      search: searchKeyword.value
    })
    const result = await get(`/api/organizations/list?${params}`)

    if (result.success) {
      organizations.value = result.data
      totalCount.value = result.total
      totalPages.value = result.totalPages
    }
  } catch (e) {
    console.error('加载机构失败:', e)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  loadOrgsPaginated()
}

const handlePageSizeChange = (newPageSize) => {
  pageSize.value = newPageSize
  currentPage.value = 1
  loadOrgsPaginated()
}

onMounted(async () => {
  await loadOrgsPaginated()
  await projectStore.loadProjects()
})

// 搜索时重新加载
watch(searchKeyword, () => {
  currentPage.value = 1
  loadOrgsPaginated()
})

// 后端已按 search 过滤；这里再按前端选中的类型（org.type）做客户端筛选，
// 否则分类下拉是死的（选了不变）。选项值与数据显示的 org.type 同一套中文。
const filteredOrgs = computed(() => {
  if (filterType.value === 'all') return organizations.value
  return organizations.value.filter(o => (o.type || '未分类') === filterType.value)
})

const getLevelClass = (level) => {
  const classMap = {
    '核心伙伴': 'level-high',
    '普通合作': 'level-medium',
    '潜在合作': 'level-low',
    '待评估': 'level-default'
  }
  return classMap[level] || 'level-default'
}

const getCoopCount = (org) => {
  return projectStore.projects.filter(p => parseOrgIds(p.orgIds).includes(org.id)).length
}

const isAllSelected = computed(() => {
  const pageIds = filteredOrgs.value.map(o => o.id)
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
  const pageIds = filteredOrgs.value.map(o => o.id)
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
  if (!confirm(`确定要删除选中的 ${count} 个机构吗？此操作不可撤销。`)) return
  for (const id of selectedIds.value) {
    await orgStore.deleteOrganization(id)
  }
  selectedIds.value = new Set()
}
</script>

<style scoped>
.organizations-page {
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

.filter-select {
  padding: 10px 16px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  min-width: 140px;
}

.org-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.org-card {
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: all 0.2s;
}

.org-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.org-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.org-name {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.org-level {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.level-high { background: #fff2e6; color: #fa8c16; }
.level-medium { background: #e6f7ff; color: #1890ff; }
.level-low { background: #f5f5f5; color: #666; }
.level-default { background: #f5f5f5; color: #999; }

.org-card-body {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.org-type, .org-contact {
  font-size: 14px;
  color: var(--text-secondary, #666);
}

.org-card-footer {
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #eee);
}

.org-meta {
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

[data-theme="dark"] .level-high { background: rgba(251, 146, 60, 0.15); color: #fb923c; border: 1px solid rgba(251, 146, 60, 0.3); }
[data-theme="dark"] .level-medium { background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); }
[data-theme="dark"] .level-low { background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); }
[data-theme="dark"] .level-default { background: var(--bg-tertiary); color: var(--text-tertiary); border: 1px solid var(--border); }

.org-header-left {
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

.org-card.selected {
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
