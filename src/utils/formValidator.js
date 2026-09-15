export const required = (value, label) => {
  if (!value || !value.toString().trim()) return `${label}不能为空`
  return null
}

// 电话：手机号 / 座机（含区号）/ 400·800 服务号；允许空格、横线、括号分隔
// ⚠️ 规则需与后端 server/utils/validators.py 保持一致
const PHONE_SEP = /[\s\-()（）]/g

export const normalizePhone = (value) => (value ?? '').toString().replace(PHONE_SEP, '').trim()

export const phone = (value) => {
  const raw = (value ?? '').toString().trim()
  if (!raw) return null
  const n = normalizePhone(raw)
  if (/^1[3-9]\d{9}$/.test(n)) return null          // 手机号
  if (/^0\d{9,11}$/.test(n)) return null            // 座机（区号 + 号码）
  if (/^[48]00\d{7}$/.test(n)) return null          // 400 / 800
  return '电话格式不正确（手机号 11 位，或座机含区号，如 010-88886666）'
}

// 身份证 18 位：格式 + 出生日期 + 校验位（GB 11643-1999）
const ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
const ID_CHECK = '10X98765432'

export const idCard = (value) => {
  const v = (value ?? '').toString().trim().toUpperCase()
  if (!v) return null
  if (!/^\d{17}[\dX]$/.test(v)) return '身份证号应为 18 位（末位可为 X）'
  const y = +v.slice(6, 10)
  const m = +v.slice(10, 12)
  const d = +v.slice(12, 14)
  const date = new Date(y, m - 1, d)
  const validDate = date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d
  if (!validDate || y < 1900 || date.getTime() > Date.now()) return '身份证号中的出生日期无效'
  let sum = 0
  for (let i = 0; i < 17; i++) sum += +v[i] * ID_WEIGHTS[i]
  if (ID_CHECK[sum % 11] !== v[17]) return '身份证号校验位不正确'
  return null
}

export const email = (value) => {
  if (value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return '邮箱格式不正确'
  return null
}

export const positiveNumber = (value, label) => {
  if (value && (isNaN(Number(value)) || Number(value) <= 0)) return `${label}必须为正数`
  return null
}

export const validate = (rules) => {
  const errors = {}
  let valid = true
  for (const [field, fieldRules] of Object.entries(rules)) {
    for (const rule of fieldRules) {
      const error = rule()
      if (error) {
        errors[field] = error
        valid = false
        break
      }
    }
  }
  return { valid, errors }
}
