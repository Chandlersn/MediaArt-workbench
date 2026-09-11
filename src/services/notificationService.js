/**
 * 通知服务层：封装通知相关的API调用
 */

import { get, post, del } from './http.js'

const BASE_URL = '/api/notifications'

export const notificationService = {

  /**
   * 获取通知列表
   * @param {Object} params - 查询参数
   * @param {number} params.page - 页码（默认1）
   * @param {number} params.pageSize - 每页数量（默认20）
   * @param {string} params.type - 类型过滤（all|info|warning|success|error）
   * @param {string} params.isRead - 已读状态过滤（all|true|false）
   */
  async getList(params = {}) {
    const queryParams = new URLSearchParams({
      page: params.page || 1,
      pageSize: params.pageSize || 20,
      type: params.type || 'all',
      isRead: params.isRead || 'all'
    })

    const response = await get(`${BASE_URL}?${queryParams}`)
    return response
  },

  /**
   * 获取未读通知数量
   */
  async getUnreadCount() {
    const response = await get(`${BASE_URL}/unread-count`)
    return response.count || 0
  },

  /**
   * 标记单个通知为已读
   * @param {string} id - 通知ID
   */
  async markAsRead(id) {
    return await post(`${BASE_URL}/read`, { id })
  },

  /**
   * 标记所有通知为已读
   */
  async markAllRead() {
    return await post(`${BASE_URL}/read-all`)
  },

  /**
   * 删除通知
   * @param {string} id - 通知ID
   */
  async delete(id) {
    return await del(`${BASE_URL}/${id}`)
  },

  /**
   * 创建新通知（管理员功能）
   * @param {Object} data - 通知数据
   * @param {string} data.title - 标题
   * @param {string} data.content - 内容
   * @param {string} data.type - 类型（info|warning|success|error）
   * @param {string} data.link - 链接地址（可选）
   */
  async create(data) {
    return await post(`${BASE_URL}/create`, data)
  },

  /**
   * 格式化时间显示
   * @param {string} isoString - ISO格式时间字符串
   */
  formatTime(isoString) {
    if (!isoString) return ''

    const date = new Date(isoString)
    const now = new Date()
    const diff = now - date

    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`

    return date.toLocaleDateString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  },

  /**
   * 获取通知类型配置
   */
  getTypeConfig(type) {
    const configs = {
      info: {
        icon: 'ℹ️',
        label: '信息',
        class: 'notification-info'
      },
      warning: {
        icon: '⚠️',
        label: '警告',
        class: 'notification-warning'
      },
      success: {
        icon: '✅',
        label: '成功',
        class: 'notification-success'
      },
      error: {
        icon: '❌',
        label: '错误',
        class: 'notification-error'
      }
    }

    return configs[type] || configs.info
  }
}
