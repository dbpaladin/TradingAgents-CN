# 会话归档：A股新闻与情绪分析优化

- 日期：2026-03-22
- 主题：优化情绪面分析师与新闻分析师（聚焦A股）
- 执行方式：直接修改代码并完成基础语法校验

## 背景

本次会话先确认了当前数据源调用路径，再执行了两类优化：

1. 情绪面分析师从“模板化输出”升级到“基于新闻库的量化输出”。
2. 新闻分析师的A股路径强化为中文数据源优先，降低外文宏观噪声。

## 关键修改

### 1) 情绪面：接入真实量化逻辑

文件：
- `tradingagents/agents/utils/agent_utils.py`

变更点：
- 重构 `get_stock_sentiment_unified` 的A股/港股分支：
  - 从 MongoDB `stock_news` 读取近7天样本（最多200条）
  - 使用 `sentiment` + `sentiment_score` 计算：
    - 情绪指数（1-10）
    - 热度指数（1-10）
    - 置信度
    - 情绪动量（近24h vs 历史）
    - 正/中/负分布与来源分散度
- 当数据库不可用时，降级到中文情绪摘要接口。
- 美股分支改为 `get_reddit_company_news`，避免调用不存在函数名导致的失败风险。

### 2) 新闻面：A股中文源优先

文件：
- `tradingagents/dataflows/news/realtime_news.py`
- `tradingagents/tools/unified_news_tool.py`

变更点：
- `RealtimeNewsAggregator.get_realtime_stock_news(...)` 新增参数：
  - `prefer_china_sources: bool = False`
- 当 `prefer_china_sources=True` 时：
  - 先拉取中文财经新闻（东方财富/财联社等路径）
  - 样本足够直接返回，减少外文源无效调用
- 在 `get_realtime_stock_news` 主流程中，A股自动传入 `prefer_china_sources=is_china_stock`。
- A股统一新闻工具移除“OpenAI全球新闻”默认兜底，聚焦：
  - 数据库缓存/AKShare同步
  - 实时中文新闻
  - Google中文新闻

## 影响与收益

- A股情绪报告从“描述性模板”提升为“可量化、可解释、可追踪”。
- A股新闻获取链路更贴近中文市场语境，减少宏观泛化内容干扰。
- 整体结果在一致性和可复盘性上更好。

## 校验结果

已执行语法校验（`python3 -m py_compile`）并通过：
- `tradingagents/agents/utils/agent_utils.py`
- `tradingagents/dataflows/news/realtime_news.py`
- `tradingagents/tools/unified_news_tool.py`

## 备注

- 本次会话中发现工作区存在与本任务无关的已修改文件：
  - `frontend/src/views/Backtest/index.vue`
- 该文件未被本次任务变更。
