# A股报告决策一致性修复（2026-03-22）

## 背景

在复核 `601669_分析报告_2026-03-21.pdf` 时，暴露出几类典型问题：

1. 题材归类前后不一致，容易把“主线相关但非核心”误写成“无主线关联”
2. 机构布局分、龙头分等评分缺乏解释，结论像黑箱
3. 北向、融资、机构席位等关键数据缺失时，仍然输出过强结论
4. 最终建议缺少“持仓者 / 空仓者”分层，且对子模块分歧解释不充分

## 修复范围

涉及文件：

- `tradingagents/agents/analysts/theme_rotation_analyst.py`
- `tradingagents/agents/analysts/institutional_theme_analyst.py`
- `tradingagents/agents/managers/risk_manager.py`
- `tradingagents/agents/trader/trader.py`
- `tradingagents/graph/trading_graph.py`

## 具体修复

### 1. 题材轮动口径统一

- 强制使用 `主线核心 / 主线外延 / 非主线` 三档标签
- 如果目标股与主线产业链有关但不是核心，不再允许直接写成“无主线关联”
- 要求补充“为什么不是核心”的依据
- 若引用角色评分，必须解释评分区间

### 2. 机构布局评分透明化

- 输出“机构布局评分”时，必须解释评分来源与区间
- 如果只是与板块有关联，但不在候选先手名单中，要求明确写成“有板块关联但不属于候选先手核心”
- 当催化、试盘、机构席位等证据缺失时，必须显式写出“数据缺口/证据不足”

### 3. 风险经理决策解释增强

- 最终决策新增“决策解释”段
- 要求明确说明：如果最终建议与基本面建议相反，为什么基本面逻辑暂时失效
- 强制输出“持仓者建议”和“空仓者建议”
- 明确禁止把缺失资金数据表述成强看空结论

### 4. 交易员输出分层化

- 交易员必须分别给出“持仓者怎么做”和“空仓者怎么做”
- 当基本面、资金面、题材面彼此冲突时，必须解释裁决逻辑
- 当北向、融资、机构席位等数据不足时，必须降低置信度

### 5. 前端 sentiment 别名补齐机构布局维度

- 当前端只选 `sentiment` 时，自动补上 `institutional_theme`
- 避免 A 股报告在情绪/资金/题材齐全时仍漏掉机构布局题材分析

## 预期效果

- 降低题材归类自相矛盾的概率
- 降低“黑箱评分”造成的误读
- 在数据不完整时输出更克制、更可解释的结论
- 让最终建议更贴近实际交易场景，而不是一刀切

## 验证

执行并通过：

```bash
python -m py_compile \
  tradingagents/agents/analysts/theme_rotation_analyst.py \
  tradingagents/agents/analysts/institutional_theme_analyst.py \
  tradingagents/agents/managers/risk_manager.py \
  tradingagents/agents/trader/trader.py \
  tradingagents/graph/trading_graph.py
```

## 关联归档

- 会话归档：`history_chat/2026-03-22_104630_601669报告复核与决策链路修复归档.md`
