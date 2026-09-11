<template>
  <div id="dashboard" class="dashboard-page">
    <div class="page-header">
      <div class="page-header-left">
        <h2>概览</h2>
        <p class="page-desc">项目与数据一览</p>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">◈</div>
        <div class="stat-info">
          <div class="stat-value">{{ projectStats.total }}</div>
          <div class="stat-label">项目总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">◇</div>
        <div class="stat-info">
          <div class="stat-value">{{ orgStats.total }}</div>
          <div class="stat-label">合作机构</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">◉</div>
        <div class="stat-info">
          <div class="stat-value">{{ playerStats.total }}</div>
          <div class="stat-label">人才资源</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">☑</div>
        <div class="stat-info">
          <div class="stat-value">{{ projectStats.preparing }}</div>
          <div class="stat-label">筹备中</div>
        </div>
      </div>
    </div>

    <div class="quick-actions">
      <h3>快捷操作</h3>
      <div class="action-buttons">
        <button class="action-btn primary" @click="$router.push('/projects/new')">
          新建项目
        </button>
        <button class="action-btn" @click="$router.push('/organizations/new')">
          添加机构
        </button>
        <button class="action-btn" @click="$router.push('/players/new')">
          添加选手
        </button>
        <button class="action-btn" @click="$router.push('/settings')">
          资料配置
        </button>
      </div>
    </div>

    <div class="recent-section">
      <h3>最近项目</h3>
      <div class="recent-list">
        <div v-if="recentProjects.length === 0" class="empty-state">
          暂无项目
        </div>
        <div
          v-for="project in recentProjects"
          :key="project.id"
          class="recent-item"
          @click="$router.push(`/projects/${project.id}`)"
        >
          <div class="recent-item-info">
            <span class="recent-item-name">{{ project.name }}</span>
            <span class="recent-item-meta">{{ project.type }} · {{ project.status }}</span>
          </div>
          <div class="recent-item-arrow">›</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onActivated } from 'vue'
import { useProjectStore, useOrganizationStore, usePlayerStore } from '../stores'

const projectStore = useProjectStore()
const orgStore = useOrganizationStore()
const playerStore = usePlayerStore()

const loadDashboardData = async () => {
  await Promise.all([
    projectStore.loadProjects(),
    orgStore.loadOrganizations(),
    playerStore.loadPlayers()
  ])
}

onMounted(loadDashboardData)
onActivated(loadDashboardData)

const projectStats = computed(() => projectStore.getProjectStats())
const orgStats = computed(() => orgStore.getOrgStats())
const playerStats = computed(() => playerStore.getPlayerStats())

const recentProjects = computed(() => {
  return projectStore.projects
    .slice()
    .sort((a, b) => {
      const dateA = new Date(a.updatedAt || a.createdAt || 0)
      const dateB = new Date(b.updatedAt || b.createdAt || 0)
      return dateB - dateA
    })
    .slice(0, 5)
})
</script>

<style scoped>
.dashboard-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 32px;
}

@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 600px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}

.stat-card {
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  font-size: 24px;
  color: var(--accent);
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary, #333);
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: var(--text-secondary, #666);
  margin-top: 4px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color, #eee);
}

.quick-actions {
  margin-bottom: 32px;
}

.quick-actions h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #333);
  margin: 0 0 16px;
}

.action-buttons {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.action-btn {
  padding: 10px 20px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  background: var(--bg-primary, #fff);
  color: var(--text-primary, #333);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.action-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.action-btn.primary:hover {
  background: #40a9ff;
  border-color: #40a9ff;
  color: #fff;
}

.recent-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #333);
  margin: 0 0 16px;
}

.recent-list {
  background: var(--bg-primary);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.recent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: background 0.2s;
}

.recent-item:last-child {
  border-bottom: none;
}

.recent-item:hover {
  background: var(--bg-hover, #f5f5f5);
}

.recent-item-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.recent-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #333);
}

.recent-item-meta {
  font-size: 12px;
  color: var(--text-secondary, #999);
}

.recent-item-arrow {
  font-size: 20px;
  color: var(--text-secondary, #ccc);
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--text-secondary, #999);
  font-size: 14px;
}

[data-theme="dark"] .action-btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
</style>
