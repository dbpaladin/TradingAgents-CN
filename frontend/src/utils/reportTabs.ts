export interface ReportTabDefinition {
  key: string
  title: string
  duplicates?: string[]
}

export interface ReportTabItem {
  key: string
  title: string
  content: any
}

const REPORT_TAB_DEFINITIONS: ReportTabDefinition[] = [
  { key: 'final_trade_decision', title: '🎯 最终交易决策-投资组合经理' },
  { key: 'trader_investment_plan', title: '💼 交易员计划' },
  { key: 'risk_management_decision', title: '👔 投资组合经理', duplicates: ['final_trade_decision'] },
  { key: 'research_team_decision', title: '🔬 研究经理决策' },
  { key: 'market_report', title: '📈 市场技术分析' },
  { key: 'a_share_sentiment_report', title: '🔥 A股盘面情绪' },
  { key: 'fund_flow_report', title: '💸 A股资金面' },
  { key: 'theme_rotation_report', title: '🧭 A股题材轮动' },
  { key: 'institutional_theme_report', title: '🏦 机构布局题材' },
  { key: 'sentiment_report', title: '💬 公共舆情分析' },
  { key: 'news_report', title: '📰 新闻事件分析' },
  { key: 'fundamentals_report', title: '💰 基本面分析' },
  { key: 'bull_researcher', title: '🐂 多头研究员' },
  { key: 'bear_researcher', title: '🐻 空头研究员' },
  { key: 'risky_analyst', title: '⚡ 激进分析师' },
  { key: 'safe_analyst', title: '🛡️ 保守分析师' },
  { key: 'neutral_analyst', title: '⚖️ 中性分析师' },
  { key: 'investment_plan', title: '📋 投资建议', duplicates: ['final_trade_decision'] },
  { key: 'investment_debate_state', title: '🔬 研究团队决策（旧）', duplicates: ['research_team_decision'] },
  { key: 'risk_debate_state', title: '⚖️ 风险管理团队（旧）', duplicates: ['risk_management_decision'] },
  { key: 'detailed_analysis', title: '📄 详细分析' }
]

const REPORT_TAB_DEFINITION_MAP = new Map(
  REPORT_TAB_DEFINITIONS.map(definition => [definition.key, definition])
)

const hasDisplayContent = (content: any): boolean => {
  if (typeof content === 'string') {
    return content.trim().length > 0
  }

  if (content === null || content === undefined) {
    return false
  }

  if (Array.isArray(content)) {
    return content.length > 0
  }

  if (typeof content === 'object') {
    return Object.keys(content).length > 0
  }

  return true
}

const getFallbackTitle = (key: string) => key.replace(/_/g, ' ')

export const getReportTabTitle = (key: string): string => {
  return REPORT_TAB_DEFINITION_MAP.get(key)?.title || getFallbackTitle(key)
}

export const normalizeReportTabs = (reports: Record<string, any> | null | undefined): ReportTabItem[] => {
  if (!reports || typeof reports !== 'object') {
    return []
  }

  const normalized: ReportTabItem[] = []
  const consumedKeys = new Set<string>()

  for (const definition of REPORT_TAB_DEFINITIONS) {
    if (consumedKeys.has(definition.key)) {
      continue
    }

    if (!hasDisplayContent(reports[definition.key])) {
      continue
    }

    const hasPreferredDuplicate = (definition.duplicates || []).some(key => {
      return consumedKeys.has(key) || hasDisplayContent(reports[key])
    })

    if (hasPreferredDuplicate) {
      consumedKeys.add(definition.key)
      continue
    }

    normalized.push({
      key: definition.key,
      title: definition.title,
      content: reports[definition.key]
    })

    consumedKeys.add(definition.key)
  }

  for (const [key, content] of Object.entries(reports)) {
    if (consumedKeys.has(key) || !hasDisplayContent(content)) {
      continue
    }

    normalized.push({
      key,
      title: getReportTabTitle(key),
      content
    })
  }

  return normalized
}
