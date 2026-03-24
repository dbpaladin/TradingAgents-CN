# 会话归档：股票代码带出名称与搜索接口500修复

- 日期：2026-03-24
- 主题：A股回测/个股分析输入代码联动股票名称；修复输入代码触发“内部服务器错误”
- 执行方式：前端联动增强 + 后端接口排障 + 接口验证 + 文档归档

## 用户诉求

1. A股回测和个股分析界面输入股票代码时，希望直接带出股票名称。
2. 输入股票代码后出现“内部服务器错误”，需要修复。
3. 要求完成文档更新、聊天归档并提交到 GitHub。

## 诊断结论

500 错误来自后端多市场搜索接口：

- 接口：`/api/markets/{market}/stocks/search`
- 表现：查询返回后在响应序列化阶段报错
- 根因：返回数据带有 MongoDB `_id(ObjectId)`，FastAPI/Pydantic 无法直接序列化

## 已实施修改

### 1) 后端修复（避免 ObjectId 序列化异常）

文件：`app/services/unified_stock_service.py`

- `find(...)` 增加投影排除 `_id`
- 在结果循环中增加 `doc.pop("_id", None)` 兜底

### 2) 个股分析页：输入代码自动联动名称

文件：`frontend/src/views/Analysis/SingleAnalysis.vue`

- 接入多市场搜索接口
- 输入防抖查询（400ms）
- 增加“正在匹配股票名称”与名称标签展示
- 生命周期中清理定时器和并发序号

### 3) 回测页：输入代码自动联动名称

文件：`frontend/src/views/Backtest/index.vue`

- 输入时防抖，失焦触发查询
- 优先精确代码匹配，失败再取首项
- 正在回测标题与历史任务中显示股票名称

### 4) 任务中心：删除确认文案增强

文件：`frontend/src/views/Tasks/TaskCenter.vue`

- 删除确认弹窗支持展示 `代码（名称）`

## 验证结果

实测 `GET /api/markets/CN/stocks/search?q=300628&limit=5` 返回：

- `success=true`
- `stocks[0].code=300628`
- `stocks[0].name=亿联网络`
- 返回项不含 `_id`

确认接口不再 500，输入代码可带出名称。

## 备注

本次归档覆盖了从“功能诉求”到“后端异常修复”的完整链路，包含代码变更、验证结果与文档同步动作。
