# A股回测与个股分析：股票名称联动与搜索500修复

- 日期：2026-03-24
- 影响范围：`frontend/src/views/Analysis/SingleAnalysis.vue`、`frontend/src/views/Backtest/index.vue`、`frontend/src/views/Tasks/TaskCenter.vue`、`app/services/unified_stock_service.py`
- 目标：输入股票代码时可带出股票名称，并修复查询时“内部服务器错误”

## 背景

用户在 A 股回测和个股分析界面希望“输入股票代码后可看到股票名称”。接入多市场搜索接口后，出现“输入股票代码报内部服务器错误”。

## 根因

后端接口 `/api/markets/{market}/stocks/search` 查询 MongoDB 时返回了默认 `_id` 字段（`ObjectId` 类型），FastAPI 在响应序列化阶段抛出异常：

- `PydanticSerializationError: Unable to serialize unknown type: <class 'bson.objectid.ObjectId'>`

即：数据库查询成功，但响应序列化失败，最终表现为 HTTP 500。

## 修复内容

### 1) 后端搜索接口修复

文件：`app/services/unified_stock_service.py`

- 查询时显式排除 `_id`：
  - `collection.find(filter_query, {"_id": 0})`
- 去重循环增加兜底清理：
  - `doc.pop("_id", None)`

效果：彻底避免 `ObjectId` 进入 API 响应体。

### 2) 个股分析页输入联动

文件：`frontend/src/views/Analysis/SingleAnalysis.vue`

- 输入股票代码后增加防抖查询（400ms）
- 新增匹配中状态：
  - “正在匹配股票名称...”
- 查询成功后显示股票名称标签
- 切换市场、输入为空、校验失败时重置名称状态
- 组件卸载时清理定时器与并发序号，避免竞态更新

### 3) A股回测页输入联动

文件：`frontend/src/views/Backtest/index.vue`

- 输入框增加 `@input` 防抖触发与 `@blur` 主动查询
- 接入 `searchStocks('CN', keyword, 10)`，优先精确代码匹配
- 新增请求序号控制，避免旧请求覆盖新输入结果
- 在“正在回测”标题与历史任务列表中显示股票名称

### 4) 任务中心文案优化

文件：`frontend/src/views/Tasks/TaskCenter.vue`

- 删除回测任务确认文案支持：
  - `代码（名称）`

## 验证

1. 本地服务重启后调用：
   - `GET /api/markets/CN/stocks/search?q=300628&limit=5`
2. 返回 `success=true`，示例返回包含：
   - `code=300628`
   - `name=亿联网络`
3. 确认返回项不再包含 `_id`，接口不再触发 500。

## 用户可见变化

1. 个股分析页输入股票代码会自动带出股票名称。
2. A股回测页输入股票代码会自动带出股票名称。
3. 多市场股票搜索不再因为 `ObjectId` 序列化报“内部服务器错误”。
