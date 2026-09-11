<template>
  <div class="finance-page">
    <div class="page-header">
      <h2>运营管理</h2>
      <div class="header-actions">
        <button class="btn-secondary" @click="exportReport">导出报表</button>
        <button class="btn-primary" @click="handleAdd">添加记录</button>
      </div>
    </div>

    <div class="finance-stats">
      <div class="stat-card income">
        <div class="stat-icon">↑</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatCurrency(stats.totalIncome) }}</div>
          <div class="stat-label">总收入</div>
        </div>
      </div>
      <div class="stat-card expense">
        <div class="stat-icon">↓</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatCurrency(stats.totalExpense) }}</div>
          <div class="stat-label">总支出</div>
        </div>
      </div>
      <div class="stat-card profit">
        <div class="stat-icon">¥</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatCurrency(stats.netBalance) }}</div>
          <div class="stat-label">净利润</div>
        </div>
      </div>
      <div class="stat-card monthly">
        <div class="stat-icon">◆</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatCurrency(stats.monthlyProfit) }}</div>
          <div class="stat-label">本月盈亏</div>
        </div>
      </div>
    </div>

    <div class="finance-charts">
      <div class="chart-card">
        <h3 class="chart-title">收支趋势</h3>
        <canvas ref="trendChartEl" id="financeTrendChart"></canvas>
      </div>
      <div class="chart-card">
        <h3 class="chart-title">分类占比</h3>
        <div class="chart-tabs">
          <button
            class="chart-tab"
            :class="{ active: pieChartMode === 'income' }"
            @click="switchPieChart('income')"
          >收入</button>
          <button
            class="chart-tab"
            :class="{ active: pieChartMode === 'expense' }"
            @click="switchPieChart('expense')"
          >支出</button>
        </div>
        <canvas ref="categoryChartEl" id="financeCategoryChart"></canvas>
      </div>
    </div>

    <div class="category-stats-section">
      <h3 class="section-title">分类统计</h3>
      <div class="category-stats-grid">
        <div
          v-for="(value, key) in categoryStats"
          :key="key"
          class="category-stat-item"
        >
          <span class="category-stat-label">{{ key }}</span>
          <span class="category-stat-value">{{ formatCurrency(value) }}</span>
        </div>
        <div v-if="Object.keys(categoryStats).length === 0" class="empty-state">
          暂无分类数据
        </div>
      </div>
    </div>

    <div class="filter-bar">
      <input
        v-model="filterSearch"
        type="text"
        class="search-input"
        placeholder="搜索摘要..."
      />
      <CustomSelect v-model="filterYear">
        <option value="all">全部年份</option>
        <option v-for="year in yearOptions" :key="year" :value="year">{{ year }}</option>
      </CustomSelect>
      <CustomSelect v-model="filterType">
        <option value="all">全部类型</option>
        <option value="收入">收入</option>
        <option value="支出">支出</option>
      </CustomSelect>
      <CustomSelect v-model="filterOrg">
        <option value="all">全部机构</option>
        <option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option>
      </CustomSelect>
      <CustomSelect v-model="filterProject">
        <option value="all">全部项目</option>
        <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
      </CustomSelect>
      <CustomSelect v-model="filterMonth">
        <option value="all">全部月份</option>
        <option value="01">1月</option>
        <option value="02">2月</option>
        <option value="03">3月</option>
        <option value="04">4月</option>
        <option value="05">5月</option>
        <option value="06">6月</option>
        <option value="07">7月</option>
        <option value="08">8月</option>
        <option value="09">9月</option>
        <option value="10">10月</option>
        <option value="11">11月</option>
        <option value="12">12月</option>
      </CustomSelect>
      <button class="btn-secondary btn-sm" @click="resetFilters">重置</button>
    </div>

    <div class="filter-summary" v-if="hasActiveFilters">
      <span class="filter-summary-text">{{ filterSummaryText }}</span>
      <span class="filter-summary-stats">{{ filteredSummaryStats }}</span>
      <button class="btn-text btn-sm" @click="clearFilters">清除筛选</button>
    </div>

    <div class="finance-list">
      <div v-if="filteredRecords.length === 0" class="empty-state">
        暂无财务记录
      </div>
      <div
        v-for="record in paginatedRecords"
        :key="record.id"
        class="finance-item"
        :class="record.type === '收入' ? 'income' : 'expense'"
      >
        <div class="finance-item-main">
          <div class="finance-item-header">
            <span class="finance-type-badge" :class="record.type === '收入' ? 'income' : 'expense'">
              {{ record.type }}
            </span>
            <span class="finance-category">{{ record.category || '-' }}</span>
            <span class="finance-date">{{ formatDate(record.date) }}</span>
          </div>
          <div class="finance-item-body">
            <span class="finance-title">{{ record.title || record.note || '-' }}</span>
            <span class="finance-amount" :class="record.type === '收入' ? 'income' : 'expense'">
              {{ record.type === '收入' ? '+' : '-' }}{{ formatCurrency(record.amount) }}
            </span>
          </div>
          <div class="finance-item-meta">
            <span v-if="getProjectName(record.projectId)">项目: {{ getProjectName(record.projectId) }}</span>
            <span v-if="getOrgName(record.orgId)">机构: {{ getOrgName(record.orgId) }}</span>
          </div>
        </div>
        <div class="finance-item-actions">
          <button class="btn-icon-text" @click="handleEdit(record.id)">编辑</button>
          <button class="btn-icon-text danger" @click="handleDelete(record.id)">删除</button>
        </div>
      </div>
    </div>

    <div class="pagination" v-if="totalPages > 1">
      <div class="pagination-info">
        <span>共 <span id="financeTotalCount">{{ filteredRecords.length }}</span> 条记录</span>
        <span>每页:</span>
        <CustomSelect v-model="pageSize" @change="changePageSize">
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </CustomSelect>
      </div>
      <div class="pagination-controls">
        <button class="btn-secondary btn-sm" :disabled="currentPage === 1" @click="prevPage">◀ 上一页</button>
        <div class="pagination-pages">
          <button
            v-for="page in visiblePages"
            :key="page"
            class="btn-page"
            :class="{ active: page === currentPage }"
            @click="goToPage(page)"
          >
            {{ page }}
          </button>
        </div>
        <button class="btn-secondary btn-sm" :disabled="currentPage === totalPages" @click="nextPage">下一页 ▶</button>
      </div>
    </div>

    <Modal
      :show="showDeleteModal"
      title="确认删除"
      size="small"
      @close="showDeleteModal = false"
    >
      <p>确定要删除这条财务记录吗？此操作不可撤销。</p>
      <template #footer>
        <button class="btn-secondary" @click="showDeleteModal = false">取消</button>
        <button class="btn-danger" @click="confirmDelete">确认删除</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import Modal from '../components/Modal.vue'
import { useFinanceStore } from '../stores/finance'
import { useProjectStore } from '../stores/project'
import { useOrganizationStore } from '../stores/organization'
import { useToast } from '../composables/useToast'
import { Chart, registerables } from 'chart.js'
import CustomSelect from '../components/CustomSelect.vue'
Chart.register(...registerables)
const { warning } = useToast()

const router = useRouter()
const financeStore = useFinanceStore()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()

const trendChartEl = ref(null)
const categoryChartEl = ref(null)
let trendChart = null
let categoryChart = null

const filterSearch = ref('')
const filterYear = ref('all')
const filterType = ref('all')
const filterOrg = ref('all')
const filterProject = ref('all')
const filterMonth = ref('all')

const currentPage = ref(1)
const pageSize = ref(10)
const showDeleteModal = ref(false)
const deleteId = ref(null)
const pieChartMode = ref('income')

onMounted(async () => {
  await financeStore.loadRecords()
  await projectStore.loadProjects()
  await orgStore.loadOrganizations()
  await nextTick()
  initCharts()
})

const projects = computed(() => projectStore.projects)
const organizations = computed(() => orgStore.organizations)

const yearOptions = computed(() => {
  const years = new Set()
  financeStore.financeRecords.forEach(r => {
    if (r.date) {
      years.add(r.date.substring(0, 4))
    }
  })
  return Array.from(years).sort().reverse()
})

const stats = computed(() => {
  const records = financeStore.financeRecords
  const income = records.filter(r => r.type === '收入').reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0)
  const expense = records.filter(r => r.type === '支出').reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0)

  const now = new Date()
  const currentMonth = now.getMonth() + 1
  const currentYear = now.getFullYear()
  const monthlyRecords = records.filter(r => {
    if (!r.date) return false
    const [year, month] = r.date.substring(0, 7).split('-')
    return parseInt(year) === currentYear && parseInt(month) === currentMonth
  })
  const monthlyIncome = monthlyRecords.filter(r => r.type === '收入').reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0)
  const monthlyExpense = monthlyRecords.filter(r => r.type === '支出').reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0)

  return {
    totalIncome: income,
    totalExpense: expense,
    netBalance: income - expense,
    monthlyProfit: monthlyIncome - monthlyExpense
  }
})

const categoryStats = computed(() => {
  const cats = {}
  filteredRecords.value.forEach(r => {
    const cat = r.category || '其他'
    if (!cats[cat]) cats[cat] = 0
    cats[cat] += parseFloat(r.amount) || 0
  })
  return cats
})

const filteredRecords = computed(() => {
  let records = [...financeStore.financeRecords]

  if (filterSearch.value) {
    const kw = filterSearch.value.toLowerCase()
    records = records.filter(r =>
      (r.title || '').toLowerCase().includes(kw) ||
      (r.note || '').toLowerCase().includes(kw)
    )
  }
  if (filterYear.value !== 'all') {
    records = records.filter(r => r.date && r.date.startsWith(filterYear.value))
  }
  if (filterType.value !== 'all') {
    records = records.filter(r => r.type === filterType.value)
  }
  if (filterOrg.value !== 'all') {
    records = records.filter(r => r.orgId === filterOrg.value)
  }
  if (filterProject.value !== 'all') {
    records = records.filter(r => r.projectId === filterProject.value)
  }
  if (filterMonth.value !== 'all') {
    records = records.filter(r => r.date && r.date.substring(5, 7) === filterMonth.value)
  }

  return records.sort((a, b) => new Date(b.date) - new Date(a.date))
})

const hasActiveFilters = computed(() => {
  return filterSearch.value || filterYear.value !== 'all' || filterType.value !== 'all' ||
    filterOrg.value !== 'all' || filterProject.value !== 'all' || filterMonth.value !== 'all'
})

const filterSummaryText = computed(() => {
  const parts = []
  if (filterType.value !== 'all') parts.push(`类型: ${filterType.value}`)
  if (filterYear.value !== 'all') parts.push(`年份: ${filterYear.value}`)
  if (filterOrg.value !== 'all') parts.push(`机构: ${getOrgName(filterOrg.value)}`)
  if (filterProject.value !== 'all') parts.push(`项目: ${getProjectName(filterProject.value)}`)
  if (filterMonth.value !== 'all') parts.push(`月份: ${filterMonth.value}月`)
  return parts.join(' | ')
})

const filteredSummaryStats = computed(() => {
  const income = filteredRecords.value.filter(r => r.type === '收入').reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0)
  const expense = filteredRecords.value.filter(r => r.type === '支出').reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0)
  return `收入: ${formatCurrency(income)} | 支出: ${formatCurrency(expense)} | 净额: ${formatCurrency(income - expense)}`
})

const totalPages = computed(() => Math.ceil(filteredRecords.value.length / pageSize.value))

const paginatedRecords = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredRecords.value.slice(start, start + pageSize.value)
})

const visiblePages = computed(() => {
  const pages = []
  const total = totalPages.value
  const current = currentPage.value
  let start = Math.max(1, current - 2)
  let end = Math.min(total, current + 2)

  if (end - start < 4) {
    if (start === 1) {
      end = Math.min(total, start + 4)
    } else {
      start = Math.max(1, end - 4)
    }
  }

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  return pages
})

const formatCurrency = (amount) => {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2
  }).format(amount || 0)
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

const getProjectName = (projectId) => {
  if (!projectId) return ''
  const project = projects.value.find(p => p.id === projectId)
  return project?.name || ''
}

const getOrgName = (orgId) => {
  if (!orgId) return ''
  const org = organizations.value.find(o => o.id === orgId)
  return org?.name || ''
}

const handleAdd = () => {
  router.push('/finance/new')
}

const handleEdit = (id) => {
  router.push(`/finance/${id}/edit`)
}

const handleDelete = (id) => {
  deleteId.value = id
  showDeleteModal.value = true
}

const confirmDelete = async () => {
  if (deleteId.value) {
    await financeStore.deleteRecord(deleteId.value)
    showDeleteModal.value = false
    deleteId.value = null
  }
}

const resetFilters = () => {
  filterSearch.value = ''
  filterYear.value = 'all'
  filterType.value = 'all'
  filterOrg.value = 'all'
  filterProject.value = 'all'
  filterMonth.value = 'all'
  currentPage.value = 1
}

const clearFilters = () => {
  resetFilters()
}

const changePageSize = () => {
  currentPage.value = 1
}

const prevPage = () => {
  if (currentPage.value > 1) currentPage.value--
}

const nextPage = () => {
  if (currentPage.value < totalPages.value) currentPage.value++
}

const goToPage = (page) => {
  currentPage.value = page
}

const exportReport = () => {
  const records = filteredRecords.value
  if (records.length === 0) {
    warning('暂无数据可导出')
    return
  }

  const headers = ['日期', '类型', '分类', '金额', '摘要', '关联机构', '关联项目', '备注']
  const rows = records.map(f => {
    const org = f.orgId ? getOrgName(f.orgId) : ''
    const project = f.projectId ? getProjectName(f.projectId) : ''
    return [f.date, f.type, f.category, f.amount, f.title || '', org, project, f.note || '']
  })

  const csvContent = [headers, ...rows].map(row => row.join(',')).join('\n')
  const BOM = '\uFEFF'
  const blob = new Blob([BOM + csvContent], { type: 'application/vnd.ms-excel;charset=utf-8' })

  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `财务报表_${new Date().toISOString().split('T')[0]}.xls`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(link.href)
}

const switchPieChart = (mode) => {
  pieChartMode.value = mode
  updatePieChart()
}

const initCharts = () => {
  if (typeof Chart === 'undefined') {
    console.warn('Chart.js not loaded')
    return
  }

  nextTick(() => {
    initTrendChart()
    initPieChart()
  })
}

const initTrendChart = () => {
  const canvas = document.getElementById('financeTrendChart')
  if (!canvas) return

  if (trendChart) {
    trendChart.destroy()
    trendChart = null
  }

  const monthlyData = getMonthlyData()

  trendChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: monthlyData.labels,
      datasets: [
        {
          label: '收入',
          data: monthlyData.income,
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          fill: true,
          tension: 0.4
        },
        {
          label: '支出',
          data: monthlyData.expense,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          fill: true,
          tension: 0.4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top' }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: value => `¥${value.toLocaleString()}`
          }
        }
      }
    }
  })
}

const initPieChart = () => {
  const canvas = document.getElementById('financeCategoryChart')
  if (!canvas) return

  if (categoryChart) {
    categoryChart.destroy()
    categoryChart = null
  }

  updatePieChart()
}

const updatePieChart = () => {
  const canvas = document.getElementById('financeCategoryChart')
  if (!canvas) return

  const categoryData = getCategoryData(pieChartMode.value)

  if (categoryChart) {
    categoryChart.destroy()
  }

  categoryChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: categoryData.labels,
      datasets: [{
        data: categoryData.values,
        backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right' }
      }
    }
  })
}

const getMonthlyData = () => {
  const monthly = {}
  filteredRecords.value.forEach(r => {
    if (!r.date) return
    const month = r.date.substring(0, 7)
    if (!monthly[month]) {
      monthly[month] = { income: 0, expense: 0 }
    }
    const amount = parseFloat(r.amount) || 0
    if (r.type === '收入') {
      monthly[month].income += amount
    } else {
      monthly[month].expense += amount
    }
  })

  const sortedMonths = Object.keys(monthly).sort()
  return {
    labels: sortedMonths,
    income: sortedMonths.map(m => monthly[m].income),
    expense: sortedMonths.map(m => monthly[m].expense)
  }
}

const getCategoryData = (type) => {
  const category = {}
  filteredRecords.value
    .filter(r => r.type === (type === 'income' ? '收入' : '支出'))
    .forEach(r => {
      const cat = r.category || '其他'
      if (!category[cat]) {
        category[cat] = 0
      }
      category[cat] += parseFloat(r.amount) || 0
    })

  return {
    labels: Object.keys(category),
    values: Object.values(category)
  }
}

watch(filteredRecords, () => {
  currentPage.value = 1
  nextTick(() => {
    initTrendChart()
    updatePieChart()
  })
})
</script>

<style scoped>
.finance-page {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  gap: 12px;
}

.finance-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-card .stat-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 600;
}

.stat-card.income .stat-icon {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.stat-card.expense .stat-icon {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.stat-card.profit .stat-icon {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.stat-card.monthly .stat-icon {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.stat-card .stat-content {
  flex: 1;
}

.stat-card .stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-card .stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.finance-charts {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}

.chart-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 16px;
}

.chart-card canvas {
  max-height: 200px;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.chart-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.chart-tab {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.chart-tab.active {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.category-stats-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.category-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.category-stat-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.category-stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.category-stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.filter-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
}

.search-input {
  flex: 1;
  min-width: 150px;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.filter-select {
  padding: 8px 32px 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  min-width: 120px;
}

.filter-summary {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  font-size: 13px;
}

.filter-summary-text {
  color: var(--text-primary);
}

.filter-summary-stats {
  color: var(--text-secondary);
  margin-left: auto;
}

.finance-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}

.finance-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.finance-item.income {
  border-left: 3px solid #ef4444;
}

.finance-item.expense {
  border-left: 3px solid #10b981;
}

.finance-item-main {
  flex: 1;
}

.finance-item-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
}

.finance-type-badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
}

.finance-type-badge.income {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.finance-type-badge.expense {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.finance-category {
  font-size: 13px;
  color: var(--text-secondary);
}

.finance-date {
  font-size: 12px;
  color: var(--text-tertiary);
}

.finance-item-body {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  min-width: 0;
}

.finance-title {
  font-size: 14px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.finance-amount {
  font-size: 16px;
  font-weight: 600;
}

.finance-amount.income {
  color: #ef4444;
}

.finance-amount.expense {
  color: #10b981;
}

.finance-item-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.finance-item-actions {
  display: flex;
  gap: 8px;
}

.btn-icon-text {
  padding: 4px 8px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.btn-icon-text:hover {
  color: var(--text-primary);
}

.btn-icon-text.danger:hover {
  color: #ef4444;
}

.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
}

.pagination-info {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: var(--text-secondary);
}

.pagination-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pagination-pages {
  display: flex;
  gap: 4px;
}

.btn-page {
  min-width: 32px;
  height: 32px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.btn-page.active {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--accent);
  color: white;
}

.btn-primary:hover {
  background: var(--accent-hover);
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

.btn-danger {
  background: #ef4444;
  color: white;
}

.btn-danger:hover {
  background: #dc2626;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}

.btn-text {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
}

.btn-text:hover {
  color: var(--text-primary);
}

@media (max-width: 1024px) {
  .finance-stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .finance-charts {
    grid-template-columns: 1fr;
  }
}

[data-theme="dark"] .stat-card.income .stat-icon { background: var(--danger-light); color: var(--danger); }
[data-theme="dark"] .stat-card.expense .stat-icon { background: var(--success-light); color: var(--success); }
[data-theme="dark"] .stat-card.profit .stat-icon { background: var(--accent-light); color: var(--accent); }
[data-theme="dark"] .stat-card.monthly .stat-icon { background: var(--warning-light); color: var(--warning); }
[data-theme="dark"] .finance-item.income { border-left-color: var(--danger); }
[data-theme="dark"] .finance-item.expense { border-left-color: var(--success); }
[data-theme="dark"] .finance-type-badge.income { background: var(--danger-light); color: var(--danger); }
[data-theme="dark"] .finance-type-badge.expense { background: var(--success-light); color: var(--success); }
[data-theme="dark"] .finance-amount.income { color: var(--danger); }
[data-theme="dark"] .finance-amount.expense { color: var(--success); }
[data-theme="dark"] .btn-icon-text.danger:hover { color: var(--danger); }
[data-theme="dark"] .btn-danger { background: var(--danger); }
[data-theme="dark"] .btn-danger:hover { background: #b91c1c; }
</style>
