/**
 * 打印体系 API 封装（对应 server/print/routes.py 一期接口）
 *
 * - 字段目录来自 certificates 表实际列 + 中文标签（后端派生，前端不自持清单）
 * - 底图上传返回像素尺寸 + 建议纸张（A4/A3 比例相同，尺寸由用户确认）
 * - 生成返回整份 HTML（含 N 页），前端开新窗预览 → 浏览器打印 / 另存 PDF
 * - 归档 + 留痕由后端写 print_logs，打印记录页可回看归档件
 */
import { get, post, fetchWithAuth } from './http.js'

/** 字段目录 + 纸张规格 */
export function fetchFieldCatalog() {
  return get('/api/print/fields')
}

/** 上传底图：FormData，返回 { background, pageWidth, pageHeight, suggestPageSize } */
export async function uploadBackground(file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetchWithAuth('/api/print/background', { method: 'POST', body: fd })
  const data = await res.json()
  if (!data.success) throw new Error(data.message || '底图上传失败')
  return data
}

/** 按本次模板和证书范围检查，返回逐证书问题及本次检查凭证。 */
export function validatePrint(payload) {
  return post('/api/print/validate', payload)
}

/** 单份实际排版预览，复用本批检查结果；不生成打印记录。 */
export function previewPrint(payload) {
  return post('/api/print/preview', payload)
}

/** 批量生成；保留 409 状态，便于界面重新检查已变化的证书或模板。 */
export async function generatePrint(payload) {
  const response = await fetchWithAuth('/api/print/generate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  })
  const result = await response.json()
  if (!response.ok) {
    const error = new Error(result.message || `生成失败 (${response.status})`)
    error.status = response.status
    throw error
  }
  return result
}

/** 生成即归档 + 写留痕（后端已落 print_logs，这里只管提交） */
export function archivePrint(payload) {
  return post('/api/print/archive', payload)
}

/** 打印记录列表 */
export function fetchPrintLogs(docType = '') {
  const q = docType ? `?docType=${encodeURIComponent(docType)}` : ''
  return get(`/api/print/logs${q}`)
}

/** 删除一条打印留痕（后端会连带清理其归档件） */
export async function deletePrintLog(logId) {
  const res = await fetchWithAuth(`/api/print/logs/${encodeURIComponent(logId)}`, { method: 'DELETE' })
  const data = await res.json()
  if (!data.success) throw new Error(data.message || '删除失败')
  return data
}

/** 字体清单：{ system: [{label, value}], uploaded: [{name, file, url}] } */
export function fetchFonts() {
  return get('/api/print/fonts')
}

/** 上传字体文件（TTF/OTF/WOFF/WOFF2），返回 { font: {name, file, url} } */
export async function uploadFont(file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetchWithAuth('/api/print/font', { method: 'POST', body: fd })
  const data = await res.json()
  if (!data.success) throw new Error(data.message || '字体上传失败')
  return data
}

/** 删除上传的字体（按 name，即 @font-face family 名） */
export function deleteFont(name) {
  return post('/api/print/font/delete', { name })
}

/** 取回归档文档（HTML 字符串） */
export function fetchPrintDoc(logId) {
  return get(`/api/print/doc/${encodeURIComponent(logId)}`)
}

/** 在新窗口打开生成的 / 归档的 HTML（打印预览统一入口） */
export function openHtmlWindow(html) {
  const win = window.open('', '_blank', 'width=1000,height=720')
  if (!win) throw new Error('浏览器拦截了新窗口，请允许弹出窗口后重试')
  win.document.write(html)
  win.document.close()
  win.focus()
  return win
}
