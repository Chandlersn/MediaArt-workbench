<template>
  <div class="certificates-page">
    <div class="page-header">
      <h2>证书管理</h2>
      <div class="header-actions">
        <button class="btn-secondary btn-sm" :class="{ active: showSync }" @click="showSync = !showSync">从选手同步</button>
        <button class="btn-secondary btn-sm" :class="{ active: preview }" @click="triggerFile">导入台账</button>
        <button class="btn-secondary btn-sm" :class="{ active: showRules }" @click="showRules = !showRules">编号规则</button>
        <button class="btn-primary btn-sm" :disabled="visibleCertificates.length === 0" @click="exportLedger(filtered, '仅导出当前筛选结果')">
          导出当前台账
        </button>
        <button class="btn-primary btn-sm" :disabled="visibleCertificates.length === 0" @click="exportLedger(visibleCertificates, '导出当前会话全部证书')">
          导出当前会话
        </button>
        <input ref="fileInput" type="file" accept=".xlsx,.xls" style="display: none" @change="onFileChange" />
      </div>
    </div>

    <!-- 自动关联：从已有选手/机构数据生成证书 -->
    <div v-if="showSync" class="panel">
      <div class="panel-title">从选手与机构数据自动生成证书（自动关联）</div>
      <div class="panel-desc">
        选择赛事项目与赛事阶段后，系统会读取已录入的「选手」「机构」数据，为每位选手自动建立一张证书，
        自动带出姓名、选送机构、组别；赛事阶段、奖项、作品名称等可在下方明细中补填。
        证书编号按规范自动生成（省赛：【川】CNRCSOV + 年份 + 四位序号；国赛：Q + 序号）。
        已存在的同名证书<b>只刷新身份字段</b>，你手工填写的内容不会被覆盖。
      </div>
      <div class="panel-actions">
        <label class="field">
          赛事项目
          <CustomSelect v-model="syncProjectId" style="width: 260px">
            <option value="">（不限项目，按全部选手）</option>
            <option v-for="p in projectOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
          </CustomSelect>
        </label>
        <label class="field">
          赛事阶段
          <CustomSelect v-model="syncRound" style="width: 160px">
            <option v-for="r in ROUND_ORDER" :key="r" :value="r">{{ r }}</option>
          </CustomSelect>
        </label>
        <button class="btn-primary" :disabled="syncing" @click="runSync">
          {{ syncing ? '同步中…' : '开始同步' }}
        </button>
        <span class="muted">当前选手库共 {{ playerCount }} 人</span>
      </div>
    </div>

    <!-- 编号规则：可配置编号模板（变量化），换项目/换赛事阶段均可复用 -->
    <div v-if="showRules" class="panel">
      <div class="panel-title">证书编号规则（可复用模板）</div>
      <div class="panel-desc">
        用占位变量编排编号格式，导入或同步时按模板自动生成。可用变量：
        <code>{province}</code> 省份、<code>{code}</code> 编号前缀、<code>{year}</code> 年份、
        <code>{seq}</code> 序号、<code>{seq:N}</code> 补零到 N 位（如 <code>{seq:4}</code>）。
        省赛与国赛分别配置；下方默认值决定生成时的省份/前缀/年份。
      </div>
      <div class="rules-grid">
        <label class="field col">
          省赛模板
          <input v-model="tplProvince" class="form-input mono" placeholder="【{province}】{code}{year}{seq:4}" />
        </label>
        <label class="field col">
          国赛模板
          <input v-model="tplNational" class="form-input mono" placeholder="Q{seq}" />
        </label>
        <label class="field">
          默认省份
          <input v-model="defProvince" class="form-input" style="width:90px" placeholder="川" />
        </label>
        <label class="field">
          默认编号前缀
          <input v-model="defCode" class="form-input mono" style="width:150px" placeholder="CNRCSOV" />
        </label>
        <label class="field">
          默认年份
          <input v-model.number="defYear" type="number" class="form-input" style="width:100px" />
        </label>
      </div>
      <div class="rules-preview">
        <span class="muted">预览：</span>
        <span class="pill mono">省赛 {{ previewProvince }}</span>
        <span class="pill mono">国赛 {{ previewNational }}</span>
      </div>
      <div class="panel-actions">
        <button class="btn-primary" :disabled="savingRules" @click="saveRules">
          {{ savingRules ? '保存中…' : '保存规则' }}
        </button>
        <span class="warn-text">保存后立即生效，并随数据持久化；切换项目时直接改这里即可复用。</span>
      </div>
    </div>

    <!-- 导入预览 -->
    <div v-if="preview" class="panel">
      <div class="panel-head">
        <div>
          <strong>导入预览：{{ preview.fileName }}</strong>
          <span class="muted">（{{ preview.orgSheets }} 个机构分表，提取 {{ preview.raw }} 行）</span>
        </div>
        <button class="btn-text" @click="cancelImport">收起</button>
      </div>
      <div class="preview-stats">
        <div class="stat"><span class="num">{{ preview.unique }}</span><span class="lbl">去重后证书数</span></div>
        <div class="stat"><span class="num">{{ preview.dup }}</span><span class="lbl">重复编号（将被合并）</span></div>
        <div class="stat"><span class="num">{{ preview.missingWorkName }}</span><span class="lbl">缺作品名</span></div>
      </div>
      <div class="preview-dist">
        <div class="dist-block">
          <div class="dist-title">按奖项</div>
          <span v-for="(c, k) in preview.byAward" :key="k" class="pill">{{ k }}：{{ c }}</span>
        </div>
        <div class="dist-block">
          <div class="dist-title">按赛事阶段</div>
          <span v-for="(c, k) in preview.byRound" :key="k" class="pill">{{ k }}：{{ c }}</span>
        </div>
      </div>
      <div class="panel-actions">
        <label class="field">
          归属项目
          <CustomSelect v-model="importProjectId" style="width: 260px">
            <option value="">（未选择，仅作独立证书）</option>
            <option v-for="p in projectOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
          </CustomSelect>
        </label>
        <button class="btn-primary" :disabled="importing" @click="confirmImport">
          {{ importing ? '导入中…' : '确认导入' }}
        </button>
        <span class="warn-text">导入按证书编号合并覆盖；重复编号只保留最后一条</span>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div v-if="stats.total > 0" class="stat-cards">
      <div class="stat-card"><span class="num">{{ stats.total }}</span><span class="lbl">证书总数</span></div>
      <div class="stat-card"><span class="num">{{ stats.packed }}</span><span class="lbl">已打包</span></div>
      <div class="stat-card"><span class="num">{{ stats.unpacked }}</span><span class="lbl">未打包</span></div>
      <div class="stat-card"><span class="num">{{ stats.missingWorkName }}</span><span class="lbl">缺作品名</span></div>
    </div>

    <!-- 导入会话：每次导入/同步为一个会话，可切换、可删除（删除仅抹除该批） -->
    <div v-if="sessions.length > 0" class="session-bar">
      <span class="session-label">导入会话</span>
      <div class="session-chips">
        <button
          v-for="s in sessions"
          :key="s.id"
          class="session-chip"
          :class="{ active: s.id === activeSessionId }"
          @click="switchSession(s.id)"
        >
          <span class="session-name">{{ s.name }}</span>
          <span class="session-count">{{ s.count }}</span>
          <span
            class="session-del"
            :title="s.id === 'legacy-import' ? '删除将抹除全部历史导入数据' : '删除该会话（仅抹除本批）'"
            @click.stop="removeSession(s)"
          >×</span>
        </button>
      </div>
    </div>

    <!-- 来源上下文：从机构 / 项目详情页的「关联证书」跳转带入 -->
    <div v-if="ctxActive" class="ctx-bar">
      <span class="ctx-label">已限定来源：{{ ctxLabel }}</span>
      <button class="btn-text" @click="clearContext">清除筛选</button>
    </div>

    <!-- 筛选栏 -->
    <div v-if="visibleCertificates.length > 0" class="filter-bar">
      <CustomSelect v-model="filterAward" style="width:150px">
        <option value="">全部奖项</option>
        <option v-for="a in awardOptions" :key="a" :value="a">{{ a }}</option>
      </CustomSelect>
      <CustomSelect v-model="filterRound" style="width:150px">
        <option value="">全部阶段</option>
        <option v-for="r in roundOptions" :key="r" :value="r">{{ r }}</option>
      </CustomSelect>
      <CustomSelect v-model="filterPacked" style="width:150px">
        <option value="">全部打包状态</option>
        <option value="已打包">已打包</option>
        <option value="未打包">未打包</option>
        <option value="待核对">待核对</option>
      </CustomSelect>
      <button class="btn-secondary btn-sm" :class="{ active: ctxMissing }" @click="ctxMissing = !ctxMissing">
        仅缺作品名
      </button>
      <input v-model="keyword" class="form-input" placeholder="搜索姓名 / 机构 / 作品 / 证书号" style="flex:1; min-width:180px;" />
    </div>

    <!-- 图表 -->
    <div v-if="stats.total > 0" class="charts">
      <div class="chart-card">
        <div class="chart-title">奖项分布</div>
        <canvas ref="awardChart"></canvas>
      </div>
      <div class="chart-card">
        <div class="chart-title">按机构 TOP 10</div>
        <canvas ref="orgChart"></canvas>
      </div>
    </div>

    <!-- 明细表 -->
    <div v-if="filtered.length > 0" class="cert-table-wrap">
      <table class="cert-table">
        <thead>
          <tr>
            <th>证书编号</th>
            <th>选手姓名</th>
            <th>组别</th>
            <th>奖项</th>
            <th>赛事阶段</th>
            <th>作品名称</th>
            <th>选送机构</th>
            <th>收件机构</th>
            <th>打包</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in pagedRows" :key="c.certNumber">
            <td class="mono">{{ c.certNumber }}</td>
            <td>{{ c.playerName }}</td>
            <td>{{ c.groupName }}</td>
            <td><span :class="['badge', awardClass(c.award)]">{{ c.award || '待填' }}</span></td>
            <td>{{ c.certRound }}</td>
            <td :class="{ 'cell-warn': !c.workName }">{{ c.workName || '待补录' }}</td>
            <td>{{ c.orgName }}</td>
            <td>{{ c.receivingOrg || c.orgName }}</td>
            <td>
              <CustomSelect v-model="c.packed" style="width:110px" @change="() => setPacked(c)">
                <option value="已打包">已打包</option>
                <option value="未打包">未打包</option>
                <option value="待核对">待核对</option>
              </CustomSelect>
            </td>
            <td>
              <div class="row-actions">
                <button class="btn-text" @click="openEdit(c)">填写</button>
                <span class="row-sep"></span>
                <button class="btn-text danger" @click="removeCert(c)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="table-foot">
        <Pagination
          :total-items="filtered.length"
          :page-size="pageSize"
          :current-page="currentPage"
          @page-change="currentPage = $event"
          @page-size-change="onPageSizeChange"
        />
      </div>
    </div>

    <div v-if="certificates.length === 0" class="empty-state">
      暂无证书数据。可点击右上角「导入台账」导入既有 Excel，或用「从选手同步」由系统中已录入的选手自动生成。
    </div>
    <div v-else-if="visibleCertificates.length === 0" class="empty-state">
      当前会话暂无证书。可在上方「导入会话」中切换到其他批次，或导入新的台账 / 从选手同步。
    </div>

    <!-- 填写抽屉 -->
    <div v-if="editing" class="drawer-mask" @click.self="closeEdit">
      <div class="drawer">
        <div class="drawer-head">
          <strong>填写证书信息</strong>
          <button class="btn-text" @click="closeEdit">收起</button>
        </div>
        <div class="drawer-body">
          <div class="drawer-row">
            <span class="drawer-label">证书编号</span>
            <span class="mono">{{ editing.certNumber }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">选手姓名</span>
            <input v-model="editing.playerName" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">赛事阶段</span>
            <CustomSelect v-model="editing.certRound" style="width:100%">
              <option v-for="r in roundOptionsAll" :key="r" :value="r">{{ r }}</option>
            </CustomSelect>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">组别</span>
            <input v-model="editing.groupName" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">奖项</span>
            <CustomSelect v-model="editing.award" style="width:100%">
              <option value="">（待定）</option>
              <option v-for="a in awardOptionsAll" :key="a" :value="a">{{ a }}</option>
            </CustomSelect>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">作品名称</span>
            <input v-model="editing.workName" class="form-input" placeholder="必填，用于证书印制" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">指导老师</span>
            <input v-model="editing.instructor" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">语种</span>
            <input v-model="editing.language" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">晋级情况</span>
            <input v-model="editing.promotion" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">选送机构（校区）</span>
            <input v-model="editing.orgName" class="form-input" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">收件机构</span>
            <input v-model="editing.receivingOrg" class="form-input" placeholder="决定导出时分到哪张表" />
          </div>
          <div class="drawer-row">
            <span class="drawer-label">打包状态</span>
            <CustomSelect v-model="editing.packed" style="width:100%">
              <option value="已打包">已打包</option>
              <option value="未打包">未打包</option>
              <option value="待核对">待核对</option>
            </CustomSelect>
          </div>
        </div>
        <div class="drawer-foot">
          <button class="btn-primary" :disabled="saving" @click="saveEdit">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { useCertificateStore } from '../stores/certificate'
import { useProjectStore } from '../stores/project'
import { useOrganizationStore } from '../stores/organization'
import { usePlayerStore } from '../stores/player'
import { parseCertificateFile } from '../services/certificateImport'
import { exportCertificateLedger, ROUND_ORDER } from '../services/certificateExport'
import CustomSelect from '../components/CustomSelect.vue'
import Pagination from '../components/Pagination.vue'
import Chart from 'chart.js/auto'

const { success, error: toastError, warning } = useToast()
const { confirm } = useConfirmDialog()
const certStore = useCertificateStore()
const projectStore = useProjectStore()
const orgStore = useOrganizationStore()
const playerStore = usePlayerStore()

const certificates = computed(() => certStore.certificates)
const visibleCertificates = computed(() => certStore.visibleCertificates)
const sessions = computed(() => certStore.sessions)
const activeSessionId = computed(() => certStore.activeSessionId)
const fileInput = ref(null)
const preview = ref(null)
const importing = ref(false)
const syncing = ref(false)
const saving = ref(false)
const importProjectId = ref('')
const showSync = ref(false)
const showRules = ref(false)
const syncProjectId = ref('')
const syncRound = ref(ROUND_ORDER[0])

// 编号规则编辑（绑定到 certSettings 的模板与默认值）
const tplProvince = ref('')
const tplNational = ref('')
const defProvince = ref('')
const defCode = ref('')
const defYear = ref(new Date().getFullYear())
const savingRules = ref(false)

const previewProvince = computed(() => {
  try { return certStore.formatCertNumber('省级展演', 1, { province: defProvince.value || '川', code: defCode.value || 'CNRCSOV', year: defYear.value || new Date().getFullYear() }) } catch (e) { return '（模板无效）' }
})
const previewNational = computed(() => {
  try { return certStore.formatCertNumber('全国展演', 1, { province: defProvince.value || '川', code: defCode.value || 'CNRCSOV', year: defYear.value || new Date().getFullYear() }) } catch (e) { return '（模板无效）' }
})

const filterAward = ref('')
const filterRound = ref('')
const filterPacked = ref('')
const keyword = ref('')

// ===== 来源上下文筛选：由机构 / 项目详情页的「关联证书」点击跳转带入 =====
const route = useRoute()
const router = useRouter()
const ctxOrgId = ref('')
const ctxOrgName = ref('')
const ctxProjectId = ref('')
const ctxMissing = ref(false)

const applyRouteQuery = () => {
  const q = route.query || {}
  ctxOrgId.value = String(q.orgId || '')
  ctxOrgName.value = String(q.orgName || '')
  ctxProjectId.value = String(q.projectId || '')
  ctxMissing.value = q.missingWorkName === '1'
  filterAward.value = String(q.award || '')
  filterRound.value = String(q.round || '')
  filterPacked.value = String(q.packed || '')
  keyword.value = String(q.keyword || '')
  currentPage.value = 1
}

const clearContext = () => {
  ctxOrgId.value = ''
  ctxOrgName.value = ''
  ctxProjectId.value = ''
  ctxMissing.value = false
  currentPage.value = 1
  // 同时清掉地址栏参数，避免刷新又回到筛选态
  if (Object.keys(route.query || {}).length) router.replace({ path: '/certificates' })
}

const currentPage = ref(1)
const pageSize = ref(50)

const awardChart = ref(null)
const orgChart = ref(null)
let chartInstances = { award: null, org: null }

const projectOptions = computed(() => (projectStore.projects || []).map(p => ({ id: p.id, name: p.name })))
const playerCount = computed(() => (playerStore.players || []).length)

const AWARD_BASE = ['特金奖', '金奖', '银奖', '铜奖', '退赛']
const awardOptionsAll = ref(AWARD_BASE.slice())
const roundOptionsAll = ref(ROUND_ORDER.slice())

const awardOptions = computed(() => {
  const set = new Set(visibleCertificates.value.map(c => c.award).filter(Boolean))
  const list = AWARD_BASE.filter(a => set.has(a)).concat([...set].filter(a => !AWARD_BASE.includes(a)))
  // 奖项为空的证书在分组里叫「未分类」，下拉也要能选到
  return visibleCertificates.value.some(c => !c.award) ? list.concat(['未分类']) : list
})
const roundOptions = computed(() => {
  const set = new Set(visibleCertificates.value.map(c => c.certRound).filter(Boolean))
  return [...new Set([...ROUND_ORDER.filter(r => set.has(r)), ...[...set].filter(r => !ROUND_ORDER.includes(r))])]
})

// 上下文是否生效 + 提示条文案
const ctxActive = computed(() => !!(ctxOrgId.value || ctxOrgName.value || ctxProjectId.value))
const ctxLabel = computed(() => {
  if (ctxProjectId.value) {
    const p = projectOptions.value.find(x => x.id === ctxProjectId.value)
    return `项目「${p?.name || ctxProjectId.value}」`
  }
  if (ctxOrgName.value || ctxOrgId.value) return `机构「${ctxOrgName.value || ctxOrgId.value}」`
  return ''
})

const stats = computed(() => certStore.getCertStats({
  award: filterAward.value,
  certRound: filterRound.value,
  packed: filterPacked.value,
  orgId: ctxOrgId.value,
  orgName: ctxOrgName.value,
  projectId: ctxProjectId.value,
  missingWorkName: ctxMissing.value
}))

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return visibleCertificates.value.filter(c => {
    // 来源上下文：机构按 id / 名称任一命中（与详情页统计口径一致）；项目按 projectId
    if (ctxOrgId.value || ctxOrgName.value) {
      const hitOrg = (ctxOrgId.value && c.orgId === ctxOrgId.value) ||
        (ctxOrgName.value && c.orgName === ctxOrgName.value)
      if (!hitOrg) return false
    }
    if (ctxProjectId.value && c.projectId !== ctxProjectId.value) return false
    if (ctxMissing.value && !c.missingWorkName) return false
    if (filterAward.value) {
      if ((c.award || '未分类') !== filterAward.value) return false
    }
    if (filterRound.value && c.certRound !== filterRound.value) return false
    if (filterPacked.value) {
      if ((c.packed || '待核对') !== filterPacked.value) return false
    }
    if (kw) {
      const hay = [c.playerName, c.orgName, c.receivingOrg, c.workName, c.certNumber, c.instructor].join(' ').toLowerCase()
      if (!hay.includes(kw)) return false
    }
    return true
  })
})

const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})

const onPageSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
}

watch([filtered], () => { if (currentPage.value > Math.max(1, Math.ceil(filtered.value.length / pageSize.value))) currentPage.value = 1 })

const awardClass = (award) => {
  if (award === '特金奖') return 'a-gold'
  if (award === '金奖') return 'a-silver'
  if (award === '银奖') return 'a-bronze'
  if (award === '铜奖') return 'a-copper'
  return 'a-other'
}

const triggerFile = () => fileInput.value?.click()
const cancelImport = () => { preview.value = null; if (fileInput.value) fileInput.value.value = '' }

const onFileChange = async (e) => {
  const file = e.target.files && e.target.files[0]
  if (!file) return
  try {
    const { preview: p, rows, meta } = await parseCertificateFile(file)
    preview.value = { ...p, fileName: file.name, _rows: rows, _meta: meta }
  } catch (err) {
    toastError('解析文件失败：' + (err.message || err))
  }
}

const matchOrgId = (orgName) => {
  const found = (orgStore.organizations || []).find(o => o.name === orgName)
  return found ? found.id : ''
}
const matchPlayerId = (name, orgName) => {
  const list = playerStore.players || []
  const hit = list.find(p => p.name === name &&
    (p.orgName === orgName || (orgStore.organizations.find(o => o.id === p.orgId)?.name === orgName)))
  return hit ? hit.id : ''
}

const confirmImport = async () => {
  if (!preview.value) return
  importing.value = true
  try {
    const rows = preview.value._rows.map(r => ({
      ...r,
      projectId: importProjectId.value,
      orgId: matchOrgId(r.orgName),
      playerId: matchPlayerId(r.playerName, r.orgName),
      importId: preview.value._meta?.parsedAt || new Date().toISOString()
    }))
    await certStore.importCertificates(rows, { fileName: preview.value.fileName, projectId: importProjectId.value })
    success(`已导入 ${rows.length} 条证书`)
    preview.value = null
    if (fileInput.value) fileInput.value.value = ''
  } catch (err) {
    toastError('导入失败：' + (err.message || err))
  } finally {
    importing.value = false
  }
}

/** 自动关联：由选手库生成证书 */
const runSync = async () => {
  if (playerCount.value === 0) {
    warning('选手库为空，请先在「选手」中录入参赛选手')
    return
  }
  syncing.value = true
  try {
    const res = await certStore.syncFromPlayers(playerStore.players || [], orgStore.organizations || [], {
      projectId: syncProjectId.value,
      certRound: syncRound.value,
      assignNumbers: true
    })
    success(`同步完成：新增 ${res.created} 条，更新 ${res.updated} 条`)
    showSync.value = false
  } catch (err) {
    toastError('同步失败：' + (err.message || err))
  } finally {
    syncing.value = false
  }
}

/** 导出台账 */
const exportLedger = (list, scopeLabel) => {
  if (!list || list.length === 0) {
    warning('没有可导出的证书数据')
    return
  }
  try {
    const projectName = importProjectId.value
      ? (projectOptions.value.find(p => p.id === importProjectId.value)?.name || '')
      : ''
    const res = exportCertificateLedger(list, {
      titlePrefix: projectName || '证书台账',
      includeSummaries: true
    })
    success(`${scopeLabel}：已生成 ${res.sheetCount} 张工作表，共 ${res.certCount} 条证书`)
  } catch (err) {
    toastError('导出失败：' + (err.message || err))
  }
}

const setPacked = async (c) => {
  try {
    await certStore.updateCert(c.certNumber, { packed: c.packed }, c.sessionId)
  } catch (err) {
    toastError('更新打包状态失败：' + (err.message || err))
  }
}

const removeCert = async (c) => {
  const ok = await confirm({
    title: '删除证书',
    message: `确定删除证书「${c.certNumber}」（选手：${c.playerName || '—'}）吗？该操作仅影响当前会话下的这一条。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'danger'
  })
  if (!ok) return
  try {
    await certStore.deleteCert(c.certNumber, c.sessionId)
    success('已删除')
  } catch (err) {
    toastError('删除失败：' + (err.message || err))
  }
}

// 切换导入会话（仅改变可视范围）
const switchSession = async (id) => {
  try {
    await certStore.switchSession(id)
  } catch (err) {
    toastError('切换会话失败：' + (err.message || err))
  }
}

// 删除导入会话：仅抹除该会话下的证书
const removeSession = async (s) => {
  const isLegacy = s.id === 'legacy-import'
  const ok = await confirm({
    title: isLegacy ? '删除历史导入会话' : '删除导入会话',
    message: isLegacy
      ? `「历史导入」包含 ${s.count} 条证书，删除后将彻底抹除且不可恢复。确定继续吗？`
      : `确定删除会话「${s.name}」吗？将抹除该会话下的 ${s.count} 条证书，其它会话不受影响。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'danger'
  })
  if (!ok) return
  try {
    const removed = await certStore.deleteSession(s.id)
    success(`已删除会话，抹除 ${removed} 条证书`)
  } catch (err) {
    toastError('删除会话失败：' + (err.message || err))
  }
}

// 保存编号规则（模板 + 默认省/前缀/年）
const saveRules = async () => {
  savingRules.value = true
  try {
    await certStore.updateTemplateSettings({
      templates: { province: tplProvince.value, national: tplNational.value },
      defaults: { province: defProvince.value, code: defCode.value, year: defYear.value }
    })
    success('编号规则已保存')
    showRules.value = false
  } catch (err) {
    toastError('保存规则失败：' + (err.message || err))
  } finally {
    savingRules.value = false
  }
}

const syncRulesFromStore = () => {
  tplProvince.value = certStore.templates.province
  tplNational.value = certStore.templates.national
  defProvince.value = certStore.defaults.province
  defCode.value = certStore.defaults.code
  defYear.value = certStore.defaults.year
}

// 填写抽屉
const editing = ref(null)
const openEdit = (c) => { editing.value = { ...c } }
const closeEdit = () => { editing.value = null }
const saveEdit = async () => {
  if (!editing.value) return
  saving.value = true
  try {
    const patch = { ...editing.value }
    delete patch.certNumber
    patch.missingWorkName = patch.workName ? 0 : 1
    patch.isWithdrawn = (patch.award || '').includes('退赛') ? 1 : 0
    patch.receivingOrg = patch.receivingOrg || patch.orgName
    await certStore.updateCert(editing.value.certNumber, patch, editing.value.sessionId)
    success('已保存')
    editing.value = null
  } catch (err) {
    toastError('保存失败：' + (err.message || err))
  } finally {
    saving.value = false
  }
}

const renderCharts = () => {
  if (!stats.value.total) return
  const awardData = stats.value.byAward
  if (awardChart.value) {
    if (chartInstances.award) chartInstances.award.destroy()
    chartInstances.award = new Chart(awardChart.value, {
      type: 'bar',
      data: { labels: awardData.map(d => d.award), datasets: [{ label: '证书数', data: awardData.map(d => d.count), backgroundColor: '#b0392b' }] },
      options: { responsive: true, plugins: { legend: { display: false } } }
    })
  }
  const orgData = stats.value.byOrg
  if (orgChart.value) {
    if (chartInstances.org) chartInstances.org.destroy()
    chartInstances.org = new Chart(orgChart.value, {
      type: 'bar',
      data: { labels: orgData.map(d => d.org), datasets: [{ label: '证书数', data: orgData.map(d => d.count), backgroundColor: '#6b5d4f' }] },
      options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false } } }
    })
  }
}

watch([stats, filtered], () => { nextTick(renderCharts) }, { deep: true })

onMounted(async () => {
  await Promise.all([
    certStore.loadCertificates(),
    projectStore.loadProjects?.(),
    orgStore.loadOrganizations?.(),
    playerStore.loadPlayers?.()
  ].filter(Boolean))
  syncRulesFromStore()
  applyRouteQuery()
  await nextTick()
  renderCharts()
})

onActivated(async () => {
  await certStore.loadCertificates()
  await Promise.all([
    projectStore.loadProjects?.(),
    orgStore.loadOrganizations?.(),
    playerStore.loadPlayers?.()
  ].filter(Boolean))
  syncRulesFromStore()
  applyRouteQuery()
  await nextTick()
  renderCharts()
})

// 地址栏 query 变化（例如从另一个机构再点进来）时重新应用上下文
watch(() => route.query, () => applyRouteQuery())
</script>

<style scoped>
.certificates-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; gap: 12px; flex-wrap: wrap; }
.page-header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
.header-actions { display: flex; gap: 10px; flex-wrap: wrap; }

.panel { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 20px; }
.panel-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.panel-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin-bottom: 12px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.field { font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 8px; }

.preview-stats { display: flex; gap: 24px; margin: 12px 0; }
.stat { display: flex; flex-direction: column; }
.stat .num { font-size: 22px; font-weight: 700; color: var(--cinnabar, #b0392b); }
.stat .lbl { font-size: 12px; color: var(--text-secondary); }
.preview-dist { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 12px; }
.dist-title { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.pill { display: inline-block; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 12px; padding: 2px 10px; font-size: 12px; margin: 0 6px 6px 0; }
.warn-text { font-size: 12px; color: var(--text-secondary); }

.stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.stat-card { background: var(--bg-secondary); border-radius: 12px; padding: 16px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.stat-card .num { display: block; font-size: 26px; font-weight: 700; color: var(--text-primary); }
.stat-card .lbl { font-size: 13px; color: var(--text-secondary); }

.filter-bar { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }
.ctx-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 8px 14px; background: #f7ece9; border-left: 3px solid var(--cinnabar, #b0392b); border-radius: 6px; }
.ctx-label { font-size: 13px; font-weight: 600; color: var(--cinnabar, #b0392b); }

.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.chart-card { background: var(--bg-secondary); border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.chart-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-primary); }
.chart-card canvas { max-height: 280px; }

.cert-table-wrap { background: var(--bg-secondary); border-radius: 12px; padding: 8px 16px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow-x: auto; }
.cert-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cert-table th, .cert-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }
.cert-table th { color: var(--text-secondary); font-weight: 600; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.cell-warn { color: var(--cinnabar, #b0392b); }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.a-gold { background: #f3e2dd; color: #b0392b; }
.a-silver { background: #eee; color: #555; }
.a-bronze { background: #f0e6da; color: #8a6d3b; }
.a-copper { background: #e8eef0; color: #4a6b78; }
.a-other { background: var(--bg-primary); color: var(--text-secondary); }
.table-foot { margin-top: 12px; }
.muted { color: var(--text-secondary); font-size: 13px; }

.drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 1000; }
.drawer { position: absolute; top: 0; right: 0; width: 420px; max-width: 92vw; height: 100%; background: var(--bg-primary); display: flex; flex-direction: column; box-shadow: -4px 0 16px rgba(0,0,0,0.18); }
.drawer-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.drawer-body { padding: 16px 20px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 14px; }
.drawer-row { display: flex; flex-direction: column; gap: 6px; }
.drawer-label { font-size: 12px; color: var(--text-secondary); }
.drawer-foot { padding: 14px 20px; border-top: 1px solid var(--border); }

.btn-primary { background: var(--cinnabar, #b0392b); color: #fff; border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border); border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.btn-secondary.active,
.btn-secondary.active:hover { background: var(--cinnabar, #b0392b); color: #fff; border-color: var(--cinnabar, #b0392b); }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn-text { background: none; border: none; color: var(--cinnabar, #b0392b); cursor: pointer; font-size: 13px; }
.btn-text.danger { color: #c0392b; }
.empty-state { padding: 60px 20px; text-align: center; color: var(--text-secondary); }

/* 导入会话条 */
.session-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.session-label { font-size: 13px; color: var(--text-secondary); white-space: nowrap; }
.session-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.session-chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 18px; background: var(--bg-secondary); color: var(--text-primary); cursor: pointer; font-size: 13px; }
.session-chip.active { border-color: var(--cinnabar, #b0392b); background: #f7ece9; color: var(--cinnabar, #b0392b); font-weight: 600; }
.session-name { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-count { background: rgba(0,0,0,0.06); border-radius: 10px; padding: 0 6px; font-size: 12px; }
.session-chip.active .session-count { background: rgba(176,57,43,0.12); }
.session-del { color: var(--text-secondary); font-size: 16px; line-height: 1; padding: 0 2px; }
.session-del:hover { color: #c0392b; }

/* 行操作：填写与删除拉开间距，避免误点 */
.row-actions { display: inline-flex; align-items: center; gap: 14px; }
.row-sep { width: 1px; height: 14px; background: var(--border); }

/* 编号规则面板 */
.rules-grid { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end; margin: 12px 0; }
.rules-grid .field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-secondary); }
.rules-grid .col { flex: 1 1 260px; }
.rules-grid .mono { font-family: ui-monospace, monospace; }
.rules-preview { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.rules-preview .pill { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 12px; padding: 2px 10px; font-size: 12px; }
.rules-preview .mono { font-family: ui-monospace, monospace; }
</style>
