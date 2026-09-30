<!--
  资料提交链接弹窗。

  ⚠️ 已暂缓（2026-09-30）：本功能面向「多设备/多人协作」场景——生成的链接指向
  window.location.origin（即 localhost），外部人员无法访问，与当前「个人本地使用」
  的定位不符。代码保留备用，**入口已从选手/机构详情页移除**，目前无任何页面引用。
  若将来要做线上或多端，把入口加回详情页即可，后端 server/submit/ 与 /submit/:token 路由均完好。
-->
<template>
  <Modal
    :show="show"
    title="资料提交链接"
    size="medium"
    @close="close"
    @update:show="(v) => emit('update:show', v)"
  >
    <div class="slm">
      <p class="slm-desc">
        把链接发给 <strong>{{ entityName || '该对象' }}</strong>，对方<strong>无需登录</strong>即可上传资料。
        文件会直接归入归档目录，系统的缺料状态随之自动更新。
      </p>

      <div class="slm-actions">
        <button class="btn-primary btn-sm" :disabled="generating" @click="generate">
          {{ generating ? '生成中…' : '生成新链接' }}
        </button>
        <button class="btn-secondary btn-sm" :disabled="loading" @click="load">
          {{ loading ? '加载中…' : '刷新' }}
        </button>
      </div>

      <p v-if="notice" class="slm-notice" :class="noticeType">{{ notice }}</p>

      <p v-if="!links.length && !loading" class="slm-empty">还没有生成过链接。</p>

      <ul v-else class="slm-list">
        <li
          v-for="l in links"
          :key="l.token"
          class="slm-item"
          :class="{ inactive: l.revoked || l.expired }"
        >
          <div class="slm-row">
            <span class="slm-badge" :class="statusClass(l)">{{ statusText(l) }}</span>
            <span class="slm-meta">有效期至 {{ l.expiresAt || '不限' }}</span>
            <span class="slm-meta">已提交 {{ l.usedCount }} 次</span>
          </div>

          <div class="slm-url">
            <input
              class="slm-input"
              readonly
              :value="urlOf(l)"
              @focus="(e) => e.target.select()"
            />
            <button class="btn-secondary btn-sm" @click="copy(l)">复制</button>
            <button
              v-if="!l.revoked"
              class="btn-danger btn-sm"
              @click="revoke(l)"
            >
              撤销
            </button>
          </div>
        </li>
      </ul>
    </div>

    <template #footer>
      <button class="btn-secondary" @click="close">关闭</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { get, post, del } from '../services/http'
import { useToast } from '../composables/useToast'

const props = defineProps({
  show: { type: Boolean, default: false },
  entityType: { type: String, default: 'player' },
  entityId: { type: String, default: '' },
  entityName: { type: String, default: '' }
})

const emit = defineEmits(['update:show'])
const { success, error } = useToast()

const links = ref([])
const loading = ref(false)
const generating = ref(false)
const notice = ref('')
const noticeType = ref('ok')

const close = () => emit('update:show', false)

async function load() {
  if (!props.entityId) return
  loading.value = true
  notice.value = ''
  try {
    const res = await get(
      `/api/submit-links?entityType=${encodeURIComponent(props.entityType)}` +
        `&entityId=${encodeURIComponent(props.entityId)}`
    )
    links.value = res.links || []
  } catch (e) {
    error(`加载链接失败：${e.message}`)
    links.value = []
  } finally {
    loading.value = false
  }
}

async function generate() {
  if (!props.entityId) return
  generating.value = true
  notice.value = ''
  try {
    const res = await post('/api/submit-links', {
      entityType: props.entityType,
      entityId: props.entityId,
      expiresInDays: 7
    })
    if (res.success) {
      noticeType.value = 'ok'
      notice.value = '链接已生成，复制后发给对方即可'
      success('提交链接已生成')
      await load()
    } else {
      noticeType.value = 'err'
      notice.value = res.message || '生成失败'
      error(res.message || '生成失败')
    }
  } catch (e) {
    noticeType.value = 'err'
    notice.value = e.message
    error(`生成失败：${e.message}`)
  } finally {
    generating.value = false
  }
}

async function revoke(link) {
  try {
    const res = await del(`/api/submit-links/${encodeURIComponent(link.token)}`)
    if (res.success) {
      success('链接已撤销')
      await load()
    } else {
      error(res.message || '撤销失败')
    }
  } catch (e) {
    error(`撤销失败：${e.message}`)
  }
}

function urlOf(link) {
  return `${window.location.origin}/#/submit/${link.token}`
}

async function copy(link) {
  const text = urlOf(link)
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      // 非安全上下文（http 访问）没有 clipboard API，退回临时 textarea
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    success('链接已复制')
  } catch (e) {
    error('复制失败，请手动选中复制')
  }
}

function statusText(link) {
  if (link.revoked) return '已撤销'
  if (link.expired) return '已过期'
  return '生效中'
}

function statusClass(link) {
  if (link.revoked) return 'badge-revoked'
  if (link.expired) return 'badge-expired'
  return 'badge-active'
}

watch(
  () => props.show,
  (v) => {
    if (v) load()
  }
)
</script>

<style scoped>
.slm-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0 0 16px;
}
.slm-desc strong {
  color: var(--text-primary);
  font-weight: 500;
}

.slm-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.slm-notice {
  font-size: 13px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  margin: 0 0 14px;
}
.slm-notice.ok {
  color: var(--success);
  background: var(--success-light);
}
.slm-notice.err {
  color: var(--danger);
  background: var(--danger-light);
}

.slm-empty {
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
  padding: 20px 0;
  margin: 0;
}

.slm-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 340px;
  overflow-y: auto;
}
.slm-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px;
  margin-bottom: 10px;
}
.slm-item.inactive {
  opacity: 0.65;
}

.slm-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 9px;
}
.slm-badge {
  font-size: 12px;
  padding: 2px 9px;
  border-radius: 999px;
}
.badge-active {
  color: var(--success);
  background: var(--success-light);
}
.badge-expired {
  color: var(--warning);
  background: var(--warning-light);
}
.badge-revoked {
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
}
.slm-meta {
  font-size: 12px;
  color: var(--text-tertiary);
}

.slm-url {
  display: flex;
  gap: 6px;
}
.slm-input {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  padding: 6px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
}
</style>
