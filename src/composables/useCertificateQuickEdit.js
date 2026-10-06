import { ref } from 'vue'
import { printReferenceKey } from '../utils/printReferences.js'

const fields = new Set(['workName', 'instructor'])
const reference = record => ({ certNumber: record.certNumber, sessionId: record.sessionId || '' })
const key = record => printReferenceKey(reference(record))

/** Freeze the visible order so saving a missing value cannot skip the next row. */
export function useCertificateQuickEdit({ canEdit, records, update }) {
  const draft = ref(null)
  const busy = ref(false)
  const error = ref('')
  let queue = []

  const open = (record, column) => {
    draft.value = { ...reference(record), column, value: String(record[column] ?? ''), original: String(record[column] ?? '') }
    error.value = ''
  }
  const begin = (record, column, visibleRows) => {
    if (!canEdit() || busy.value || draft.value || !fields.has(column)) return false
    queue = visibleRows.map(reference)
    open(record, column)
    return true
  }
  const cancel = () => {
    if (busy.value) return
    draft.value = null
    error.value = ''
    queue = []
  }
  const save = async (advance = false) => {
    if (!draft.value || busy.value || !canEdit()) return false
    const current = { ...draft.value }
    busy.value = true
    error.value = ''
    try {
      if (!records().some(record => key(record) === key(current))) throw new Error('证书已不存在，请取消后刷新')
      if (current.value !== current.original) {
        const patch = { [current.column]: current.value }
        if (current.column === 'workName') patch.missingWorkName = current.value.trim() ? 0 : 1
        const saved = await update(current.certNumber, patch, current.sessionId)
        if (saved === null) throw new Error('证书已不存在，未保存修改')
      }
      draft.value = null
      if (advance) {
        const position = queue.findIndex(record => key(record) === key(current))
        for (const candidate of queue.slice(position + 1)) {
          const row = records().find(record => key(record) === key(candidate))
          if (row) { open(row, current.column); break }
        }
      }
      return true
    } catch (err) {
      error.value = err.message || '保存失败，请重试'
      return false
    } finally {
      busy.value = false
    }
  }
  return { draft, busy, error, begin, cancel, save }
}
