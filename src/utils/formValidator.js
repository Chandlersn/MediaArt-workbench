export const required = (value, label) => {
  if (!value || !value.toString().trim()) return `${label}不能为空`
  return null
}

export const phone = (value) => {
  if (value && !/^1[3-9]\d{9}$/.test(value)) return '手机号格式不正确'
  return null
}

export const idCard = (value) => {
  if (value && !/^\d{17}[\dXx]$/.test(value)) return '身份证号格式不正确'
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
