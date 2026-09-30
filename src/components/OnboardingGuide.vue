<template>
  <Modal
    :show="visible"
    title="欢迎使用媒体艺术智能工作台"
    size="medium"
    :close-on-overlay="false"
    @close="dismiss"
    @update:show="(v) => { if (!v) dismiss() }"
  >
    <div class="ob">
      <p class="ob-lead">
        看起来系统里还没有数据。建议按下面的顺序开始 ——
        建好这几步之后，资料催收、缺料提醒、归档都会自动串起来。
      </p>

      <ol class="ob-steps">
        <li v-for="(s, i) in steps" :key="s.name" class="ob-step">
          <span class="ob-index">{{ i + 1 }}</span>
          <div class="ob-body">
            <div class="ob-name">{{ s.name }}</div>
            <div class="ob-desc">{{ s.desc }}</div>
          </div>
        </li>
      </ol>

      <p class="ob-note">
        这份引导只出现这一次，之后可以在左侧「使用说明」里随时查看。
      </p>
    </div>

    <template #footer>
      <button class="btn-primary" @click="dismiss">开始使用</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { get } from '../services/http'

/**
 * 安装后首次使用的引导。
 *
 * 定位说明：这是「第一次使用」的一次性引导，**不是工作台页面里的常驻内容**。
 * 因此它挂在应用级（App.vue），只在「已登录 + 系统里一条数据都没有 + 用户还没看过」
 * 三个条件同时成立时出现；用户点掉之后写入 localStorage，不再打扰。
 * 已有数据的老用户不会看到（避免打扰），检查失败时也静默跳过（不影响正常使用）。
 */

const STORAGE_KEY = 'workbench_onboarding_done'

const props = defineProps({
  // 是否处于「可能出现引导」的状态：已登录，且不在公开页
  active: { type: Boolean, default: false }
})

const visible = ref(false)
let checked = false

const steps = [
  { name: '建项目', desc: '一个活动 / 赛事就是一个项目' },
  { name: '录机构', desc: '参赛单位、合作方' },
  { name: '录选手', desc: '关联到对应项目与机构' },
  { name: '配资料要求', desc: '在「资料配置」里指定每个赛段要收哪些材料，之后缺料会自动标红并置顶' }
]

function isDone() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function markDone() {
  try {
    localStorage.setItem(STORAGE_KEY, '1')
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略即可 */
  }
}

function dismiss() {
  visible.value = false
  markDone()
}

async function maybeShow() {
  if (checked || isDone()) return
  checked = true
  try {
    const res = await get('/api/data/load')
    const d = res.data || {}
    const hasData = Boolean(
      (d.projects && d.projects.length) ||
      (d.organizations && d.organizations.length) ||
      (d.players && d.players.length)
    )
    if (hasData) {
      // 已有数据说明不是全新部署，直接标记为已看过，不再打扰
      markDone()
      return
    }
    visible.value = true
  } catch (e) {
    // 检查失败就不显示引导，绝不影响正常使用
    console.warn('首次使用引导检查跳过:', e)
  }
}

watch(
  () => props.active,
  (v) => {
    if (v) maybeShow()
  },
  { immediate: true }
)
</script>

<style scoped>
.ob-lead {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0 0 20px;
}

.ob-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ob-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.ob-index {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  line-height: 24px;
  text-align: center;
}

.ob-body {
  flex: 1;
  min-width: 0;
}

.ob-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.ob-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.ob-note {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 20px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
  line-height: 1.6;
}
</style>
