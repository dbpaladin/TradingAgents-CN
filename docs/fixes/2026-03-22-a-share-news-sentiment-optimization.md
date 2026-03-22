# A股新闻与情绪分析优化（2026-03-22）

## 问题

1. 情绪分析师在A股/港股路径下主要输出模板化文本，缺少可计算信号。
2. 新闻分析在A股场景下存在外文或宏观新闻兜底，容易偏离个股语境。

## 解决方案

### 一、情绪分析量化改造

文件：`tradingagents/agents/utils/agent_utils.py`

对 `get_stock_sentiment_unified` 做了以下升级：

- 使用 `stock_news` 近7天数据（最多200条）作为A股/港股情绪样本。
- 使用 `sentiment` 与 `sentiment_score` 生成量化指标：
  - 情绪指数（1-10）
  - 热度指数（1-10）
  - 置信度（样本量+来源分散度）
  - 情绪动量（24小时均值与历史均值差）
  - 正/中/负样本分布
- 数据库不可用时降级到中文情绪摘要接口，避免空报告。
- 美股分支改为 `get_reddit_company_news`，规避潜在函数名不一致问题。

### 二、A股新闻中文源优先

文件：
- `tradingagents/dataflows/news/realtime_news.py`
- `tradingagents/tools/unified_news_tool.py`

优化点：

- `RealtimeNewsAggregator.get_realtime_stock_news` 增加 `prefer_china_sources` 参数。
- 当 A股触发该参数时：
  - 先获取中文财经新闻源（东方财富/财联社等）。
  - 若数量已满足要求则直接返回，减少无关外文源调用。
- A股统一新闻工具不再默认使用“OpenAI全球新闻”兜底，改为仅中文链路：
  - 数据库缓存/AKShare同步
  - 实时中文新闻
  - Google中文新闻

## 效果

- 情绪报告变为“可量化、可解释”的结构化输出。
- A股新闻数据来源更聚焦国内市场，信息噪声降低。
- 整体分析结果更稳定，更利于复盘。

## 验证

执行并通过：

```bash
python3 -m py_compile tradingagents/agents/utils/agent_utils.py
python3 -m py_compile tradingagents/dataflows/news/realtime_news.py
python3 -m py_compile tradingagents/tools/unified_news_tool.py
```

## 关联归档

- 会话归档：`docs/archive/chats/2026-03-22-a-share-news-sentiment-optimization.md`
