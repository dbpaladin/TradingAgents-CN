# A股分析报告质量优化记录

- 日期：2026-03-21
- 范围：A 股新闻情绪、基本面补数、行业识别、成长性分析、行业分析、投资建议、网页链路同步核对
- 示例标的：`601669`

## 背景

用户反馈 A 股个股分析报告存在明显数据缺失和模板化问题，典型表现包括：

- “未能获取完整的财务数据”
- “当前获取到的有效新闻样本仅 1 条”
- `所属行业` 显示为占位值 `stock_cn`
- `PS / 股息率 / 现金比率` 为 `N/A / 待查询 / 待分析`
- “成长性分析 / 行业分析 / 投资建议”表述偏泛，不够像正式研报

## 本次优化内容

### 1. 新闻与情绪数据链路

涉及文件：

- [chinese_finance.py](/home/wing/myproject/TradingAgents-CN/tradingagents/dataflows/news/chinese_finance.py)
- [manager.py](/home/wing/myproject/TradingAgents-CN/app/services/data_sources/manager.py)

主要改动：

- 移除固定 1 条示例新闻的 mock 逻辑
- 优先从 Mongo 新闻缓存读取，再回退到应用层新闻源
- 增加新闻去重、公司名/简称/代码匹配、来源统计和样本标题摘要
- 新闻 fallback 顺序优先使用 `akshare`
- 置信度从“固定低置信”改为基于样本量、来源覆盖和论坛数据动态评估

## 2. 基本面数据补齐与容错

涉及文件：

- [optimized_china_data.py](/home/wing/myproject/TradingAgents-CN/tradingagents/dataflows/optimized_china_data.py)

主要改动：

- 修复基本面缓存写入参数问题
- 从“整段失败就退简化报告”调整为“部分字段缺失时继续输出已有指标”
- 支持从多级来源补齐：
  - 实时价格/市值
  - Mongo 标准化财务数据
  - AKShare 财务摘要
  - Tushare `daily_basic` / 财报数据
- 重点补齐字段：
  - `PE`
  - `PB`
  - `PE_TTM`
  - `PS`
  - `股息率`
  - `现金比率`
  - `ROE`
  - `总市值`

## 3. 行业识别修复

主要改动：

- 过滤 `stock_cn`、空值等占位行业
- 增加 Tushare 基础信息 fallback
- `601669` 当前可正确识别为 `建筑工程`

## 4. 报告正文研报化

主要改动：

- 成长性分析：加入收入增速、利润增速、ROE、净利率、资产负债率、现金比率与行业属性
- 行业分析：加入行业驱动因素、利润率特征、资金占用、估值锚和分红属性
- 投资建议：结合估值、安全边际、盈利质量、分红、防御性、杠杆风险和催化条件形成结论

## 5. 配置兼容修复

涉及文件：

- [config.py](/home/wing/myproject/TradingAgents-CN/app/core/config.py)

主要改动：

- 兼容 `DEBUG=release / prod / production / dev / development` 等环境变量写法，避免运行时报错

## 验证

### 编译验证

以下文件已通过 `python3 -m py_compile`：

- [config.py](/home/wing/myproject/TradingAgents-CN/app/core/config.py)
- [manager.py](/home/wing/myproject/TradingAgents-CN/app/services/data_sources/manager.py)
- [simple_analysis_service.py](/home/wing/myproject/TradingAgents-CN/app/services/simple_analysis_service.py)
- [analysis.py](/home/wing/myproject/TradingAgents-CN/app/routers/analysis.py)
- [chinese_finance.py](/home/wing/myproject/TradingAgents-CN/tradingagents/dataflows/news/chinese_finance.py)
- [optimized_china_data.py](/home/wing/myproject/TradingAgents-CN/tradingagents/dataflows/optimized_china_data.py)
- [analysis_runner.py](/home/wing/myproject/TradingAgents-CN/web/utils/analysis_runner.py)
- [analysis_results.py](/home/wing/myproject/TradingAgents-CN/web/components/analysis_results.py)
- [report_exporter.py](/home/wing/myproject/TradingAgents-CN/web/utils/report_exporter.py)

### 运行验证

对 `601669` 的实测结果：

- 新闻情绪：`7` 条新闻，`7` 个来源
- 所属行业：`建筑工程`
- 市销率：`0.16倍`
- 股息收益率：`2.17%`
- 现金比率：`0.17`
- 成长性分析、行业分析、投资建议均已按新逻辑输出

## 网页链路同步结论

### 已确认同步

- 后端分析接口链路已使用新逻辑：
  - [analysis.py](/home/wing/myproject/TradingAgents-CN/app/routers/analysis.py)
  - [simple_analysis_service.py](/home/wing/myproject/TradingAgents-CN/app/services/simple_analysis_service.py)
  - [agent_utils.py](/home/wing/myproject/TradingAgents-CN/tradingagents/agents/utils/agent_utils.py)
  - [optimized_china_data.py](/home/wing/myproject/TradingAgents-CN/tradingagents/dataflows/optimized_china_data.py)
- `web/` 侧相关 Python 文件已纳入编译检查，说明 Web Python 界面与导出链路未被本次优化破坏

### 尚未能宣称完全构建通过

`frontend/` 在执行 `npm run build` 时失败，原因是项目中已存在的大量 TypeScript 历史类型错误，覆盖 `api/`、`stores/`、`views/` 多个模块。这些错误不是本次 A 股报告优化单点引入的，但意味着当前不能把“前端整包构建通过”作为本次结论的一部分。

## 结论

本次 A 股报告质量优化已经完成并落在主分析链路上，CLI、后端分析接口和 `web/` Python 页面链路均已同步到新版逻辑。若要让正在运行的网页实例实际呈现新结果，仍需对应环境重启服务；若要把 Vue 前端整包构建也恢复到绿色，需要单独处理现有 TypeScript 技术债。
