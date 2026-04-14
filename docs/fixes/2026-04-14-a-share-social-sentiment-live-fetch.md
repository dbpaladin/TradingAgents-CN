# A股社媒情绪样本补齐（股吧实时抓取 + 雪球降级兜底）

## 背景
在 A 股分析中，社媒维度出现“样本为 0”，导致情绪结论可信度明显下降。根因是既有链路主要依赖 Mongo 缓存与 `stock_news`，缺少稳定的实时论坛补样本能力。

## 目标
1. 在社媒缓存缺失时，自动补齐公开社媒样本。
2. 输出可解释指标：热度、平台分布、极端用语占比、样本标题示例。
3. 不增加主流程脆弱性（外部站点风控时可自动降级）。

## 方案

### 1. 新增轻量抓取模块
新增文件：`tradingagents/dataflows/news/cn_social_sentiment.py`

- 东方财富股吧：
  - 抓取 `https://guba.eastmoney.com/list,{symbol}.html`
  - 解析页面内 `var article_list=...` JSON 数据
  - 产出字段：`title/publish_time/platform/source/url/engagement/sentiment_score/extreme`
- 雪球：
  - 轻量尝试搜索接口
  - 命中 WAF 挑战页时返回空，不抛异常，不阻断主链路

### 2. 接入中文情绪聚合器
修改文件：`tradingagents/dataflows/news/chinese_finance.py`

- `_get_social_media_items`：
  - 先读 `social_media_messages` 缓存
  - 缓存为空时，自动调用 `fetch_cn_social_posts` 实时抓取
  - 新增开关：`CN_SOCIAL_LIVE_FETCH_ENABLED`（默认开启）
- `_get_stock_forum_sentiment`：
  - 新增统计字段：
    - `sample_titles`
    - `platform_breakdown`
    - `extreme_ratio`
    - `heat_level`
- `get_chinese_social_sentiment` 报告文本增强：
  - 增加“讨论热度、平台分布、极端用语占比、社媒标题示例”

## 验证

### 语法
- `python -m py_compile tradingagents/dataflows/news/chinese_finance.py tradingagents/dataflows/news/cn_social_sentiment.py`

### 运行验证（示例：000938）
- 东方财富股吧可获取到有效样本（40条）
- 雪球风控场景可自动降级
- 报告中已输出：
  - 讨论样本数
  - 讨论热度
  - 平台分布
  - 极端用语占比
  - 论坛/社媒标题示例

## 影响与兼容性
- 对既有缓存优先策略无破坏。
- 仅在缓存缺失时触发实时抓取，避免无谓外网依赖。
- 雪球不可用时仍可由股吧维持非零样本，改善“社媒样本为0”的关键痛点。

## 相关文件
- `tradingagents/dataflows/news/cn_social_sentiment.py`（新增）
- `tradingagents/dataflows/news/chinese_finance.py`（修改）
- `history_chat/2026-04-14_223100_000938社媒情绪补齐_股吧实时抓取与报告增强.md`（归档）
