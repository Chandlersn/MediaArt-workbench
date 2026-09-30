<!--
  免登录资料提交页（/submit/:token）。

  ⚠️ 已暂缓（2026-09-30）：该页依赖「外部设备能访问本机服务」，与当前
  「个人本地使用」定位不符。代码与路由保留备用，管理端入口已移除，页面本身
  仍可通过 URL 直接访问（不影响本地使用）。
-->
<template>
  <div class="submit-page">
    <div class="submit-card">
      <!-- 链接不可用（无效 / 过期 / 已撤销） -->
      <div v-if="fatal" class="fatal">
        <div class="fatal-icon">⚠️</div>
        <h1 class="fatal-title">链接不可用</h1>
        <p class="fatal-msg">{{ fatal }}</p>
        <p class="fatal-hint">如需继续提交资料，请联系主办方重新获取链接。</p>
      </div>

      <p v-else-if="loading" class="loading-text">正在加载…</p>

      <template v-else>
        <header class="head">
          <div class="brand">媒体艺术智能工作台</div>
          <h1 class="title">资料提交</h1>
          <div class="who">
            <span class="who-name">{{ info.entityName }}</span>
            <span v-if="info.stage" class="who-stage">{{ info.stage }}</span>
          </div>
          <p v-if="info.expiresAt" class="expiry">链接有效期至 {{ info.expiresAt }}</p>
        </header>

        <p class="progress">
          已提交 <strong>{{ doneCount }}</strong> / {{ items.length }} 项
        </p>

        <ul class="items">
          <li
            v-for="item in items"
            :key="item.name"
            class="item"
            :class="{ done: item.done }"
          >
            <span class="item-icon">{{ item.icon }}</span>
            <div class="item-meta">
              <div class="item-name">{{ item.name }}</div>
              <div class="item-status">{{ item.done ? '已提交' : '待提交' }}</div>
            </div>
            <button
              class="item-btn"
              :disabled="uploading === item.name"
              @click="pick(item.name)"
            >
              {{ uploading === item.name ? '上传中…' : (item.done ? '重新上传' : '上传') }}
            </button>
          </li>
        </ul>

        <p v-if="notice" class="notice" :class="noticeType">{{ notice }}</p>

        <p class="tips">
          支持图片、文档、音视频与压缩包，单个文件不超过 {{ maxMb }}MB。<br />
          重复上传同一项会覆盖之前的文件。
        </p>

        <input
          ref="fileInput"
          type="file"
          class="hidden-input"
          @change="onFileChange"
        />
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

// 免登录公开页：token 来自链接，直接调 /api/public/submit/*
// ⚠️ 不走 services/http.js —— 那里会自动附带 Authorization 并在 401 时触发登录刷新流程，
//    而本页没有、也不应有登录态。
const route = useRoute()
const token = route.params.token

const maxMb = 50

const loading = ref(true)
const fatal = ref('')
const info = ref({ entityName: '', stage: '', expiresAt: '', items: [] })
const uploading = ref('')
const notice = ref('')
const noticeType = ref('ok')
const fileInput = ref(null)
let pendingType = ''

const items = computed(() => info.value.items || [])
const doneCount = computed(() => items.value.filter((i) => i.done).length)

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const res = await fetch(`/api/public/submit/${encodeURIComponent(token)}`)
    const data = await res.json().catch(() => ({}))
    if (!res.ok || !data.success) {
      fatal.value = data.message || `链接不可用（${res.status}）`
      return
    }
    info.value = data
  } catch (e) {
    fatal.value = '网络错误，请稍后重试'
  } finally {
    loading.value = false
  }
}

function pick(type) {
  pendingType = type
  notice.value = ''
  fileInput.value?.click()
}

async function onFileChange(e) {
  const file = e.target.files && e.target.files[0]
  if (!file) return

  uploading.value = pendingType
  notice.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('materialType', pendingType)

    const res = await fetch(`/api/public/submit/${encodeURIComponent(token)}`, {
      method: 'POST',
      body: fd
    })
    const data = await res.json().catch(() => ({}))

    if (res.ok && data.success) {
      noticeType.value = 'ok'
      notice.value = `「${pendingType}」提交成功`
      await load(true)
    } else {
      noticeType.value = 'err'
      notice.value = data.message || `提交失败（${res.status}）`
    }
  } catch (err) {
    noticeType.value = 'err'
    notice.value = '网络错误，提交失败'
  } finally {
    uploading.value = ''
    if (fileInput.value) fileInput.value.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.submit-page {
  min-height: 100vh;
  background: var(--bg-primary);
  padding: 24px 16px 48px;
  box-sizing: border-box;
}

.submit-card {
  max-width: 560px;
  margin: 0 auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 28px 24px;
  box-shadow: var(--shadow-md);
  box-sizing: border-box;
}

/* ---------- 不可用状态 ---------- */
.fatal {
  text-align: center;
  padding: 32px 8px;
}
.fatal-icon {
  font-size: 40px;
  margin-bottom: 12px;
}
.fatal-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 10px;
}
.fatal-msg {
  font-size: 14px;
  color: var(--danger);
  margin: 0 0 8px;
  line-height: 1.6;
}
.fatal-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

.loading-text {
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
  padding: 40px 0;
  margin: 0;
}

/* ---------- 头部 ---------- */
.head {
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 18px;
}
.brand {
  font-size: 12px;
  color: var(--text-tertiary);
  letter-spacing: 0.4px;
  margin-bottom: 8px;
}
.title {
  font-size: 20px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 12px;
}
.who {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.who-name {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}
.who-stage {
  font-size: 12px;
  color: var(--accent);
  background: var(--accent-light);
  padding: 3px 9px;
  border-radius: 999px;
}
.expiry {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 10px 0 0;
}

.progress {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 14px;
}
.progress strong {
  color: var(--accent);
  font-weight: 500;
}

/* ---------- 清单 ---------- */
.items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  margin-bottom: 10px;
  background: var(--surface);
  transition: border-color var(--transition-fast), background var(--transition-fast);
}
.item.done {
  border-color: var(--success);
  background: var(--success-light);
}
.item-icon {
  font-size: 20px;
  flex-shrink: 0;
}
.item-meta {
  flex: 1;
  min-width: 0;
}
.item-name {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 3px;
}
.item-status {
  font-size: 12px;
  color: var(--text-tertiary);
}
.item.done .item-status {
  color: var(--success);
}
.item-btn {
  flex-shrink: 0;
  font-size: 13px;
  padding: 7px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--text-inverse);
  cursor: pointer;
  transition: background var(--transition-fast), opacity var(--transition-fast);
}
.item.done .item-btn {
  background: transparent;
  color: var(--accent);
}
.item-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  color: var(--text-inverse);
}
.item-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ---------- 提示 ---------- */
.notice {
  font-size: 13px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  margin: 14px 0 0;
  line-height: 1.5;
}
.notice.ok {
  color: var(--success);
  background: var(--success-light);
}
.notice.err {
  color: var(--danger);
  background: var(--danger-light);
}

.tips {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.7;
  margin: 18px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
}

.hidden-input {
  display: none;
}

@media (max-width: 480px) {
  .submit-page {
    padding: 12px 10px 32px;
  }
  .submit-card {
    padding: 20px 16px;
    border-radius: var(--radius-md);
  }
  .item {
    padding: 12px 10px;
    gap: 10px;
  }
  .item-btn {
    padding: 7px 11px;
    font-size: 12px;
  }
}
</style>
