# A股资金面分析师开发记录

- 日期：2026-03-21
- 范围：A股资金面分析工具、分析师接入、前后端同步、验证与环境修正

## 背景

系统原本对“资金面”只有分散覆盖：

- `A股情绪分析师` 可输出龙虎榜近一月上榜次数和净买额
- `机构布局题材分析师` 可做机构提前布局题材的前瞻推断
- `市场分析师` 的职责文案中提到北向资金、融资融券、大宗交易

但没有一个独立角色专门负责回答：

- 当前是谁在买
- 是游资接力、机构吸筹，还是资金分歧
- 龙虎榜、北向、融资融券这些线索是否支持交易

因此本轮新增独立的 `资金面分析师`。

## 新增能力

### 1. 资金面分析工具

文件：

- [a_share_fund_flow.py](/home/wing/myproject/TradingAgents-CN/tradingagents/tools/analysis/a_share_fund_flow.py)

功能：

- 读取 AKShare 龙虎榜统计、涨停池、强势池、炸板池
- 尝试补充 Tushare `moneyflow`、`margin_detail`、`hk_hold`
- 输出：
  - 个股当前状态
  - 资金风格判断
  - 行动偏向
  - 机构信号
  - 北向信号
  - 融资融券信号
  - 关键证据列表

### 2. 资金面分析师

文件：

- [fund_flow_analyst.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/analysts/fund_flow_analyst.py)

职责：

- 以 A 股资金面为独立视角出报告
- 区分机构资金、游资资金和增量资金
- 判断交易更适合跟随、等分歧还是先观望

## 主链路接入

涉及文件：

- [__init__.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/__init__.py)
- [agent_states.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/utils/agent_states.py)
- [agent_utils.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/utils/agent_utils.py)
- [conditional_logic.py](/home/wing/myproject/TradingAgents-CN/tradingagents/graph/conditional_logic.py)
- [propagation.py](/home/wing/myproject/TradingAgents-CN/tradingagents/graph/propagation.py)
- [setup.py](/home/wing/myproject/TradingAgents-CN/tradingagents/graph/setup.py)
- [trading_graph.py](/home/wing/myproject/TradingAgents-CN/tradingagents/graph/trading_graph.py)
- [reflection.py](/home/wing/myproject/TradingAgents-CN/tradingagents/graph/reflection.py)

接入点：

- 新增 `fund_flow_report`
- 新增 `fund_flow_tool_call_count`
- 新增 `get_a_share_fund_flow`
- 新增 graph analyst node / tool node
- `sentiment` alias 扩展时自动包含 `fund_flow`

## 研究、交易、风控同步

涉及文件：

- [bull_researcher.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/researchers/bull_researcher.py)
- [bear_researcher.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/researchers/bear_researcher.py)
- [trader.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/trader/trader.py)
- [research_manager.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/managers/research_manager.py)
- [risk_manager.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/managers/risk_manager.py)
- [aggresive_debator.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/risk_mgmt/aggresive_debator.py)
- [conservative_debator.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/risk_mgmt/conservative_debator.py)
- [neutral_debator.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/risk_mgmt/neutral_debator.py)

效果：

- 资金面报告不再只是“展示模块”
- 它会参与投资计划、目标价判断和风险辩论

## 前后端同步

涉及文件：

- [analysts.ts](/home/wing/myproject/TradingAgents-CN/frontend/src/constants/analysts.ts)
- [SingleAnalysis.vue](/home/wing/myproject/TradingAgents-CN/frontend/src/views/Analysis/SingleAnalysis.vue)
- [Backtest/index.vue](/home/wing/myproject/TradingAgents-CN/frontend/src/views/Backtest/index.vue)
- [ReportDetail.vue](/home/wing/myproject/TradingAgents-CN/frontend/src/views/Reports/ReportDetail.vue)
- [Detail.vue](/home/wing/myproject/TradingAgents-CN/frontend/src/views/Stocks/Detail.vue)
- [analysis_form.py](/home/wing/myproject/TradingAgents-CN/web/components/analysis_form.py)
- [analysis_results.py](/home/wing/myproject/TradingAgents-CN/web/components/analysis_results.py)
- [results_display.py](/home/wing/myproject/TradingAgents-CN/web/components/results_display.py)
- [analysis_runner.py](/home/wing/myproject/TradingAgents-CN/web/utils/analysis_runner.py)
- [progress_tracker.py](/home/wing/myproject/TradingAgents-CN/web/utils/progress_tracker.py)
- [async_progress_tracker.py](/home/wing/myproject/TradingAgents-CN/web/utils/async_progress_tracker.py)
- [report_exporter.py](/home/wing/myproject/TradingAgents-CN/web/utils/report_exporter.py)
- [simple_analysis_service.py](/home/wing/myproject/TradingAgents-CN/app/services/simple_analysis_service.py)
- [analysis.py](/home/wing/myproject/TradingAgents-CN/app/routers/analysis.py)

结果：

- 单股分析可选 `资金面分析师`
- 回测可选 `fund_flow`
- 报告页、详情页、导出页、Streamlit 展示都识别 `fund_flow_report`

## 验证

### 测试

执行：

```bash
./.venv/bin/python -m pytest tests/test_a_share_fund_flow.py tests/test_a_share_sentiment.py tests/test_a_share_institutional_theme.py -q
```

结果：

- `7 passed`
- `1 warning`

### 环境结论

本轮还确认了一个重要开发约定：

- 系统 Python：`/usr/bin/python3`
- 项目虚拟环境：[`./.venv/bin/python`](/home/wing/myproject/TradingAgents-CN/.venv/bin/python)

`pytest` 和 `pandas` 安装在项目 `.venv` 中，因此后续所有验证命令都应优先使用：

```bash
./.venv/bin/python -m pytest ...
```

## 结论

本轮已经把 A 股资金面从“分散字段和提示词职责”升级为独立分析模块，并且完成了：

- 新工具
- 新分析师
- 主链路接入
- 前后端接线
- 导出支持
- 基础测试验证
