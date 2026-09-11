<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { useAuditLogStore } from '../stores'
import PageHeader from '../components/PageHeader.vue'
import CustomSelect from '../components/CustomSelect.vue'

const auditLogStore = useAuditLogStore()

const filterType = ref('all')
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = 20

const actionTypes = [
  { value: 'all', label: '全部操作' },
  { value: 'create', label: '创建' },
  { value: 'update', label: '更新' },
  { value: 'delete', label: '删除' },
  { value: 'login', label: '登录' },
  { value: 'logout', label: '登出' }
]

const logs = computed(() => auditLogStore.logs)
const loading = computed(() => auditLogStore.loading)

const filteredLogs = computed(() => {
  let result = logs.value

  if (filterType.value !== 'all') {
    result = result.filter(l => l.actionType === filterType.value)
  }

  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    result = result.filter(l =>
      l.userName?.toLowerCase().includes(kw) ||
      l.description?.toLowerCase().includes(kw) ||
      l.target?.toLowerCase().includes(kw)
    )
  }

  return result
})

const paginatedLogs = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredLogs.value.slice(start, start + pageSize)
})

const totalPages = computed(() => Math.ceil(filteredLogs.value.length / pageSize))

const getActionBadgeClass = (type) => {
  const classes = {
    create: 'action-create',
    update: 'action-update',
    delete: 'action-delete',
    login: 'action-login',
    logout: 'action-logout'
  }
  return classes[type] || 'action-default'
}

const getActionLabel = (type) => {
  const labels = {
    create: '创建',
    update: '更新',
    delete: '删除',
    login: '登录',
    logout: '登出'
  }
  return labels[type] || type
}

const formatDateTime = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

const handlePrevPage = () => {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

const handleNextPage = () => {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
  }
}

onMounted(() => {
  auditLogStore.loadLogs()
})

onActivated(() => {
  auditLogStore.loadLogs()
})
</script>

<template>
  <div class="audit-logs-view">
    <PageHeader
      title="审计日志"
      description="查看系统操作记录和用户活动"
    />

    <div class="filter-bar">
      <div class="filter-group">
        <CustomSelect v-model="filterType">
          <option v-for="t in actionTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
        </CustomSelect>
      </div>
      <input
        v-model="searchKeyword"
        type="text"
        class="search-input"
        placeholder="搜索操作人、内容或目标..."
      />
    </div>

    <div class="logs-stats">
      <div class="stat-item">
        <span class="stat-label">总记录数</span>
        <span class="stat-value">{{ filteredLogs.length }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">今日</span>
        <span class="stat-value">{{ logs.filter(l => formatDate(l.createdAt) === formatDate(new Date())).length }}</span>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <span class="loading-icon">⏳</span>
      <span>加载中...</span>
    </div>

    <div v-else class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>操作类型</th>
            <th>操作人</th>
            <th>描述</th>
            <th>操作对象</th>
            <th>IP地址</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="paginatedLogs.length === 0">
            <td colspan="6" class="empty-cell">
              <div class="empty-state">
                <span class="empty-icon">📋</span>
                <span>暂无日志记录</span>
              </div>
            </td>
          </tr>
          <tr v-for="log in paginatedLogs" :key="log.id">
            <td class="time-cell">{{ formatDateTime(log.createdAt) }}</td>
            <td>
              <span class="action-badge" :class="getActionBadgeClass(log.actionType)">
                {{ getActionLabel(log.actionType) }}
              </span>
            </td>
            <td>{{ log.userName }}</td>
            <td class="desc-cell">{{ log.description }}</td>
            <td>{{ log.target }}</td>
            <td class="ip-cell">{{ log.ip || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pagination" v-if="totalPages > 1">
      <button
        class="page-btn"
        :disabled="currentPage === 1"
        @click="handlePrevPage"
      >
        上一页
      </button>
      <span class="page-info">
        第 {{ currentPage }} / {{ totalPages }} 页
      </span>
      <button
        class="page-btn"
        :disabled="currentPage === totalPages"
        @click="handleNextPage"
      >
        下一页
      </button>
    </div>
  </div>
</template>

<style scoped>
.audit-logs-view {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  gap: 12px;
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  min-width: 140px;
}

.search-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  flex: 1;
  min-width: 160px;
  width: auto;
}

.logs-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.loading-icon {
  font-size: 24px;
}

.table-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 12px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
}

.data-table th {
  background: var(--bg-tertiary);
  font-weight: 600;
  color: var(--text-secondary);
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.time-cell {
  white-space: nowrap;
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.action-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.action-create {
  background: rgba(16, 185, 129, 0.1);
  color: var(--success-color);
}

.action-update {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.action-delete {
  background: rgba(220, 53, 69, 0.1);
  color: var(--danger-color);
}

.action-login,
.action-logout {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
}

.desc-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ip-cell {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.empty-cell {
  text-align: center;
  padding: 60px 20px !important;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 48px;
  opacity: 0.5;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
}

.page-btn {
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  background: var(--bg-hover);
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 14px;
  color: var(--text-secondary);
}

[data-theme="dark"] .action-update { color: var(--accent); }
[data-theme="dark"] .action-login, [data-theme="dark"] .action-logout { color: var(--text-secondary); }
</style>
