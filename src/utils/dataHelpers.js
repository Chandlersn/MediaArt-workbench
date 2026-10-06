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

/**
 * 构造「从业务一键沉淀为知识」的跳转地址。
 *
 * 知识产生在现场（刚排完一个故障、刚做完一次复盘），但入口在知识库深处；
 * 详情页调用本函数即可带着业务对象跳进知识表单，用户补一句标题就能存。
 *
 * @param {'project'|'player'|'org'} linkType 关联对象类型（与知识库 links 的 type 对齐）
 * @param {{id: string, name: string}} target 业务对象
 * @param {string} [type] 知识分类（guide/troubleshoot/case/tip/reference），默认 case（案例）
 * @returns {object} 可直接传给 router.push 的 location
 */
export const knowledgeSedimentRoute = (linkType, target, type = 'case') => ({
  path: '/knowledge/new',
  query: {
    type,
    linkType,
    linkId: String(target?.id ?? ''),
    linkName: target?.name || '',
    // 标题前缀带到表单，用户只需补后半句；不覆盖用户已改动的输入（表单只在新建时读一次）
    title: target?.name ? `${target.name} - ` : ''
  }
})

