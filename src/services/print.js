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

/** 批量生成可打印 HTML（certNumbers: [{certNumber, sessionId}]） */
export function generatePrint(payload) {
  return post('/api/print/generate', payload)
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
