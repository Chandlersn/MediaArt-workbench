import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as dataService from '../services/dataService.js'
import { useAuditLogStore } from './auditLog'

/** 默认编号模板与默认值（换项目/换赛事阶段可复用，存于 certSettings） */
const DEFAULT_SETTINGS = () => ({
  activeSessionId: '',
  sessionMeta: {}, // { [sessionId]: { name, createdAt, kind } }
  templates: {
    // 省赛：可放 {province}{code}{year}{seq}{seq:N} 变量
    province: '【{province}】{code}{year}{seq:4}',
    // 国赛
    national: 'Q{seq}'
  },
  defaults: {
    province: '川',
    code: 'CNRCSOV',
    year: new Date().getFullYear()
  }
})

const LEGACY_SESSION = 'legacy-import'

const normalizeSettings = (s) => {
  const base = DEFAULT_SETTINGS()
  if (!s || typeof s !== 'object') return base
  return {
    activeSessionId: s.activeSessionId || '',
    sessionMeta: (s.sessionMeta && typeof s.sessionMeta === 'object') ? s.sessionMeta : {},
    templates: {
      province: s.templates?.province || base.templates.province,
      national: s.templates?.national || base.templates.national
    },
    defaults: {
      province: s.defaults?.province || base.defaults.province,
      code: s.defaults?.code || base.defaults.code,
      year: s.defaults?.year || base.defaults.year
    }
  }
}

const genSessionId = () => 's-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7)

const isNational = (round) => {
  const r = round || ''
  return r === '全国展演' || r.includes('国赛') || r.includes('全国展演')
}

/** 把编号模板渲染为字符串：{province}{code}{year}{seq}{seq:N} */
const renderTemplate = (tpl, vars) => {
  return String(tpl).replace(/\{(\w+)(?::(\d+))?\}/g, (m, name, pad) => {
    if (name === 'seq') {
      const s = String(vars.seq ?? '')
      return pad ? s.padStart(Number(pad), '0') : s
    }
    if (name === 'province') return String(vars.province ?? '')
    if (name === 'code') return String(vars.code ?? '')
    if (name === 'year') return String(vars.year ?? '')
    return m // 未知占位符原样保留
  })
}

export const useCertificateStore = defineStore('certificate', () => {
  const certificates = ref([])          // 全量（跨会话）
  const certSettings = ref(normalizeSettings(null))
  const activeSessionId = ref('')
  const loading = ref(false)
  const error = ref(null)
  const lastImport = ref(null)

  const AWARD_ORDER = ['特金奖', '金奖', '银奖', '铜奖', '退赛']

  // 会话列表（由证书按 sessionId 聚合，名称取 certSettings.sessionMeta）
  const sessions = computed(() => {
    const counts = {}
    for (const c of certificates.value) {
      const sid = c.sessionId || LEGACY_SESSION
      counts[sid] = (counts[sid] || 0) + 1
    }
    return Object.keys(counts).map(sid => {
      const meta = certSettings.value.sessionMeta?.[sid] || {}
      const name = meta.name || (sid === LEGACY_SESSION ? '历史导入' : `批次 ${sid.slice(-4)}`)
      return {
        id: sid,
        name,
        count: counts[sid],
        kind: meta.kind || (sid === LEGACY_SESSION ? 'legacy' : 'import'),
        createdAt: meta.createdAt || ''
      }
    }).sort((a, b) => {
      if (a.id === LEGACY_SESSION) return -1
      if (b.id === LEGACY_SESSION) return 1
      return (b.createdAt || '').localeCompare(a.createdAt || '')
    })
  })

  // 当前会话可见证书
  const visibleCertificates = computed(() => {
    const aid = activeSessionId.value || LEGACY_SESSION
    return certificates.value.filter(c => (c.sessionId || LEGACY_SESSION) === aid)
  })

  const templates = computed(() => certSettings.value.templates)
  const defaults = computed(() => certSettings.value.defaults)

  const loadCertificates = async () => {
    loading.value = true
    error.value = null
    try {
      await dataService.load()
      const raw = dataService.getData('certificates') || []
      // 旧数据（无 sessionId）统一归入 legacy 会话，保证可见、可切换
      certificates.value = raw.map(c => ({ ...c, sessionId: c.sessionId || LEGACY_SESSION }))
      certSettings.value = normalizeSettings(dataService.getData('certSettings'))
      const ids = sessions.value.map(s => s.id)
      const aid = certSettings.value.activeSessionId || ''
      activeSessionId.value = (aid && ids.includes(aid)) ? aid : (ids[0] || '')
      certSettings.value.activeSessionId = activeSessionId.value
    } catch (e) {
      console.error('加载证书失败:', e)
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const getCertById = (certNumber, sessionId) => {
    const sid = sessionId || activeSessionId.value || LEGACY_SESSION
    return certificates.value.find(c => c.certNumber === certNumber && (c.sessionId || LEGACY_SESSION) === sid) || null
  }

  const getCertsByProject = (projectId) => {
    if (!projectId) return []
    return certificates.value.filter(c => c.projectId === projectId)
  }

  const getCertsByOrg = (orgId) => {
    if (!orgId) return []
    return certificates.value.filter(c => c.orgId === orgId)
  }

  // 聚合统计：默认作用于当前会话；可按 award / certRound / language / packed 过滤
  const getCertStats = (filter = {}) => {
    let list = visibleCertificates.value
    if (filter.projectId) list = list.filter(c => c.projectId === filter.projectId)
    if (filter.orgId || filter.orgName) {
      list = list.filter(c =>
        (filter.orgId ? c.orgId === filter.orgId : false) ||
        (filter.orgName ? c.orgName === filter.orgName : false)
      )
    }
    // 奖项：空值按「未分类」处理，与下方 byAward 的分组口径保持一致
    if (filter.award) list = list.filter(c => (c.award || '未分类') === filter.award)
    if (filter.certRound) list = list.filter(c => c.certRound === filter.certRound)
    if (filter.language) list = list.filter(c => c.language === filter.language)
    if (filter.packed) list = list.filter(c => c.packed === filter.packed)
    if (filter.missingWorkName) list = list.filter(c => c.missingWorkName)

    const byAward = {}
    const byRound = {}
    const byLanguage = {}
    const byOrg = {}
    let packedCount = 0
    let unpackedCount = 0
    let missingWorkName = 0

    for (const c of list) {
      const award = c.award || '未分类'
      byAward[award] = (byAward[award] || 0) + 1
      const round = c.certRound || '未分类'
      byRound[round] = (byRound[round] || 0) + 1
      const lang = c.language || '未分类'
      byLanguage[lang] = (byLanguage[lang] || 0) + 1
      const org = c.orgName || '未归类'
      byOrg[org] = (byOrg[org] || 0) + 1
      if (c.packed === '已打包') packedCount++
      else if (c.packed === '未打包') unpackedCount++
      if (c.missingWorkName) missingWorkName++
    }

    const awardSorted = AWARD_ORDER
      .filter(a => byAward[a] != null)
      .map(a => ({ award: a, count: byAward[a] }))
      .concat(
        Object.keys(byAward)
          .filter(a => !AWARD_ORDER.includes(a))
          .map(a => ({ award: a, count: byAward[a] }))
      )

    const topOrgs = Object.keys(byOrg)
      .map(org => ({ org, count: byOrg[org] }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10)

    return {
      total: list.length,
      byAward: awardSorted,
      byRound,
      byLanguage,
      byOrg: topOrgs,
      packed: packedCount,
      unpacked: unpackedCount,
      missingWorkName
    }
  }

  // 全量持久化（证书 + 编号规则/会话设置）
  const persistAll = async () => {
    dataService.setData('certificates', certificates.value)
    dataService.setData('certSettings', certSettings.value)
    await dataService.save()
  }

  // 导入：每次导入 = 一个新会话，互不合并；切换/删除会话由用户控制
  const importCertificates = async (list, importMeta = {}) => {
    loading.value = true
    error.value = null
    try {
      const sessionId = genSessionId()
      const sessionName = importMeta.sessionName || importMeta.fileName || `导入批次`
      const rows = (Array.isArray(list) ? list : [])
        .filter(r => r && r.certNumber)
        .map(r => ({ ...r, sessionId }))
      certificates.value = certificates.value.concat(rows)
      certSettings.value.sessionMeta = {
        ...certSettings.value.sessionMeta,
        [sessionId]: { name: sessionName, createdAt: new Date().toISOString(), kind: 'import' }
      }
      certSettings.value.activeSessionId = sessionId
      activeSessionId.value = sessionId
      await persistAll()
      lastImport.value = {
        ...importMeta,
        at: new Date().toISOString(),
        count: rows.length,
        sessionId
      }
      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'import_certificates',
          actionType: 'create',
          target: '证书',
          description: `导入证书数据 ${rows.length} 条（会话：${sessionName}；源文件：${importMeta.fileName || '未知'}）`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }
      return rows.length
    } catch (e) {
      console.error('保存证书失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  // 切换会话（仅改变可视范围，不触达数据）
  const switchSession = async (id) => {
    if (!id) return
    activeSessionId.value = id
    certSettings.value.activeSessionId = id
    try {
      await persistAll()
    } catch (e) {
      console.error('切换会话失败:', e)
    }
  }

  // 删除会话：仅抹除该会话下的证书，其余会话不受影响
  const deleteSession = async (id) => {
    if (!id) return 0
    loading.value = true
    try {
      const before = certificates.value.length
      certificates.value = certificates.value.filter(c => (c.sessionId || LEGACY_SESSION) !== id)
      const removed = before - certificates.value.length
      const meta = { ...certSettings.value.sessionMeta }
      delete meta[id]
      certSettings.value.sessionMeta = meta
      if (activeSessionId.value === id) {
        const remaining = sessions.value
        activeSessionId.value = remaining.length ? remaining[0].id : ''
        certSettings.value.activeSessionId = activeSessionId.value
      }
      await persistAll()
      return removed
    } catch (e) {
      console.error('删除会话失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  // 保存编号规则 / 默认值（持久化到后端 certSettings）
  const saveSettings = async () => {
    dataService.setData('certSettings', certSettings.value)
    await dataService.save()
  }

  const updateTemplateSettings = async (patch) => {
    if (patch.templates) certSettings.value.templates = { ...certSettings.value.templates, ...patch.templates }
    if (patch.defaults) certSettings.value.defaults = { ...certSettings.value.defaults, ...patch.defaults }
    await saveSettings()
  }

  // 单条 upsert（手动修正）
  const saveCert = async (certData) => {
    loading.value = true
    error.value = null
    try {
      const now = new Date().toISOString()
      const sid = certData.sessionId || activeSessionId.value || LEGACY_SESSION
      const idx = certificates.value.findIndex(c => c.certNumber === certData.certNumber && (c.sessionId || LEGACY_SESSION) === sid)
      const merged = { ...certData, sessionId: sid, updatedAt: now }
      if (idx >= 0) {
        certificates.value[idx] = merged
      } else {
        merged.createdAt = merged.createdAt || now
        certificates.value.push(merged)
      }
      dataService.setData('certificates', certificates.value)
      await dataService.save()
      return merged
    } catch (e) {
      console.error('保存证书失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  const updateCert = async (certNumber, patch, sessionId) => {
    const sid = sessionId || activeSessionId.value || LEGACY_SESSION
    const idx = certificates.value.findIndex(c => c.certNumber === certNumber && (c.sessionId || LEGACY_SESSION) === sid)
    if (idx < 0) return null
    const merged = { ...certificates.value[idx], ...patch, sessionId: sid, updatedAt: new Date().toISOString() }
    certificates.value[idx] = merged
    dataService.setData('certificates', certificates.value)
    await dataService.save()
    return merged
  }

  const deleteCert = async (certNumber, sessionId) => {
    const sid = sessionId || activeSessionId.value || LEGACY_SESSION
    certificates.value = certificates.value.filter(c =>
      !((c.certNumber === certNumber) && ((c.sessionId || LEGACY_SESSION) === sid)))
    dataService.setData('certificates', certificates.value)
    await dataService.save()
  }

  // ===== 自动关联：由已有「选手 / 机构」数据生成证书（每次同步 = 一个新会话） =====

  /**
   * 依据当前已有证书，计算某赛事阶段的下一个序号
   * 通过编号模板反推前缀（模板中 {seq} 之前的部分），再取该前缀之后数字的最大值。
   */
  const nextSequence = (round, list, opts = {}) => {
    const tpl = isNational(round) ? certSettings.value.templates.national : certSettings.value.templates.province
    const vars = {
      province: opts.province ?? certSettings.value.defaults.province,
      code: opts.code ?? certSettings.value.defaults.code,
      year: opts.year ?? certSettings.value.defaults.year,
      seq: ''
    }
    const prefix = renderTemplate(tpl, vars)
    let max = 0
    for (const c of (list || [])) {
      if ((c.certRound || '') !== round) continue
      const cn = String(c.certNumber || '')
      if (prefix && cn.startsWith(prefix)) {
        const digits = cn.slice(prefix.length).replace(/\D/g, '')
        if (digits) max = Math.max(max, Number(digits))
      }
    }
    return max
  }

  /**
   * 生成符合编号模板的证书编号
   * @param {string} round 省级展演 / 全国展演
   * @param {number} seq 序号
   * @param {object} opts { province, code, year }
   */
  const formatCertNumber = (round, seq, opts = {}) => {
    const tpl = isNational(round) ? certSettings.value.templates.national : certSettings.value.templates.province
    const vars = {
      province: opts.province ?? certSettings.value.defaults.province,
      code: opts.code ?? certSettings.value.defaults.code,
      year: opts.year ?? certSettings.value.defaults.year,
      seq
    }
    return renderTemplate(tpl, vars)
  }

  /**
   * 从选手库同步生成证书（自动关联的核心）
   * 沿用已有实体信息；已存在的「选手+赛事阶段」只刷新身份字段。
   * 本次同步整体归入一个新会话，便于切换/回滚。
   *
   * @param {Array} playerList 选手数据
   * @param {Array} orgList 机构数据
   * @param {object} opts { projectId, certRound, assignNumbers, province, code, year }
   * @returns {Promise<{created:number, updated:number, skipped:number}>}
   */
  const syncFromPlayers = async (playerList = [], orgList = [], opts = {}) => {
    loading.value = true
    error.value = null
    try {
      const round = opts.certRound || '省级展演'
      const projectId = opts.projectId || ''
      const genOpts = {
        province: opts.province ?? certSettings.value.defaults.province,
        code: opts.code ?? certSettings.value.defaults.code,
        year: opts.year ?? certSettings.value.defaults.year
      }
      const orgNameById = new Map()
      for (const o of orgList) {
        if (o && o.id) orgNameById.set(o.id, o.name || '')
      }

      const targets = playerList.filter(p => p && (p.name || '').trim() && (!projectId || p.projectId === projectId))
      const pool = certificates.value
      const used = new Set(pool.map(c => c.certNumber))
      let seq = nextSequence(round, pool, genOpts)
      let created = 0
      let updated = 0
      let skipped = 0
      const now = new Date().toISOString()
      const additions = []
      const sessionId = genSessionId()
      const sessionName = `从选手同步 · ${round}`

      for (const p of targets) {
        const orgName = orgNameById.get(p.orgId) || p.orgName || ''
        const existing = pool.find(c => c.playerId === p.id && (c.certRound || round) === round)
        if (existing) {
          existing.playerName = p.name || existing.playerName
          existing.orgName = orgName || existing.orgName
          existing.orgId = p.orgId || existing.orgId
          existing.groupName = p.category || existing.groupName
          existing.receivingOrg = existing.receivingOrg || orgName
          existing.projectId = existing.projectId || projectId
          existing.updatedAt = now
          updated++
          continue
        }
        if (!opts.assignNumbers) { skipped++; continue }
        let certNumber = ''
        do {
          seq++
          certNumber = formatCertNumber(round, seq, genOpts)
        } while (used.has(certNumber))
        used.add(certNumber)

        additions.push({
          certNumber,
          sessionId,
          projectId,
          orgId: p.orgId || '',
          orgName,
          playerId: p.id,
          playerName: p.name || '',
          groupName: p.category || '',
          award: '',
          certRound: round,
          workName: '',
          instructor: '',
          language: '',
          promotion: '',
          packed: '待核对',
          missingWorkName: 1,
          isWithdrawn: 0,
          receivingOrg: orgName,
          sourceSheet: '',
          importId: '',
          createdAt: now,
          updatedAt: now
        })
        created++
      }

      certificates.value = pool.concat(additions)
      certSettings.value.sessionMeta = {
        ...certSettings.value.sessionMeta,
        [sessionId]: { name: sessionName, createdAt: now, kind: 'sync' }
      }
      certSettings.value.activeSessionId = sessionId
      activeSessionId.value = sessionId
      await persistAll()

      try {
        const auditStore = useAuditLogStore()
        await auditStore.addLog({
          action: 'sync_certificates_from_players',
          actionType: 'create',
          target: '证书',
          description: `从选手库同步证书：新增 ${created} 条、更新 ${updated} 条（赛事阶段：${round}；会话：${sessionName}）`
        })
      } catch (e) {
        console.warn('记录审计日志失败:', e)
      }

      return { created, updated, skipped }
    } catch (e) {
      console.error('从选手库同步证书失败:', e)
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    certificates,
    certSettings,
    activeSessionId,
    sessions,
    visibleCertificates,
    templates,
    defaults,
    loading,
    error,
    lastImport,
    loadCertificates,
    getCertById,
    getCertsByProject,
    getCertsByOrg,
    getCertStats,
    importCertificates,
    syncFromPlayers,
    switchSession,
    deleteSession,
    saveSettings,
    updateTemplateSettings,
    formatCertNumber,
    nextSequence,
    saveCert,
    updateCert,
    deleteCert
  }
})
