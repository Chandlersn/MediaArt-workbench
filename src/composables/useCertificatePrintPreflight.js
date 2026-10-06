import { ref } from 'vue'

/** One print attempt owns its references; only the latest check may authorize it. */
export function useCertificatePrintPreflight(validate) {
  const references = ref([])
  const checking = ref(false)
  const result = ref(null)
  const error = ref('')
  const checkedTemplateId = ref('')
  let sequence = 0

  const invalidate = () => {
    sequence++
    checking.value = false
    result.value = null
    error.value = ''
    checkedTemplateId.value = ''
  }
  const begin = rows => {
    invalidate()
    references.value = rows.map(row => ({ certNumber: row.certNumber, sessionId: row.sessionId || '' }))
  }
  const check = async templateId => {
    const requestId = ++sequence
    checking.value = true
    result.value = null
    error.value = ''
    checkedTemplateId.value = ''
    const certNumbers = references.value.map(row => ({ ...row }))
    try {
      if (!templateId || !certNumbers.length) throw new Error('请选择模板及要打印的证书')
      const response = await validate({ templateId, certNumbers })
      if (requestId !== sequence) return null
      if (!response?.success) throw new Error(response?.message || '检查失败，请重试')
      if (!Array.isArray(response.issues) || typeof response.canGenerate !== 'boolean' || !response.validationToken) {
        throw new Error('检查结果不完整，请重试')
      }
      result.value = response
      checkedTemplateId.value = templateId
      return response
    } catch (err) {
      if (requestId === sequence) error.value = err.message || '检查失败，请重试'
      return null
    } finally {
      if (requestId === sequence) checking.value = false
    }
  }
  return { references, checking, result, error, checkedTemplateId, begin, invalidate, check }
}
