/**
 * 证书 xlsx 导入服务（浏览器端，依赖 SheetJS / xlsx）
 *
 * 源文件结构约定（已用实物逐层核对）：
 * - 工作簿 105 个 sheet：3 个汇总表（① 打包总览 / ② 各校区奖项统计 / ④ 作品名称待补清单）
 *   与 102 个收件机构分表（命名形如 "01-A剧团"、"84-刘诗昆-汇总"）。
 * - 每个机构分表内含：第 0 行标题（合并 A:L）、第 1 行统计副标题（合并 A:L）、
 *   「一、按选送校区小计」区块、「二、逐人明细清单」区块（表头 12 列）。
 * - 明细表头：序号|赛事阶段|证书编号|选手姓名|组别|奖项|作品名称|指导老师|选送机构（校区）|语种|晋级情况|打包核对
 *
 * 重要坑（曾导致数据丢失，勿回退）：
 * - 赛事阶段有「省级展演」「全国展演」两类。**省赛证书号为「【川】CNRCSOV2026xxxx」，
 *   国赛证书号为「Q1780」「Q2368」这类**。早期版本用“遇到不以【开头即停止”判断明细区结束，
 *   结果在每个分表遇到第一条国赛记录时就 break，1113 条国赛被静默丢弃。
 *   现改为：遍历到表尾，证书号单元格非空即采信，仅跳过空行与重复出现的表头行。
 * - 作品名称存在占位值「（国赛未收录）」，须与真空白一并计入缺作品名。
 * - 打包核对列取值只有两种：空值，或退赛行的「退赛·不出证书」。
 */
import * as XLSX from 'xlsx'

const DETAIL_HEADER = ['序号', '赛事阶段', '证书编号', '选手姓名', '组别', '奖项', '作品名称', '指导老师', '选送机构（校区）', '语种', '晋级情况', '打包核对']

// 国赛占位：作品名称未收录时的统一填充值
const WORK_NAME_PLACEHOLDERS = ['（国赛未收录）', '(国赛未收录)']

const isSummarySheet = (name) => /^[①②③④]/.test(name)
const isWithdrawn = (award) => (award || '').includes('退赛')

/** 表形如 "01-A剧团" / "84-刘诗昆-汇总" → 取收件机构名 */
const receivingOrgFromSheet = (sheetName) => String(sheetName || '').replace(/^\d+-\s*/, '').trim()

/**
 * 解析已读取的工作簿，提取全部证书事实行（含省赛与国赛）
 * @param {object} wb SheetJS workbook
 * @returns {{rows: object[], sheets: number, orgSheets: number}}
 */
function extractFromWorkbook(wb) {
  const rows = []
  let orgSheets = 0

  for (const sheetName of wb.SheetNames) {
    if (isSummarySheet(sheetName)) continue
    orgSheets++

    const ws = wb.Sheets[sheetName]
    if (!ws) continue
    const matrix = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '', raw: false })

    // 定位明细表头行
    let hIdx = -1
    for (let i = 0; i < matrix.length; i++) {
      const r = matrix[i]
      if (r && r[1] === DETAIL_HEADER[1] && r[2] === DETAIL_HEADER[2] && r[3] === DETAIL_HEADER[3]) {
        hIdx = i
        break
      }
    }
    if (hIdx < 0) continue

    const receivingOrg = receivingOrgFromSheet(sheetName)

    // 明细区：一直走到表尾。证书号非空即算一条（兼容【…】与 Q… 两种编号）
    for (let i = hIdx + 1; i < matrix.length; i++) {
      const r = matrix[i]
      if (!r) continue
      const certNumber = String(r[2] ?? '').trim()
      if (!certNumber || certNumber === DETAIL_HEADER[2]) continue // 空行 / 重复表头

      const award = String(r[5] ?? '').trim()
      const rawWorkName = String(r[6] ?? '').trim()
      const workName = WORK_NAME_PLACEHOLDERS.includes(rawWorkName) ? '' : rawWorkName
      const packedRaw = String(r[11] ?? '').trim()

      rows.push({
        certNumber,
        certRound: String(r[1] ?? '').trim(),
        playerName: String(r[3] ?? '').trim(),
        groupName: String(r[4] ?? '').trim(),
        award,
        workName,
        instructor: String(r[7] ?? '').trim(),
        orgName: String(r[8] ?? '').trim(),
        language: String(r[9] ?? '').trim(),
        promotion: String(r[10] ?? '').trim(),
        packed: packedRaw || '待核对',
        // 占位值与真空白都算“缺作品名”
        missingWorkName: workName ? 0 : 1,
        isWithdrawn: isWithdrawn(award) ? 1 : 0,
        receivingOrg: receivingOrg || String(r[8] ?? '').trim(),
        sourceSheet: sheetName,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      })
    }
  }

  return { rows, sheets: wb.SheetNames.length, orgSheets }
}

/**
 * 按证书编号去重（后者覆盖前者），返回去重后的行与重复计数
 */
function dedupByCertNumber(rows) {
  const map = new Map()
  let dup = 0
  for (const row of rows) {
    if (map.has(row.certNumber)) dup++
    map.set(row.certNumber, row)
  }
  return { unique: Array.from(map.values()), dup }
}

/**
 * 解析 xlsx 文件（File 对象），返回预览 + 去重后的证书行
 * @param {File} file
 * @returns {Promise<{preview: object, rows: object[], meta: object}>}
 */
export async function parseCertificateFile(file) {
  const buf = await file.arrayBuffer()
  const wb = XLSX.read(new Uint8Array(buf), { type: 'array' })
  const { rows, sheets, orgSheets } = extractFromWorkbook(wb)
  const { unique, dup } = dedupByCertNumber(rows)

  const byAward = {}
  const byRound = {}
  let missingWorkName = 0
  for (const r of unique) {
    const awardKey = r.award || '未分类'
    byAward[awardKey] = (byAward[awardKey] || 0) + 1
    const roundKey = r.certRound || '未分类'
    byRound[roundKey] = (byRound[roundKey] || 0) + 1
    if (r.missingWorkName) missingWorkName++
  }

  const preview = {
    sheets,
    orgSheets,
    raw: rows.length,
    unique: unique.length,
    dup,
    missingWorkName,
    byAward,
    byRound
  }

  const meta = {
    fileName: file.name,
    fileSize: file.size,
    parsedAt: new Date().toISOString()
  }

  return { preview, rows: unique, meta }
}
