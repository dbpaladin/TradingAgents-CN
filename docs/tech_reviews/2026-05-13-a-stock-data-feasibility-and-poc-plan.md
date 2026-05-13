# `a-stock-data` 数据源可行性评估与 PoC 计划

- 日期：2026-05-13
- 评估对象：[`dbpaladin/a-stock-data`](https://github.com/dbpaladin/a-stock-data)
- 评估范围：仅做现有项目的数据源替换/互补研究，不修改生产代码
- 目标项目：`TradingAgents-CN`

## 结论摘要

本轮结论是：

- **不建议直接替换** 现有 A 股主数据源链路
- **建议作为 A 股增强层接入**，优先补强 `K线 / 实时估值 / F10 / 财务快照 / 北向分钟 / 研报 / 公告`
- **建议先做旁路 PoC**，稳定后再决定是否进入统一 `DataSourceManager`

原因在于，`a-stock-data` 的定位更接近“给 AI 助手直接调用的自包含工具集”，而不是稳定、批量、结构化的通用 Python SDK。它的强项是多源拼装后的 A 股特色能力，而不是替代当前系统依赖的 `daily_basic + 批量同步 + 主链路入库`。

## 本项目现状

当前项目已经具备统一数据源抽象，A 股主链路至少覆盖：

- `Tushare`
- `AKShare`
- `BaoStock`

核心接口抽象包括：

- `get_stock_list`
- `get_daily_basic`
- `find_latest_trade_date`
- `get_realtime_quotes`
- `get_kline`
- `get_news`

对应代码位置：

- `app/services/data_sources/base.py`
- `app/services/data_sources/manager.py`
- `app/services/data_sources/tushare_adapter.py`
- `app/services/data_sources/akshare_adapter.py`
- `app/services/data_sources/baostock_adapter.py`

这意味着架构上完全支持新增一个 A 股增强型 provider 或 service，但不意味着应该直接替换当前主数据源。

## `a-stock-data` 的能力定位

根据其 `README` 与 `SKILL.md`，该仓库当前强调六层能力：

- 行情层：`mootdx + 腾讯财经`
- 研报层：`东财 + iwencai + akshare`
- 信号层：`同花顺热点 + 北向资金`
- 新闻层：`akshare`
- 基础数据层：`mootdx finance / F10`
- 公告层：`巨潮`

仓库现状特征：

- 开源发布时间很新
- 最近公开提交较少
- 主要内容集中在 `SKILL.md`
- 更适合作为“能力清单 + 示例实现来源”，不适合作为即插即用的生产 SDK

## 实测验证结论

本轮使用隔离虚拟环境进行了只读实测，未修改项目代码。

### 1. `mootdx`

验证结果：

- `bars` 可用
- `quotes` 可用
- `finance` 可用
- `F10` 可用

判断：

- 非常适合补 A 股 `K线 / 五档盘口 / F10 / 季报快照`
- 适合作为增强层，不适合作为现有 `daily_basic` 替代品

### 2. 腾讯财经

验证结果：

- 实时返回 `price / pre_close / open / high / low / pct_chg`
- 可返回 `PE(TTM) / PB / 总市值 / 流通市值 / 换手率 / 涨跌停价 / 量比`

判断：

- 非常适合补现有实时估值展示
- 建议与 `mootdx` 实时价格拼装为增强版 quote

### 3. `hsgtApi`

验证结果：

- 可返回分钟级北向数据
- 当前 JSON 顶层结构为：`time / hgt / sgt`

判断：

- 很适合补资金面分析师的盘中北向证据
- 这类数据当前系统有需求，但不在现有主源统一抽象中

### 4. `AKShare` 封装相关端点

验证结果：

- `stock_news_em` 可用
- `stock_zh_a_disclosure_report_cninfo` 可用
- 部分 README/skill 示例接口在当前环境下已有漂移

判断：

- 说明 `a-stock-data` 中依赖的部分能力有实用价值
- 但不能把示例代码等同于稳定接口契约

## 为什么不建议直接替换主数据源

### 1. 主链路依赖结构化批量数据

当前项目的很多同步和分析链路依赖：

- `daily_basic`
- 交易日探测
- 批量股票列表
- 实时行情入库
- 结构化字段一致性

`a-stock-data` 在这些方面并不是天然主源。

### 2. 它的价值集中在“特色能力”

相比当前主数据源，它最有价值的是：

- `mootdx` K线和 F10
- 腾讯财经实时估值
- 北向分钟数据
- 东财研报与 PDF
- 巨潮公告

这更像增强层，而不是替代层。

### 3. 多个能力依赖非官方端点

这类端点通常存在：

- 字段漂移
- 反爬波动
- 时段敏感
- 文档不稳定

因此更适合低耦合、可降级接入。

## 建议的接入定位

建议将 `a-stock-data` 定位为：

- **A 股增强层**
- **旁路研究能力层**
- **高价值特色数据补充源**

而不是：

- A 股主结构化数据源
- 批量同步主源
- `daily_basic` 替代源

## 优先接入能力

按优先级建议如下：

1. `mootdx K线`
2. 腾讯财经实时估值快照
3. `mootdx finance`
4. `mootdx F10`
5. 同花顺 `hsgtApi`
6. 巨潮公告
7. 东财研报 / PDF

暂不建议优先接入：

- `iwencai`
- 将 `a-stock-data` 直接接成 `daily_basic`
- 依赖 skill 文件作为运行时主入口

## 关键字段确认项

### 腾讯财经 `amount`

- 原始值口径判断为 **万元**
- 标准模型建议统一转换为 **元**

### `mootdx finance`

本轮确认到的高价值字段样本：

- `liutongguben`
- `zongguben`
- `updated_date`
- `zhuyingshouru`
- `jinglirun`
- `weifenpeilirun`
- `meigujingzichan`

建议第一版保留 `raw`

### `hsgtApi`

当前 JSON 结构：

- `time`
- `hgt`
- `sgt`

建议标准化为：

- `hgt_net_buy`
- `sgt_net_buy`
- `northbound_total`

### 巨潮公告

当前最稳实现建议：

- `akshare.stock_zh_a_disclosure_report_cninfo(symbol=..., market='沪深京')`

### 东财研报

已确认可稳定提取：

- `title`
- `stockCode`
- `orgSName`
- `publishDate`
- `infoCode`
- `predictThisYearEps`
- `predictNextYearEps`
- `predictNextTwoYearEps`
- `emRatingName`
- `lastEmRatingName`
- `ratingChange`

## 字段映射摘要

### 1. 增强实时报价 `EnhancedQuote`

建议统一字段：

- `code`
- `name`
- `price`
- `pre_close`
- `open`
- `high`
- `low`
- `pct_chg`
- `change_amt`
- `volume`
- `amount`
- `turnover_rate`
- `pe_ttm`
- `pe_static`
- `pb`
- `total_mv`
- `circ_mv`
- `limit_up`
- `limit_down`
- `vol_ratio`
- `source`
- `fetched_at`

### 2. 腾讯财经映射

- `vals[1] -> name`
- `vals[3] -> price`
- `vals[4] -> pre_close`
- `vals[5] -> open`
- `vals[31] -> change_amt`
- `vals[32] -> pct_chg`
- `vals[33] -> high`
- `vals[34] -> low`
- `vals[37] -> amount_wan`
- `vals[38] -> turnover_rate`
- `vals[39] -> pe_ttm`
- `vals[44] -> total_mv`
- `vals[45] -> circ_mv`
- `vals[46] -> pb`
- `vals[47] -> limit_up`
- `vals[48] -> limit_down`
- `vals[49] -> vol_ratio`
- `vals[52] -> pe_static`

建议标准化：

- `amount = amount_wan * 10000`

### 3. `mootdx quotes` 映射

- `code -> code`
- `price -> price`
- `last_close -> pre_close`
- `open -> open`
- `high -> high`
- `low -> low`
- `vol -> volume`
- `amount -> amount`
- `servertime -> fetched_at`

说明：

- `mootdx` 提供交易层数据
- 估值层字段建议由腾讯财经补齐

### 4. `mootdx bars` 映射

- `open -> open`
- `close -> close`
- `high -> high`
- `low -> low`
- `vol -> volume`
- `amount -> amount`
- `datetime` 或日期组合字段 -> `time`

### 5. `mootdx finance` 映射

建议第一版标准化：

- `liutongguben -> float_share`
- `zongguben -> total_share`
- `updated_date -> report_date`
- `zhuyingshouru -> revenue`
- `jinglirun -> net_profit`
- `weifenpeilirun -> undistributed_profit`
- `meigujingzichan -> bps`

并保留：

- `raw`

### 6. `hsgtApi` 映射

- `time[i] -> time`
- `hgt[i] -> hgt_net_buy`
- `sgt[i] -> sgt_net_buy`
- `hgt[i] + sgt[i] -> northbound_total`

### 7. 巨潮公告映射

当前稳定列：

- `代码 -> code`
- `简称 -> name`
- `公告标题 -> title`
- `公告时间 -> publish_time`
- `公告链接 -> url`

### 8. 东财研报映射

- `stockCode -> code`
- `title -> title`
- `orgSName -> org`
- `publishDate -> publish_date`
- `infoCode -> pdf_info_code`
- `predictThisYearEps -> eps_forecast_1y`
- `predictNextYearEps -> eps_forecast_2y`
- `predictNextTwoYearEps -> eps_forecast_3y`
- `emRatingName -> rating`
- `lastEmRatingName -> last_rating`
- `ratingChange -> rating_change`

## 推荐模块设计

建议先做增强服务层，而不是直接扩展主 adapter。

### 新增目录

- `app/services/a_stock_enhanced/`

### 建议文件

- `models.py`
- `config.py`
- `utils.py`
- `tencent_quotes.py`
- `mootdx_client.py`
- `northbound.py`
- `research_reports.py`
- `announcements.py`
- `service.py`

### 推荐统一入口

建议新增：

- `AStockEnhancedService`

建议方法：

- `get_quote_enhanced(code)`
- `get_quotes_enhanced(codes)`
- `get_kline_enhanced(code, period, limit)`
- `get_finance_snapshot(code)`
- `get_f10_document(code, category)`
- `get_northbound_intraday()`
- `get_research_reports(code)`
- `get_announcements(code)`

### 推荐数据组合策略

- 实时价格与盘口：优先 `mootdx`
- 实时估值字段：优先腾讯财经
- 北向分钟：独立 `hsgtApi`
- 公告：独立巨潮
- 研报：独立东财

## 推荐实施路径

### 阶段 1：只读 PoC

目标：

- 验证端点稳定性
- 统一字段映射
- 不接入生产主流程

交付：

- 字段映射表
- PoC 验证脚本
- 可行性报告

### 阶段 2：增强服务接入

目标：

- 新增 `AStockEnhancedService`
- 以旁路方式提供增强能力

建议能力：

- `get_quote_enhanced`
- `get_kline_enhanced`
- `get_finance_snapshot`
- `get_f10_document`
- `get_northbound_intraday`
- `get_research_reports`
- `get_announcements`

### 阶段 3：有限统一接入

前提：

- 连续 3 到 5 个交易日 PoC 验证通过
- 字段映射稳定
- 失败率可接受

候选接入点：

- `get_kline()`
- `get_realtime_quotes()`
- 公告/研报扩展接口

## PoC 验收标准

建议按以下维度评估：

- 成功率
- 延迟
- 字段缺失率
- 字段漂移
- 降级表现
- 是否影响现有主链路

建议连续观察 3 到 5 个交易日。

## 下次开发建议顺序

1. 建标准模型
2. 建字段标准化工具
3. 接腾讯财经增强 quote
4. 接 `mootdx` K线 / finance / F10
5. 接北向分钟数据
6. 接公告
7. 接研报
8. 最后再评估是否进入统一 manager

## 风险清单

- 非官方接口字段漂移
- 部分 `akshare` 包装与底层站点不一致
- 研报 / 公告端点存在反爬波动
- `mootdx` 对网络和节点可达性较敏感
- 北向分钟数据口径与其他源不同

## 最终建议

最终建议是：

- **不替换当前 A 股主数据源**
- **以增强层 PoC 的方式引入 `a-stock-data` 中最有价值的特色能力**
- **先独立服务化，再考虑有限统一接入**

这是兼顾收益、风险和现有架构成本的最优路径。
