# A股回测性能优化技术总结 (2026-03-29)

## 1. 背景与目标
在回测场景下，原有系统存在单日分析耗时过长（约 13.4 分钟/天）的问题。主要瓶颈在于分析师节点的串联执行、冗余的辩论与风控 LLM 调用、以及过高的 IO/日志开销。本次优化的目标是将单日分析耗时降低至 1 分钟以内。

## 2. 优化方案与实施逻辑

### P0: 分析师节点并行化 (Analyst Parallelization)
- **改动文件**: `tradingagents/graph/setup.py`
- **实施逻辑**: 将原本按顺序连接的分析师节点改为并行扇出。所有选中的分析师同时从 `START` 启动，并在各自完成 `Msg Clear` 后汇聚到后续决策节点。
- **预期预期提速**: 40-70%。

### P1: 回测专用轻量决策图 (Lightweight Backtest Graph)
- **改动文件**: `tradingagents/graph/setup.py`, `tradingagents/graph/trading_graph.py`, `app/services/backtest_service.py`
- **实施逻辑**: 
    - 引入 `backtest_mode` 配置。
    - 在回测模式下，跳过 `Bull/Bear Researcher` 辩论、`Research Manager` 总结、`Trader` 决策、`Risky/Safe/Neutral Analyst` 风险讨论及 `Risk Judge`。
    - 新增 `Backtest Decision` 节点，综合各并行分析师的报告，通过单词 LLM 调用直接输出买卖信号。
- **预期提速**: 额外 30-50%。

### P3: 日志降级与进度更新节流 (Log Downgrade & Progress Throttling)
- **改动文件**: `tradingagents/graph/conditional_logic.py`, `app/services/backtest_service.py`
- **实施逻辑**:
    - 将 `conditional_logic.py` 中 79 条 `logger.info` 降级为 `logger.debug`，减少海量回测时的控制台/文件 IO 压力。
    - 在 `backtest_service.py` 中对进度更新进行节流。进度变化小于 5% 且未达到 95% 时，不写入 MongoDB，仅触发内存回调。
- **预期提速**: 5-10%。

## 3. 性能对比预估

| 场景 | 优化前 (Est.) | 优化后 (Est.) |
|------|------------|--------------|
| 单日分析 (标准模式) | ~13 分钟 | ~2-3 分钟 |
| 单日分析 (回测模式) | ~5 分钟 | ~30-60 秒 |
| 20天回测总耗时 | ~60 分钟 | ~8-12 分钟 |

## 4. 验证与后续建议
- **验证**: 检查日志中 `Backtest Decision` 节点的执行情况，并观察 `timing summary` 中的总耗时变化。
- **后续建议**: 
    - 进一步实现 P2 阶段的工具函数缓存（需修改 DataFlow 层）。
    - 在 UI 界面增加“极速回测”预设，方便用户快速使用该模式。
