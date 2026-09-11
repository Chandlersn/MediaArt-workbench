/**
 * 证书台账导出引擎（浏览器端，依赖 SheetJS / xlsx）
 *
 * 目标：以系统内的证书事实数据为源，**反向生成**与参照台账完全同构的工作簿，
 * 使日常只需在工作台「点击/填写」，即可一键导出可直接用于打包与邮寄的台账表。
 *
 * 工作簿结构（逐层对标参照文件）：
 *   ① 打包总览            —— 12 列，每家收件机构一行 + 「合计」行
 *   ② 各校区奖项统计      —— 15 列，收件机构×选送校区 拆解省赛/国赛奖项 + 「合计」行
 *   ④ 作品名称待补清单    —— 9 列，缺作品名的证书列表（用于补录）
 *   NN-收件机构           —— 每个收件机构一张分表：
 *        第1行 标题（合并 A:L）、第2行 统计副标题（合并 A:L）
 *        一、按选送校区小计（同包裹内请按此分叠）
 *        二、逐人明细清单（按 赛事阶段 → 证书编号 升序 排序）
 *
 * 注意：省赛/国赛在 ② 中列数不对称——省赛只有 特金/金/银/铜 + 小计（无退赛列），
 *       国赛为 特金/金/银/铜/退赛 + 小计。导出严格保持该列布局。
 */
import * as XLSX from 'xlsx'

/** 赛事阶段排序：参照台账中明细按该顺序排列（省赛在前，国赛在后） */
export const ROUND_ORDER = ['省级展演', '全国展演']

const AWARD_KEYS = ['特金奖', '金奖', '银奖', '铜奖', '退赛']

/** 全角空格（U+3000）：参照台账在字段间隔统一使用 */
const SP = '\u3000'

const num = (v) => (typeof v === 'number' ? v : Number(v) || 0)

const roundIndex = (r) => {
  const i = ROUND_ORDER.indexOf(r)
  return i === -1 ? ROUND_ORDER.length : i
}

/** 明细排序：赛事阶段（省赛→国赛）优先，其次证书编号升序 */
function sortDetail(list) {
  return [...list].sort((a, b) => {
    const dr = roundIndex(a.certRound) - roundIndex(b.certRound)
    if (dr !== 0) return dr
    return String(a.certNumber || '').localeCompare(String(b.certNumber || ''), 'zh-Hans-CN')
  })
}

/** 汇总奖项构成 */
function awardCounts(list) {
  const out = { 特金奖: 0, 金奖: 0, 银奖: 0, 铜奖: 0, 退赛: 0 }
  for (const c of list) {
    const a = c.award
    if (a && out[a] !== undefined) out[a] += 1
  }
  return out
}

/** 收件机构名兜底：未指定时沿用选送机构名 */
const receivingOf = (c) => (c.receivingOrg || c.orgName || '未归类').trim() || '未归类'

/** 按收件机构分组（分组键即导出的分表维度） */
export function groupByReceivingOrg(certs) {
  const map = new Map()
  for (const c of Array.isArray(certs) ? certs : []) {
    const key = receivingOf(c)
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(c)
  }
  return map
}

/** 工作表命名：01-A剧团；清理 Excel 非法字符并截断至 31 字符 */
function sheetNameFor(index, orgName) {
  const safe = String(orgName).replace(/[\\/?*\x5b\x5d:]/g, '·').slice(0, 28)
  return `${String(index + 1).padStart(2, '0')}-${safe}`
}

/**
 * 构建单个收件机构分表的数据区（二维数组）
 */
function buildOrgSheet(orgName, certs) {
  const total = certs.length
  const provList = certs.filter(c => c.certRound === '省级展演')
  const natList = certs.filter(c => c.certRound === '全国展演')
  const awards = awardCounts(certs)

  // 校区拆解
  const campusMap = new Map()
  for (const c of certs) {
    const k = (c.orgName || '未注明').trim() || '未注明'
    if (!campusMap.has(k)) campusMap.set(k, [])
    campusMap.get(k).push(c)
  }
  const campuses = Array.from(campusMap.entries()).sort((a, b) => b[1].length - a[1].length)

  const rows = []
  rows.push([`${orgName} — 证书打包清单`])

  const parts = AWARD_KEYS.slice(0, 4).filter(a => awards[a] > 0).map(a => `${a} ${awards[a]}`)
  // eslint-disable-next-line no-irregular-whitespace
  const awardPart = parts.length ? `　|　奖项构成：${parts.join(SP)}` : ''
  rows.push([
    `收件/打包单位：${orgName}${SP}|${SP}证书合计 ${total} 张（省赛 ${provList.length} + 国赛 ${natList.length}）${awardPart}${SP}|${SP}含 ${campuses.length} 个选送校区`
  ])
  rows.push([])

  const titleOneRow = rows.length
  rows.push(['一、按选送校区小计（同包裹内请按此分叠）'])
  rows.push(['序号', '选送机构（校区）', '特金奖', '金奖', '银奖', '铜奖', '退赛', '小计'])
  campuses.forEach(([campus, list], i) => {
    const a = awardCounts(list)
    rows.push([String(i + 1), campus, num(a['特金奖']), num(a['金奖']), num(a['银奖']), num(a['铜奖']), num(a['退赛']), list.length])
  })
  rows.push([
    '小计',
    `${campuses.length} 个校区`,
    num(awards['特金奖']), num(awards['金奖']), num(awards['银奖']), num(awards['铜奖']), num(awards['退赛']),
    total
  ])
  rows.push([])
  rows.push([])

  const titleTwoRow = rows.length
  rows.push(['二、逐人明细清单（按 赛事阶段 → 证书编号 升序 排序）'])
  rows.push(['序号', '赛事阶段', '证书编号', '选手姓名', '组别', '奖项', '作品名称', '指导老师', '选送机构（校区）', '语种', '晋级情况', '打包核对'])
  sortDetail(certs).forEach((c, i) => {
    rows.push([
      String(i + 1),
      c.certRound || '',
      c.certNumber || '',
      c.playerName || '',
      c.groupName || '',
      c.award || '',
      c.workName || '',
      c.instructor || '',
      c.orgName || '',
      c.language || '',
      c.promotion || '',
      c.packed === '待核对' ? '' : (c.packed || '')
    ])
  })

  return { rows, titleOneRow, titleTwoRow }
}

/**
 * 构建三个汇总表
 */
function buildOverviewSheet(certs, opts) {
  const groups = Array.from(groupByReceivingOrg(certs).entries())
  // 分表顺序：默认按收件机构名称（与参照台账 01–102 的编号次序一致）；
  // 也可 opts.sortBy='certNumber' 改为按各家最小证书编号升序。
  // 沿用导入时的原始顺序：证书自带 sourceSheet（形如 "01-A剧团"），
  // 用其数字前缀排序即可让「再导出」与源台账完全同序；无来源的（系统内新增）退化为按名称排序。
  const sourceOrder = (list) => {
    let min = Infinity
    for (const c of list) {
      const m = /^(\d+)-/.exec(String(c.sourceSheet || ''))
      if (m) min = Math.min(min, Number(m[1]))
    }
    return min
  }
  const orderCache = new Map(groups.map(([org, list]) => [org, sourceOrder(list)]))

  if (opts.sortBy === 'certNumber') {
    groups.sort((a, b) => {
      const minA = sortDetail(a[1])[0]?.certNumber || ''
      const minB = sortDetail(b[1])[0]?.certNumber || ''
      return String(minA).localeCompare(String(minB), 'zh-Hans-CN')
    })
  } else {
    groups.sort((a, b) => {
      const ka = orderCache.get(a[0])
      const kb = orderCache.get(b[0])
      if (ka !== kb) {
        if (ka === Infinity) return 1
        if (kb === Infinity) return -1
        return ka - kb
      }
      return String(a[0]).localeCompare(String(b[0]), 'zh-Hans-CN')
    })
  }

  const rows = []
  rows.push([`${opts.titlePrefix} · 证书打包总览（按收件机构）`])
  let grandProv = 0
  let grandNat = 0
  for (const [, list] of groups) {
    grandProv += list.filter(c => c.certRound === '省级展演').length
    grandNat += list.filter(c => c.certRound === '全国展演').length
  }
  const orderText = opts.sortBy === 'certNumber' ? '按证书编号升序' : '按收件机构名称排序'
  rows.push([`省赛 ${grandProv} 条 + 国赛 ${grandNat} 条|${SP}收件机构 ${groups.length} 家｜工作表顺序：${orderText}`])
  rows.push(['序号', '收件机构\n（负责单位/打包单位）', '特金奖', '金奖', '银奖', '铜奖', '退赛', '证书合计', '其中省赛', '其中国赛', '含校区数', '已打包\n(打勾)'])

  const sums = { t: 0, j: 0, y: 0, b: 0, w: 0, total: 0, prov: 0, nat: 0, campuses: 0 }
  groups.forEach(([org, list], i) => {
    const a = awardCounts(list)
    const prov = list.filter(c => c.certRound === '省级展演').length
    const nat = list.filter(c => c.certRound === '全国展演').length
    const campusCount = new Set(list.map(c => (c.orgName || '').trim())).size
    rows.push([
      String(i + 1), org,
      num(a['特金奖']), num(a['金奖']), num(a['银奖']), num(a['铜奖']), num(a['退赛']),
      list.length, prov, nat, campusCount, ''
    ])
    sums.t += a['特金奖']; sums.j += a['金奖']; sums.y += a['银奖']; sums.b += a['铜奖']; sums.w += a['退赛']
    sums.total += list.length; sums.prov += prov; sums.nat += nat; sums.campuses += campusCount
  })
  const totalCampuses = new Set(groups.flatMap(([, list]) => list.map(c => `${receivingOf(c)}||${(c.orgName || '').trim()}`))).size
  rows.push([
    '合计', `${groups.length} 家收件机构`,
    num(sums.t), num(sums.j), num(sums.y), num(sums.b), num(sums.w),
    num(sums.total), num(sums.prov), num(sums.nat), totalCampuses, ''
  ])

  return { rows, groups }
}

function buildCampusSheet(certs, opts) {
  const rows = []
  rows.push([`${opts.titlePrefix} · 各选送机构（校区）奖项统计明细`])
  rows.push(['口径：同一「收件机构（负责单位）」下若含多个校区，证书统一打包寄至收件机构，本表用于核对每个校区各出了多少张证书。'])
  rows.push([
    '序号', '收件机构\n（负责单位）', '选送机构\n（校区/学校）',
    '省赛\n特金奖', '省赛\n金奖', '省赛\n银奖', '省赛\n铜奖', '省赛\n小计',
    '国赛\n特金奖', '国赛\n金奖', '国赛\n银奖', '国赛\n铜奖', '国赛\n退赛', '国赛\n小计',
    '证书合计'
  ])

  const pairs = new Map()
  for (const c of certs) {
    const recv = receivingOf(c)
    const campus = (c.orgName || '未注明').trim() || '未注明'
    const key = `${recv}||${campus}`
    if (!pairs.has(key)) pairs.set(key, { recv, campus, list: [] })
    pairs.get(key).list.push(c)
  }
  const list = Array.from(pairs.values()).sort((a, b) => b.list.length - a.list.length)

  const sum = { p1: 0, p2: 0, p3: 0, p4: 0, ps: 0, n1: 0, n2: 0, n3: 0, n4: 0, n5: 0, ns: 0, total: 0 }
  list.forEach((p, i) => {
    const pv = p.list.filter(c => c.certRound === '省级展演')
    const nt = p.list.filter(c => c.certRound === '全国展演')
    const pa = awardCounts(pv)
    const na = awardCounts(nt)
    rows.push([
      String(i + 1), p.recv, p.campus,
      num(pa['特金奖']), num(pa['金奖']), num(pa['银奖']), num(pa['铜奖']), pv.length,
      num(na['特金奖']), num(na['金奖']), num(na['银奖']), num(na['铜奖']), num(na['退赛']), nt.length,
      p.list.length
    ])
    sum.p1 += pa['特金奖']; sum.p2 += pa['金奖']; sum.p3 += pa['银奖']; sum.p4 += pa['铜奖']; sum.ps += pv.length
    sum.n1 += na['特金奖']; sum.n2 += na['金奖']; sum.n3 += na['银奖']; sum.n4 += na['铜奖']; sum.n5 += na['退赛']; sum.ns += nt.length
    sum.total += p.list.length
  })
  rows.push([
    '合计', '', `${list.length} 个校区`,
    num(sum.p1), num(sum.p2), num(sum.p3), num(sum.p4), num(sum.ps),
    num(sum.n1), num(sum.n2), num(sum.n3), num(sum.n4), num(sum.n5), num(sum.ns),
    num(sum.total)
  ])

  return rows
}

function buildMissingSheet(certs, opts) {
  const missing = sortDetail(certs.filter(c => c.missingWorkName === 1 || c.missingWorkName === true || !c.workName))
  const rows = []
  rows.push([`${opts.titlePrefix} · 作品名称待补清单`])
  rows.push([`共 ${missing.length} 条记录缺少作品名称。请先在最右侧「补录作品名称」列填写后再回填至系统；未补录的证书在印制时无法带出作品名。`])
  rows.push(['序号', '收件机构\n（负责单位）', '选送校区', '证书编码', '选手姓名', '组别', '奖项', '指导老师', '补录作品名称\n（空白待填）'])
  missing.forEach((c, i) => {
    rows.push([
      String(i + 1),
      receivingOf(c),
      (c.orgName || '').trim(),
      c.certNumber || '',
      c.playerName || '',
      c.groupName || '',
      c.award || '',
      c.instructor || '',
      ''
    ])
  })
  return rows
}

/**
 * 构建完整工作簿（不落盘，便于预览/测试）
 * @param {Array} certificates 证书事实数据
 * @param {object} opts { titlePrefix, includeSummaries }
 * @returns {{workbook: object, overview: Array, sheetCount: number}}
 */
export function buildCertificateWorkbook(certificates, opts = {}) {
  const options = {
    titlePrefix: opts.titlePrefix || '证书',
    includeSummaries: opts.includeSummaries !== false,
    sortBy: opts.sortBy === 'certNumber' ? 'certNumber' : 'name'
  }
  const wb = XLSX.utils.book_new()

  if (options.includeSummaries) {
    const { rows: overview, groups } = buildOverviewSheet(certificates, options)
    const ws1 = XLSX.utils.aoa_to_sheet(overview)
    ws1['!merges'] = [
      { s: { c: 0, r: 0 }, e: { c: 11, r: 0 } },
      { s: { c: 0, r: 1 }, e: { c: 11, r: 1 } }
    ]
    XLSX.utils.book_append_sheet(wb, ws1, '① 打包总览')

    const campus = buildCampusSheet(certificates, options)
    const ws2 = XLSX.utils.aoa_to_sheet(campus)
    ws2['!merges'] = [
      { s: { c: 0, r: 0 }, e: { c: 14, r: 0 } },
      { s: { c: 0, r: 1 }, e: { c: 14, r: 1 } }
    ]
    XLSX.utils.book_append_sheet(wb, ws2, '② 各校区奖项统计')

    const missing = buildMissingSheet(certificates, options)
    const ws4 = XLSX.utils.aoa_to_sheet(missing)
    ws4['!merges'] = [
      { s: { c: 0, r: 0 }, e: { c: 8, r: 0 } },
      { s: { c: 0, r: 1 }, e: { c: 8, r: 1 } }
    ]
    XLSX.utils.book_append_sheet(wb, ws4, '④ 作品名称待补清单')

    groups.forEach(([org, list], i) => {
      const { rows, titleOneRow, titleTwoRow } = buildOrgSheet(org, list)
      const ws = XLSX.utils.aoa_to_sheet(rows)
      ws['!merges'] = [
        { s: { c: 0, r: 0 }, e: { c: 11, r: 0 } },
        { s: { c: 0, r: 1 }, e: { c: 11, r: 1 } },
        { s: { c: 0, r: titleOneRow }, e: { c: 5, r: titleOneRow } },
        { s: { c: 0, r: titleTwoRow }, e: { c: 5, r: titleTwoRow } }
      ]
      XLSX.utils.book_append_sheet(wb, ws, sheetNameFor(i, org))
    })
  } else {
    const groups = Array.from(groupByReceivingOrg(certificates).entries())
    groups.forEach(([org, list], i) => {
      const { rows, titleOneRow, titleTwoRow } = buildOrgSheet(org, list)
      const ws = XLSX.utils.aoa_to_sheet(rows)
      ws['!merges'] = [
        { s: { c: 0, r: 0 }, e: { c: 11, r: 0 } },
        { s: { c: 0, r: 1 }, e: { c: 11, r: 1 } },
        { s: { c: 0, r: titleOneRow }, e: { c: 5, r: titleOneRow } },
        { s: { c: 0, r: titleTwoRow }, e: { c: 5, r: titleTwoRow } }
      ]
      XLSX.utils.book_append_sheet(wb, ws, sheetNameFor(i, org))
    })
  }

  return {
    workbook: wb,
    sheetCount: wb.SheetNames.length,
    certCount: certificates.length
  }
}

/**
 * 导出证书台账为 xlsx 并触发浏览器下载
 * @param {Array} certificates 证书事实数据
 * @param {object} opts { fileName, titlePrefix, includeSummaries }
 */
export function exportCertificateLedger(certificates, opts = {}) {
  const { workbook, sheetCount, certCount } = buildCertificateWorkbook(certificates, opts)
  const fileName = opts.fileName || `证书打包分表（按收件机构）_${new Date().toISOString().slice(0, 10)}.xlsx`
  XLSX.writeFile(workbook, fileName, { bookType: 'xlsx', compression: true })
  return { fileName, sheetCount, certCount }
}
