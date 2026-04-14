# A股报告“当前价格”日期错位修复（2026-04-14）

## 问题现象

- 单股分析 `000938` 报告中“当前价格”不是 `2026-04-14` 收盘价。
- 报告显示价格 `28.24`（对应 `2026-04-13`），而 `2026-04-14` 收盘应为 `27.86`。

## 根因

1. 生效数据源配置中 `tushare` 被禁用，历史数据优先取 `akshare` 缓存。
2. 当历史日线未覆盖目标结束日时，报告层默认取“最后一条历史 close”，缺少新鲜度兜底。
3. `market_quotes` 快照虽已更新到当日价格，但 `app_adapter` 返回字段不足，无法稳定用于报告层判定。

## 修复内容

### 1) 数据源策略调整（运行配置）

- 在 `system_configs` 激活配置中设置：
  - `tushare: enabled=True, priority=2`
  - `akshare: enabled=True, priority=1`

### 2) 历史缓存新鲜度策略

文件：`tradingagents/dataflows/cache/mongodb_cache_adapter.py`

- 增加 `.env` 第三方 Tushare 覆盖检测，避免被旧数据库开关误禁用。
- 查询历史数据时按“优先级 + 最新 trade_date”联合决策：
  - 高优先级源过旧时继续尝试备用源。
  - 都未覆盖目标日时回退到最新 trade_date 的候选结果。

### 3) 报告价格兜底与来源标注

文件：`tradingagents/dataflows/data_source_manager.py`

- 在技术分析结果格式化阶段，增加 `market_quotes` 快照兜底。
- 当历史数据未覆盖 `end_date` 且快照更新时间达到目标日时，优先使用快照价格。
- 增加文本标注：价格来源、trade_date 与 updated_at。

### 4) 快照字段补齐

文件：`tradingagents/dataflows/cache/app_adapter.py`

- 新增返回字段：`pre_close`、`updated_at`、`data_source`。

## 验证

- `py_compile` 检查通过。
- 复测 `get_china_stock_data_unified('000938', ..., '2026-04-14')` 输出为：
  - `最新价格: ¥27.86`
  - 并显示 `market_quotes` 快照来源说明。

## 影响范围

- A股单股分析链路（尤其报告中的“当前/最新价格”）
- 依赖 `MongoDBCacheAdapter` 的历史数据读取分支

