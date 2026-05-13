# 报告股票名称展示统一修复

## 背景

用户反馈当前分析报告“只有股票代码，没有股票名称”。排查后确认：

- `analysis_reports` 文档模型已经支持 `stock_name`
- 报告详情页标题也会优先展示 `stock_name`
- 但最终落盘的模块报告、导出 Markdown 和下载文件名，仍有多处直接使用 `stock_symbol`

因此问题不在数据采集层，而在最终报告生成与导出链路没有统一使用“股票展示名”。

## 根因

根因分为两层：

### 1. 标题生成各自为政

以下链路各自单独拼标题，且大多直接使用 `stock_symbol`：

- `app/services/simple_analysis_service.py`
- `web/utils/report_exporter.py`
- `app/routers/reports.py`
- `frontend/src/views/Reports/ReportDetail.vue`

这导致：

- 模块报告标题可能只有代码
- 汇总导出标题可能只有代码
- 下载文件名也只有代码

### 2. 原始正文缺少统一兜底

即使某些模块报告正文本身已经较完整，只要模型没主动写出股票名称，最终文件就会显得像“只分析代码”。

换句话说，系统缺少一个“在最终产物落盘前补齐分析对象”的统一后处理步骤。

## 修复方案

### 1. 统一股票展示名

新增统一规则：

- 有名称时：`股票名称（股票代码）`
- 无名称时：回退为 `股票代码`

该规则在服务层落盘、Web 导出、下载接口、前端下载文件名中统一使用。

### 2. 在最终产物保存前补齐分析对象

新增正文兜底逻辑：

- 若正文前部已包含 `分析对象` 或 `股票名称（代码）`，则保持原样
- 否则自动补写一行：

```md
**分析对象**：工业富联（601138）
```

这样即使原始分析内容没主动带名称，最终报告仍会显式标识分析对象。

### 3. 扩展到最终决策与降级报告

不仅普通模块报告会补齐名称：

- `final_trade_decision.md` 也补上 `分析对象`
- `news_report` 的降级报告同样会带出 `名称（代码）`

这样可以避免“正常报告有名称、降级报告没名称”的展示割裂。

## 影响范围

涉及文件：

- `app/services/simple_analysis_service.py`
- `web/utils/report_exporter.py`
- `app/routers/reports.py`
- `frontend/src/views/Reports/ReportDetail.vue`
- `tests/test_simple_analysis_service_report_fallbacks.py`

## 验证

通过以下验证：

```bash
pytest -q tests/test_simple_analysis_service_report_fallbacks.py
python -m py_compile app/services/simple_analysis_service.py web/utils/report_exporter.py app/routers/reports.py
```

重点确认：

- 模块报告标题带股票名称
- 降级新闻报告带股票名称
- 最终决策报告带股票名称
- 下载文件名优先使用 `股票名称（股票代码）`

## 关联归档

- `history_chat/2026-05-10_143025_分析报告股票名称展示修复_归档文档更新与GitHub提交.md`

## Follow-up（2026-05-13：`analysis` 旁路接口补齐）

后续用户再次反馈“问题又出现了”。复核后确认并不是上一次修复被覆盖，而是还有一条旁路没有接入同样的 `stock_name` 规则：

- `app/routers/analysis.py` 在任务状态与结果返回中没有统一补回 `stock_name`
- `frontend/src/views/Analysis/SingleAnalysis.vue`
- `frontend/src/views/Reports/index.vue`
- `frontend/src/views/Dashboard/index.vue`

这会导致：

- 报告详情页正常显示名称
- 但单股分析页、仪表盘或报告列表下载入口仍可能只显示股票代码

本轮补齐后：

- `analysis` 任务状态与结果接口都会显式返回 `stock_name`
- 上述三个前端下载入口统一改为优先使用 `股票名称（股票代码）`

关联归档：

- `history_chat/2026-05-13_091314_报告名称显示复发排查_旁路接口补齐与GitHub提交.md`
