export const parseOrgIds = (orgIds) => {
  if (Array.isArray(orgIds)) return orgIds
  if (typeof orgIds === 'string') {
    try {
      const parsed = JSON.parse(orgIds)
      if (Array.isArray(parsed)) return parsed
    } catch {
      // 非 JSON 字符串，按"解析失败"处理，返回空数组
    }
  }
  return []
}
