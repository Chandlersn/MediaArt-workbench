// 纯数据 + 纯函数模型层（不依赖 vue/pinia，可独立单测）
// 从 checklist.js 抽出：清单默认模板与 items 字符串→对象的规范化逻辑。
// 关键约束：DEFAULT_CHECKLISTS 的 items 是字符串数组，但运行时全部按
// {text,checked,isCustom} 对象处理，必须由 buildInitialChecklists / normalizeProjectMap
// 在 seeds 与加载时统一转成对象，否则会出现「模板空白 + toggle 崩溃」。

/**
 * 清单工具默认数据定义
 * 5种清单类型：赛前准备、报名登记、赛事执行、成绩管理、赛后总结
 */
export const DEFAULT_CHECKLISTS = {
  startup: {
    label: '赛前准备',
    cards: [
      {
        id: 'startup-1',
        title: '项目立项',
        items: [
          '项目已在系统中创建',
          '项目立项报告已完成',
          '项目预算已审批',
          '项目负责人已确定',
          '项目时间表已制定',
          '项目状态已更新为"进行中"'
        ]
      },
      {
        id: 'startup-2',
        title: '机构对接',
        items: [
          '合作机构已在系统中录入',
          '机构联系人已确认',
          '合作协议已签订',
          '合作机构名单已确定',
          '机构对接人通讯录已建立',
          '机构合作等级已评估',
          '机构资料已收集完整'
        ]
      },
      {
        id: 'startup-3',
        title: '选手招募',
        items: [
          '报名通知已发布',
          '选手已在系统中录入',
          '选手所属机构已关联',
          '选手参赛阶段已设置',
          '选手资料类型已配置',
          '缺资料选手已提醒',
          '选手分组已完成',
          '参赛证/号码牌已制作'
        ]
      },
      {
        id: 'startup-4',
        title: '资料收集',
        items: [
          '资料类型已配置',
          '各阶段资料要求已设置',
          '选手报名表已收集',
          '身份证明已收集',
          '个人照片已收集',
          '其他必填资料已收集'
        ]
      }
    ]
  },
  registration: {
    label: '报名登记',
    cards: [
      {
        id: 'reg-1',
        title: '报名管理',
        items: [
          '报名表模板已设计',
          '报名通道已开通',
          '报名信息已录入系统',
          '报名截止日期已确认',
          '报名人数已统计',
          '报名费用标准已确定'
        ]
      },
      {
        id: 'reg-2',
        title: '资料审核',
        items: [
          '选手身份证明已审核',
          '参赛资格已核实',
          '报名资料完整性已检查',
          '不合格报名已处理',
          '补充资料已通知',
          '审核结果已通知选手'
        ]
      },
      {
        id: 'reg-3',
        title: '缴费确认',
        items: [
          '缴费方式已公布',
          '缴费到账已确认',
          '缴费凭证已收集',
          '退费规则已说明',
          '缴费统计已完成',
          '财务对账已完成'
        ]
      },
      {
        id: 'reg-4',
        title: '参赛确认',
        items: [
          '参赛名单已确认',
          '参赛号已分配',
          '参赛须知已发送',
          '选手分组已公布',
          '比赛日程已通知',
          '选手签到方式已确定'
        ]
      }
    ]
  },
  execution: {
    label: '赛事执行',
    cards: [
      {
        id: 'exec-1',
        title: '赛前准备',
        items: [
          '活动场地已预订',
          '场地布置方案已确定',
          '舞台搭建已完成',
          '灯光音响已调试',
          '座位安排已完成',
          '安检设备已就位',
          '医疗急救点已设置',
          '安保人员已安排',
          '志愿者已培训',
          '工作证/胸牌已制作'
        ]
      },
      {
        id: 'exec-2',
        title: '比赛执行',
        items: [
          '工作人员已到岗',
          '参赛人员已签到',
          '评委已邀请并确认',
          '评分表已准备',
          '比赛流程已确认',
          '主持人已确定',
          '背景音乐已准备',
          '拍摄设备已就位',
          '直播设备已调试（如需）',
          '应急预案已准备',
          '成绩统计表已准备',
          '奖品/证书已准备'
        ]
      },
      {
        id: 'exec-3',
        title: '宣发执行',
        items: [
          '宣发方案已制定',
          '海报/横幅已制作',
          '媒体邀请函已发送',
          '新闻通稿已准备',
          '社交媒体已发布',
          '现场拍照已安排',
          '视频录制已安排',
          '活动照片已上传系统'
        ]
      },
      {
        id: 'exec-4',
        title: '财务执行',
        items: [
          '预算已审批',
          '收入已录入系统',
          '支出已录入系统',
          '发票已收集',
          '报销流程已完成',
          '财务报表已生成'
        ]
      }
    ]
  },
  scoring: {
    label: '成绩管理',
    cards: [
      {
        id: 'score-1',
        title: '评分管理',
        items: [
          '评分标准已制定',
          '评分表已分发',
          '评委评分已收集',
          '评分数据已录入',
          '异常评分已复核',
          '最终得分已计算'
        ]
      },
      {
        id: 'score-2',
        title: '统计汇总',
        items: [
          '成绩已统计完成',
          '排名已生成',
          '获奖名单已确定',
          '成绩报表已导出',
          '成绩数据已备份',
          '统计图表已制作'
        ]
      },
      {
        id: 'score-3',
        title: '成绩公示',
        items: [
          '成绩公示方案已确定',
          '成绩已公示',
          '异议处理机制已建立',
          '成绩异议已处理',
          '最终成绩已确认',
          '选手阶段已更新'
        ]
      },
      {
        id: 'score-4',
        title: '奖项发放',
        items: [
          '获奖证书已制作',
          '奖品已准备',
          '奖金已审批',
          '证书/奖品已发放',
          '获奖名单已公布',
          '获奖通知已发送'
        ]
      }
    ]
  },
  summary: {
    label: '赛后总结',
    cards: [
      {
        id: 'summary-1',
        title: '总结报告',
        items: [
          '项目总结报告已完成',
          '活动效果评估已完成',
          '数据分析报告已完成',
          '问题汇总已整理',
          '改进建议已记录',
          '总结会议已召开'
        ]
      },
      {
        id: 'summary-2',
        title: '资料归档',
        items: [
          '财务资料已整理',
          '合同资料已归档',
          '人员资料已整理',
          '宣传资料已保存',
          '影像资料已备份',
          '选手档案已归档',
          '归档目录已制作',
          '电子档案已备份',
          '项目状态已更新为"已结束"'
        ]
      },
      {
        id: 'summary-3',
        title: '财务结算',
        items: [
          '所有收入已入账',
          '所有支出已结算',
          '发票已全部收集',
          '财务报表已生成',
          '利润核算已完成',
          '税务申报已完成',
          '财务档案已归档'
        ]
      },
      {
        id: 'summary-4',
        title: '经验整理',
        items: [
          '项目经验总结已记录',
          '问题教训已整理',
          '感谢信已发送',
          '合作机构反馈已收集',
          '选手满意度调查已完成',
          '下次活动建议已记录'
        ]
      }
    ]
  }
}

/** 当前视图未选中具体项目时使用的键 */
export const GLOBAL_KEY = '__global__'

/** 已知的默认 Tab key，用于识别旧版「按 tab 平铺」的清单数据 */
export const DEFAULT_TAB_KEYS = Object.keys(DEFAULT_CHECKLISTS)

/**
 * 把单个清单项规范为 { text, checked, isCustom } 对象。
 * DEFAULT_CHECKLISTS 里 items 是字符串数组，运行时所有逻辑
 * （toggleItem / getProgress / 视图渲染 item.text 等）都按对象处理，
 * 因此必须在 seeds 与加载时统一转成对象，否则会出现「模板空白 +
 * Cannot create property 'checked' on string」的崩溃。
 */
export function normalizeChecklistItem(it) {
  if (typeof it === 'string') {
    return { text: it, checked: false, isCustom: false }
  }
  if (it && typeof it === 'object') {
    return {
      text: typeof it.text === 'string'
        ? it.text
        : (it.text != null ? String(it.text) : ''),
      checked: !!it.checked,
      isCustom: !!it.isCustom
    }
  }
  return { text: it != null ? String(it) : '', checked: false, isCustom: false }
}

function normalizeCard(card) {
  if (!card || typeof card !== 'object') return { id: '', title: '', items: [] }
  return {
    id: card.id || '',
    title: card.title || '',
    items: Array.isArray(card.items) ? card.items.map(normalizeChecklistItem) : []
  }
}

function normalizeTab(tab) {
  if (!tab || typeof tab !== 'object') return { label: '', cards: [] }
  return {
    label: typeof tab.label === 'string' ? tab.label : '',
    cards: Array.isArray(tab.cards) ? tab.cards.map(normalizeCard) : []
  }
}

/** 递归规范化整个按项目组织的清单结构，确保 items 都是对象 */
export function normalizeProjectMap(map) {
  const out = {}
  if (map && typeof map === 'object' && !Array.isArray(map)) {
    for (const [pk, tabs] of Object.entries(map)) {
      if (!tabs || typeof tabs !== 'object' || Array.isArray(tabs)) continue
      out[pk] = {}
      for (const [tk, tab] of Object.entries(tabs)) {
        out[pk][tk] = normalizeTab(tab)
      }
    }
  }
  return out
}

/**
 * 深拷贝默认清单结构（避免多个项目共享同一份对象引用），
 * 并把 items 统一规范为 { text, checked, isCustom } 对象。
 */
export function buildInitialChecklists() {
  const base = JSON.parse(JSON.stringify(DEFAULT_CHECKLISTS))
  for (const tab of Object.values(base)) {
    tab.cards = (tab.cards || []).map(normalizeCard)
  }
  return base
}