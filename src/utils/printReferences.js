/** Print logs before session tracking contain certificate numbers as strings. */
export function parsePrintReferences(raw) {
  let values = raw
  if (typeof values === 'string') {
    try { values = JSON.parse(values) } catch { return [] }
  }
  if (!Array.isArray(values)) return []
  return values.flatMap(value => {
    if (typeof value === 'string' || typeof value === 'number') {
      const number = String(value)
      return number.trim() ? [number] : []
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) return []
    if (typeof value.certNumber !== 'string' && typeof value.certNumber !== 'number') return []
    const reference = { certNumber: String(value.certNumber) }
    if (!reference.certNumber.trim()) return []
    // An absent session remains unknown; never infer it from the current batch.
    if (value.sessionId !== undefined && value.sessionId !== null) {
      reference.sessionId = String(value.sessionId)
    }
    return [reference]
  })
}

export const printReferenceNumber = reference =>
  typeof reference === 'object' ? reference.certNumber : String(reference)

export const printReferenceKey = reference => JSON.stringify([
  printReferenceNumber(reference),
  typeof reference === 'object' ? (reference.sessionId ?? null) : null
])

export function indexPrintReferences(logs) {
  const index = Object.create(null)
  for (const log of logs) {
    for (const reference of parsePrintReferences(log.ref_ids)) {
      const key = printReferenceKey(reference)
      const entry = index[key] || (index[key] = { count: 0, last: '', title: '' })
      entry.count++
      if (String(log.printed_at || '') > entry.last) {
        entry.last = log.printed_at
        entry.title = log.title
      }
    }
  }
  return index
}
