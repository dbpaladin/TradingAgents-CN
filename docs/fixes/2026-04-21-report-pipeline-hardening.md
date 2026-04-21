# 报告生产链路加固（2026-04-21）

## 背景

在复核工业富联（`601138`）最新单股报告时，暴露出两类生产问题：

1. 最终报告可能出现“动作与目标价冲突”
2. `news_report.md` 可能被写成空文件

这两类问题都不是单份报告内容问题，而是生产链路在“二次抽取”和“工具调用透传”上的实现缺陷。

## 影响范围

涉及文件：

- `tradingagents/graph/signal_processing.py`
- `app/services/simple_analysis_service.py`
- `tradingagents/agents/analysts/news_analyst.py`

新增测试：

- `tests/test_signal_processor_decision_consistency.py`
- `tests/test_news_analyst_toolcall_passthrough.py`

## 问题一：最终决策二次抽取导致动作与目标价冲突

### 根因

`risk_manager` 先输出自然语言最终结论，随后 `SignalProcessor.process_signal()` 再把这段自然语言抽取为结构化决策。

原实现存在 3 个问题：

1. 过度依赖二次 LLM 摘要中的 `action`
2. 用宽松正则从整段文本里扫“任意价格数字”
3. 不校验 `action`、`target_price` 与 `current_price` 的方向一致性

典型坏结果：

- 文本里写“持仓者减仓观察 / 空仓者等待确认”
- 但结构化结果被抽成：
  - `action = 持有`
  - `target_price = 55`
  - 当前价格却是 `61.51`

### 修复

在 `tradingagents/graph/signal_processing.py` 中：

- 优先从原文提取：
  - `最终建议`
  - `核心目标价`
  - `基准目标价`
  - `基准情景目标价`
- 新增 `current_price` 提取
- 新增一致性修正逻辑：
  - 当 `持有 + 低于现价的目标价 + 偏空语义` 同时出现时，修正为更符合原文的 `卖出`
- 新增返回字段：
  - `current_price`
  - `consistency_note`

## 问题二：新闻分析师在 tool_calls 分支提前落空报告

### 根因

在 `tradingagents/agents/analysts/news_analyst.py` 的非 Google 分支中：

- 若模型返回 `tool_calls`
- 原代码却直接读取 `result.content` 当最终报告
- 但带工具调用的 AIMessage 经常 `content == ""`
- 随后 tool_calls 又被清掉

这会导致：

1. `news_report` 被写成空字符串
2. 图执行层看到“无 tool_calls”，提前结束
3. `news_report.md` 被保存为空文件

### 修复

- 有 `tool_calls` 时，直接返回原始消息给工作流执行工具
- 不再把空 `content` 当正文
- 若最终确实没有正文，落一个“新闻分析降级报告”，显式标明该维度结果无效

## 服务层可见化修复

在 `app/services/simple_analysis_service.py` 中：

- `formatted_decision` 接收并保留：
  - `current_price`
  - `consistency_note`
- `recommendation` 中追加一致性修正说明
- `final_trade_decision.md` 中新增：
  - `当前价格`
  - `一致性修正说明`

这样就算解析器进行了纠偏，最终产物里也能看出修正原因，而不是静默改值。

## 验证

通过：

```bash
python3 -m py_compile \
  tradingagents/graph/signal_processing.py \
  app/services/simple_analysis_service.py \
  tradingagents/agents/analysts/news_analyst.py \
  tests/test_signal_processor_decision_consistency.py \
  tests/test_news_analyst_toolcall_passthrough.py
```

并通过隔离 stub 脚本验证：

- 冲突决策会产生 `consistency_note`
- `tool_calls + 空content` 场景不再写空 `news_report`

## 关联归档

- `history_chat/2026-04-21_工业富联报告复核_生产链路修复与GitHub提交.md`
