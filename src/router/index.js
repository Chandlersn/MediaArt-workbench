import { createRouter, createWebHashHistory } from 'vue-router'
import { isAuthenticated } from '../services/auth'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: '首页', guest: true }
  },
  {
    path: '/guide',
    name: 'Guide',
    component: () => import('../views/GuideView.vue'),
    meta: { title: '使用指南', guest: true }
  },
  {
    path: '/projects',
    name: 'Projects',
    component: () => import('../views/ProjectsView.vue'),
    meta: { title: '项目管理', requiresAuth: true }
  },
  {
    path: '/projects/new',
    name: 'ProjectNew',
    component: () => import('../views/ProjectFormView.vue'),
    meta: { title: '新建项目', requiresAuth: true }
  },
  {
    path: '/projects/:id',
    name: 'ProjectDetail',
    component: () => import('../views/ProjectDetailView.vue'),
    meta: { title: '项目详情', requiresAuth: true }
  },
  {
    path: '/projects/:id/edit',
    name: 'ProjectEdit',
    component: () => import('../views/ProjectFormView.vue'),
    meta: { title: '编辑项目', requiresAuth: true }
  },
  {
    path: '/organizations',
    name: 'Organizations',
    component: () => import('../views/OrganizationsView.vue'),
    meta: { title: '机构管理', requiresAuth: true }
  },
  {
    path: '/organizations/new',
    name: 'OrganizationNew',
    component: () => import('../views/OrganizationFormView.vue'),
    meta: { title: '新建机构', requiresAuth: true }
  },
  {
    path: '/organizations/:id',
    name: 'OrganizationDetail',
    component: () => import('../views/OrganizationDetailView.vue'),
    meta: { title: '机构详情', requiresAuth: true }
  },
  {
    path: '/organizations/:id/edit',
    name: 'OrganizationEdit',
    component: () => import('../views/OrganizationFormView.vue'),
    meta: { title: '编辑机构', requiresAuth: true }
  },
  {
    path: '/players',
    name: 'Players',
    component: () => import('../views/PlayersView.vue'),
    meta: { title: '选手管理', requiresAuth: true }
  },
  {
    path: '/players/new',
    name: 'PlayerNew',
    component: () => import('../views/PlayerFormView.vue'),
    meta: { title: '添加选手', requiresAuth: true }
  },
  {
    path: '/players/:id',
    name: 'PlayerDetail',
    component: () => import('../views/PlayerDetailView.vue'),
    meta: { title: '选手详情', requiresAuth: true }
  },
  {
    path: '/players/:id/edit',
    name: 'PlayerEdit',
    component: () => import('../views/PlayerFormView.vue'),
    meta: { title: '编辑选手', requiresAuth: true }
  },
  {
    path: '/finance',
    name: 'Finance',
    component: () => import('../views/FinanceView.vue'),
    meta: { title: '财务管理', requiresAuth: true }
  },
  {
    path: '/certificates',
    name: 'Certificates',
    component: () => import('../views/CertificatesView.vue'),
    meta: { title: '证书管理', requiresAuth: true }
  },
  {
    path: '/finance/new',
    name: 'FinanceNew',
    component: () => import('../views/FinanceFormView.vue'),
    meta: { title: '添加记录', requiresAuth: true }
  },
  {
    path: '/finance/:id/edit',
    name: 'FinanceEdit',
    component: () => import('../views/FinanceFormView.vue'),
    meta: { title: '编辑记录', requiresAuth: true }
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('../views/KnowledgeView.vue'),
    meta: { title: '知识库', requiresAuth: true }
  },
  {
    path: '/knowledge/new',
    name: 'KnowledgeNew',
    component: () => import('../views/KnowledgeFormView.vue'),
    meta: { title: '新建知识', requiresAuth: true }
  },
  {
    path: '/knowledge/:id',
    name: 'KnowledgeDetail',
    component: () => import('../views/KnowledgeDetailView.vue'),
    meta: { title: '知识详情', requiresAuth: true }
  },
  {
    path: '/knowledge/:id/edit',
    name: 'KnowledgeEdit',
    component: () => import('../views/KnowledgeFormView.vue'),
    meta: { title: '编辑知识', requiresAuth: true }
  },
  {
    path: '/resources',
    name: 'Resources',
    component: () => import('../views/ResourcesView.vue'),
    meta: { title: '素材库', requiresAuth: true }
  },
  {
    path: '/templates',
    name: 'Templates',
    component: () => import('../views/TemplatesView.vue'),
    meta: { title: '模板管理', requiresAuth: true }
  },
  {
    path: '/archive',
    name: 'Archive',
    component: () => import('../views/ArchiveView.vue'),
    meta: { title: '归档管理', requiresAuth: true }
  },
  {
    path: '/material-config',
    name: 'MaterialConfig',
    component: () => import('../views/MaterialConfigView.vue'),
    meta: { title: '资料配置', requiresAuth: true }
  },
  {
    path: '/checklists',
    name: 'Checklists',
    component: () => import('../views/ChecklistsView.vue'),
    meta: { title: '检查清单', requiresAuth: true }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { title: '系统设置', requiresAuth: true }
  },
  {
    path: '/users',
    name: 'Users',
    component: () => import('../views/UsersView.vue'),
    meta: { title: '用户管理', requiresAuth: true }
  },
  {
    path: '/audit-logs',
    name: 'AuditLogs',
    component: () => import('../views/AuditLogsView.vue'),
    meta: { title: '操作日志', requiresAuth: true }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

let globalShowLogin = null

export const setLoginCallback = (callback) => {
  globalShowLogin = callback
}

router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title || '媒体艺术智能工作台'}`

  if (to.meta.requiresAuth && !isAuthenticated()) {
    if (globalShowLogin) {
      globalShowLogin()
    }
    next('/')
  } else {
    next()
  }
})

export default router
