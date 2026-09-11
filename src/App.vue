<template>
  <div class="app-container">
    <header class="app-header">
      <div class="logo">
        <div class="logo-icon">M</div>
        <h1>媒体艺术智能工作台</h1>
      </div>
      <div class="header-actions">
        <span class="current-date">{{ currentDateStr }}</span>
        <button class="theme-toggle" @click="toggleTheme" title="切换主题">
          <span class="theme-icon-light">☀️</span>
          <span class="theme-icon-dark">🌙</span>
        </button>
        <div class="notification-bell" @click="toggleNotifications">
          🔔
          <span class="notification-badge" v-if="notificationCount > 0">{{ notificationCount }}</span>
        </div>
        <div class="user-info">
          <span id="currentUsername">{{ currentUsername }}</span>
          <button
            v-if="!loggedIn"
            class="btn-secondary btn-sm"
            @click="showLogin = true"
          >登录</button>
          <button
            v-else
            class="btn-secondary btn-sm"
            @click="handleLogout"
          >退出</button>
        </div>
      </div>
    </header>

    <nav class="sidebar">
      <div class="nav-section">
        <div class="nav-title">核心功能</div>
        <ul class="nav-menu">
          <li
            class="nav-item"
            :class="{ active: $route.path === '/' }"
            @click="navigateTo('/')"
          >
            <span>概览</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/projects') }"
            @click="navigateTo('/projects')"
          >
            <span>项目</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/organizations') }"
            @click="navigateTo('/organizations')"
          >
            <span>机构</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/players') }"
            @click="navigateTo('/players')"
          >
            <span>选手</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/finance') }"
            @click="navigateTo('/finance')"
          >
            <span>运营</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/certificates') }"
            @click="navigateTo('/certificates')"
          >
            <span>证书管理</span>
          </li>
        </ul>
      </div>
      <div class="nav-section">
        <div class="nav-title">资源中心</div>
        <ul class="nav-menu">
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/knowledge') }"
            @click="navigateTo('/knowledge')"
          >
            <span>知识库</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/resources') }"
            @click="navigateTo('/resources')"
          >
            <span>资源中心</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/templates') }"
            @click="navigateTo('/templates')"
          >
            <span>模板管理</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/archive') }"
            @click="navigateTo('/archive')"
          >
            <span>归档管理</span>
          </li>
        </ul>
      </div>
      <div class="nav-section">
        <div class="nav-title">工具</div>
        <ul class="nav-menu">
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/checklists') }"
            @click="navigateTo('/checklists')"
          >
            <span>检查清单</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/material-config') }"
            @click="navigateTo('/material-config')"
          >
            <span>资料配置</span>
          </li>
        </ul>
      </div>
      <div class="nav-section">
        <div class="nav-title">系统</div>
        <ul class="nav-menu">
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/users') }"
            @click="navigateTo('/users')"
          >
            <span>用户管理</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/audit-logs') }"
            @click="navigateTo('/audit-logs')"
          >
            <span>操作日志</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/settings') }"
            @click="navigateTo('/settings')"
          >
            <span>设置</span>
          </li>
          <li
            class="nav-item"
            :class="{ active: $route.path.startsWith('/guide') }"
            @click="navigateTo('/guide')"
          >
            <span>使用说明</span>
          </li>
        </ul>
      </div>
    </nav>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <LoginModal v-model="showLogin" @login-success="handleLoginSuccess" />
    <Toast />
    <ConfirmDialog />
    <Message />
    <NotificationPanel
      :visible="showNotifications"
      @close="showNotifications = false"
      @navigate="handleNotificationNavigate"
      @update:unreadCount="updateUnreadCount"
      ref="notificationPanelRef"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import LoginModal from './components/LoginModal.vue'
import Toast from './components/Toast.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import Message from './components/Message.vue'
import NotificationPanel from './components/NotificationPanel.vue'
import { useToast } from './composables/useToast'

import { getCurrentUser, isAuthenticated, logout } from './services/auth'
import { setLoginCallback } from './router'

const router = useRouter()
const { success, info } = useToast()

const showLogin = ref(false)
const currentUsername = ref('未登录')
// 是否已登录：登录后按钮变「退出」
const loggedIn = ref(false)
const notificationCount = ref(0)
const showNotifications = ref(false)
const notificationPanelRef = ref(null)

setLoginCallback(() => {
  showLogin.value = true
})

const navigateTo = (path) => {
  router.push(path)
}

const toggleTheme = () => {
  const current = document.documentElement.getAttribute('data-theme')
  const newTheme = current === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', newTheme)
  localStorage.setItem('theme', newTheme)
}

const toggleNotifications = () => {
  showNotifications.value = !showNotifications.value
  if (showNotifications.value) {
    loadUnreadCount(true)
  }
}

const closeNotifications = () => {
  showNotifications.value = false
}

// 点击页面其他地方关闭通知面板
const handleClickOutside = (event) => {
  const notificationBell = event.target.closest('.notification-bell')
  const panel = event.target.closest('.notification-panel')

  if (!notificationBell && !panel && showNotifications.value) {
    closeNotifications()
  }
}

const updateUnreadCount = (count) => {
  notificationCount.value = count
}

const handleNotificationNavigate = (path) => {
  if (path && router) {
    router.push(path)
  }
}

let _lastNotificationFetch = 0
const NOTIFICATION_DEBOUNCE_MS = 10000

const loadUnreadCount = async (force = false) => {
  const now = Date.now()
  if (!force && now - _lastNotificationFetch < NOTIFICATION_DEBOUNCE_MS) return

  try {
    const { notificationService } = await import('./services/notificationService.js')
    const count = await notificationService.getUnreadCount()
    notificationCount.value = count
    _lastNotificationFetch = now
  } catch (e) {
    console.error('加载未读通知数失败:', e)
  }
}

const handleLoginSuccess = (user) => {
  currentUsername.value = user?.username || '未知用户'
  loggedIn.value = true
  success('登录成功')
}

const currentDateStr = ref('')

const updateCurrentDate = () => {
  const now = new Date()
  currentDateStr.value = now.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long'
  })
}

/**
 * 同步顶部用户区状态（挂载时、登录后、退出后调用）
 */
const updateUserInfo = () => {
  loggedIn.value = isAuthenticated()
  if (loggedIn.value) {
    const user = getCurrentUser()
    currentUsername.value = user?.username || '已登录'
  } else {
    currentUsername.value = '未登录'
  }
}

/**
 * 退出登录：清除本地凭证并把顶部按钮切回「登录」
 */
const handleLogout = async () => {
  await logout()
  updateUserInfo()
  info('已退出登录')
  // 当前页面若需要登录态，退回首页，避免停留在无法刷新的页面
  if (router.currentRoute.value.meta?.requiresAuth) {
    router.push('/')
  }
}

// 定时器与可见性处理放在模块作用域。
// 此前 dateInterval / notificationInterval / startTimers / stopTimers /
// handleVisibilityChange 都定义在 onMounted 的回调内部，导致 onUnmounted 里引用
// stopTimers 与 handleVisibilityChange 时抛 ReferenceError —— 清理逻辑中断，
// click 与 visibilitychange 两个监听器被泄漏。
let dateInterval = null
let notificationInterval = null

function stopTimers() {
  if (dateInterval) clearInterval(dateInterval)
  if (notificationInterval) clearInterval(notificationInterval)
  dateInterval = null
  notificationInterval = null
}

function startTimers() {
  stopTimers()
  dateInterval = setInterval(updateCurrentDate, 60000)
  notificationInterval = setInterval(loadUnreadCount, 300000)
}

function handleVisibilityChange() {
  if (document.hidden) {
    stopTimers()
  } else {
    updateCurrentDate()
    loadUnreadCount()
    startTimers()
  }
}

onMounted(() => {
  updateCurrentDate()
  updateUserInfo()
  loadUnreadCount()

  startTimers()

  document.addEventListener('visibilitychange', handleVisibilityChange)

  // 监听认证过期事件，显示登录弹窗
  window.addEventListener('auth:required', () => {
    // 凭证已失效，顶部按钮同步切回「登录」
    updateUserInfo()
    showLogin.value = true
  })

  // 点击外部关闭通知面板
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  stopTimers()
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
