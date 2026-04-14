# 报告动作一致性修复（final_trade_decision vs trader_investment_plan）

## 背景
在单股分析报告中，存在 `final_trade_decision` 与 `trader_investment_plan` 动作不一致的问题，导致：
- 页面展示的结构化 `decision.action` 与正文计划冲突
- 用户对最终建议产生歧义

## 修复内容
文件：`app/services/simple_analysis_service.py`

1. 新增动作归一化与解析方法：
- `_normalize_action(raw_action)`
- `_extract_action_from_text(text)`
- `_reconcile_report_actions(reports, decision)`

2. 一致性规则：
- 优先级：`final_trade_decision` > `decision.action` > `trader_investment_plan`
- 将结构化 `decision.action` 对齐为最终 canonical action
- 若交易计划与最终决策冲突，在 `trader_investment_plan` 顶部追加“**一致性校正说明**”

3. 接入点：
- 分析执行完成后，生成 `result` 前进行一次对齐
- 保存到 `analysis_reports` 前再次对齐，保证落库数据一致

## 兼容性说明
- 不改动下游接口结构，仅修正字段值与报告说明
- 对历史冲突报告可做一次性回写校正（本次已对最新 000938 报告执行）
