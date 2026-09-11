<template>
  <div class="notification-panel" v-if="visible" @click.stop>
    <div class="notification-header">
      <h3>通知中心</h3>
      <div class="notification-actions">
        <button
          v-if="unreadCount > 0"
          class="btn-link"
          @click="handleMarkAllRead"
        >
          全部已读
        </button>
        <button class="notification-close" @click="close">✕</button>
      </div>
    </div>

    <div class="notification-filters">
      <button
        v-for="filter in filters"
        :key="filter.value"
        :class="['filter-btn', { active: currentFilter === filter.value }]"
        @click="currentFilter = filter.value; loadNotifications()"
      >
        {{ filter.label }}
      </button>
    </div>

    <div class="notification-list" ref="listRef">
      <div v-if="loading" class="notification-loading">
        加载中...
      </div>

      <div v-else-if="notifications.length === 0" class="notification-empty">
        <div class="empty-icon">📭</div>
        <p>{{ emptyText }}</p>
      </div>

      <div
        v-else
        v-for="item in notifications"
        :key="item.id"
        :class="['notification-item', { unread: !item.isRead }]"
        @click="handleClick(item)"
      >
        <div :class="['notification-icon', getTypeConfig(item.type).class]">
          {{ getTypeConfig(item.type).icon }}
        </div>
        <div class="notification-content">
          <div class="notification-title">{{ item.title }}</div>
          <div class="notification-desc">{{ item.content }}</div>
          <div class="notification-meta">
            <span class="notification-time">{{ formatTime(item.createdAt) }}</span>
            <span v-if="!item.isRead" class="unread-dot"></span>
          </div>
        </div>
        <button
          class="notification-delete"
          @click.stop="handleDelete(item.id)"
          title="删除"
        >
          🗑️
        </button>
      </div>
    </div>

    <div v-if="total > pageSize" class="notification-footer">
      <button
        class="btn-secondary btn-sm"
        @click="loadMore"
        :disabled="loading"
      >
        {{ loading ? '加载中...' : '加载更多' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { notificationService } from '../services/notificationService'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'navigate', 'update:unreadCount'])

const notifications = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = 10
const total = ref(0)
const unreadCount = ref(0)
const currentFilter = ref('all')
const listRef = ref(null)

let pollTimer = null

const filters = [
  { label: '全部', value: 'all' },
  { label: '未读', value: 'unread' },
  { label: '信息', value: 'info' },
  { label: '警告', value: 'warning' }
]

const emptyText = computed(() => {
  if (currentFilter.value === 'unread') return '暂无未读通知'
  if (currentFilter.value === 'info') return '暂无信息类通知'
  if (currentFilter.value === 'warning') return '暂无警告类通知'
  return '暂无通知'
})

const loadNotifications = async () => {
  loading.value = true

  try {
    const params = {
      page: 1,
      pageSize,
      type: currentFilter.value === 'unread' ? 'all' : currentFilter.value,
      isRead: currentFilter.value === 'unread' ? 'false' : 'all'
    }

    const result = await notificationService.getList(params)

    notifications.value = result.data || []
    total.value = result.total || 0
    unreadCount.value = result.unreadCount || 0

    emit('update:unreadCount', unreadCount.value)
  } catch (e) {
    console.error('加载通知失败:', e)
  } finally {
    loading.value = false
  }
}

const loadMore = async () => {
  if (notifications.value.length >= total.value) return

  loading.value = true
  currentPage.value++

  try {
    const params = {
      page: currentPage.value,
      pageSize,
      type: currentFilter.value,
      isRead: 'all'
    }

    const result = await notificationService.getList(params)
    notifications.value.push(...(result.data || []))
    total.value = result.total || 0
  } catch (e) {
    console.error('加载更多通知失败:', e)
  } finally {
    loading.value = false
  }
}

const handleMarkAllRead = async () => {
  try {
    await notificationService.markAllRead()
    await loadNotifications()
  } catch (e) {
    console.error('标记已读失败:', e)
  }
}

const handleDelete = async (id) => {
  try {
    await notificationService.delete(id)
    await loadNotifications()
  } catch (e) {
    console.error('删除通知失败:', e)
  }
}

const handleClick = async (item) => {
  if (!item.isRead) {
    try {
      await notificationService.markAsRead(item.id)
      item.isRead = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      emit('update:unreadCount', unreadCount.value)
    } catch (e) {
      console.error('标记已读失败:', e)
    }
  }

  if (item.link) {
    emit('navigate', item.link)
    close()
  }
}

const close = () => {
  emit('close')
}

const formatTime = (isoString) => {
  return notificationService.formatTime(isoString)
}

const getTypeConfig = (type) => {
  return notificationService.getTypeConfig(type)
}

const startPolling = () => {
  pollTimer = setInterval(async () => {
    try {
      const count = await notificationService.getUnreadCount()
      if (count !== unreadCount.value) {
        unreadCount.value = count
        emit('update:unreadCount', count)

        if (props.visible) {
          await loadNotifications()
        }
      }
    } catch (e) {
      // 静默失败
    }
  }, 30000) // 每30秒轮询一次
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadNotifications()
  }
})

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

defineExpose({
  refresh: loadNotifications,
  getUnreadCount: () => unreadCount.value
})
</script>

<style scoped>
.notification-panel {
  position: absolute;
  top: 100%;
  right: 0;
  width: 380px;
  max-height: 500px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.notification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}

.notification-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.notification-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.btn-link {
  background: none;
  border: none;
  color: var(--primary-color);
  cursor: pointer;
  font-size: 13px;
  padding: 4px 8px;
}

.btn-link:hover {
  text-decoration: underline;
}

.notification-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  color: var(--text-secondary);
}

.notification-close:hover {
  color: var(--text-primary);
}

.notification-filters {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  overflow-x: auto;
}

.filter-btn {
  padding: 6px 14px;
  border: 1px solid var(--border-color);
  background: transparent;
  border-radius: 16px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.filter-btn.active {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.notification-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.notification-loading,
.notification-empty {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.notification-item {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  transition: background 0.2s;
  position: relative;
}

.notification-item:hover {
  background: var(--bg-secondary);
}

.notification-item.unread {
  background: rgba(59, 130, 246, 0.05);
}

.notification-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.notification-info {
  background: #eff6ff;
}

.notification-warning {
  background: #fffbeb;
}

.notification-success {
  background: #f0fdf4;
}

.notification-error {
  background: #fef2f2;
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notification-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.notification-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.notification-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.unread-dot {
  width: 8px;
  height: 8px;
  background: var(--primary-color);
  border-radius: 50%;
}

.notification-delete {
  background: none;
  border: none;
  opacity: 0;
  cursor: pointer;
  padding: 4px;
  font-size: 14px;
  transition: opacity 0.2s;
}

.notification-item:hover .notification-delete {
  opacity: 1;
}

.notification-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
  text-align: center;
}
</style>
