# 会话归档：A-Stock Enhanced 接入 Tushare 主备路由与生产灰度闭环

- 日期：2026-05-15
- 主题：评估 `TradingAgents-astock` 可借鉴点；在本仓库落地 `a_stock_enhanced` 的 Tushare 主备路由、灰度放量、观测与自动巡检
- 执行方式：代码实现 + 配置扩展 + 运维脚本 + 手册文档 + 归档

## 用户诉求

1. 对比外部仓库，判断哪些思路值得借鉴。
2. 重点讨论 Tushare 是否仍有价值，是否适合主链路。
3. 将 `a_stock_enhanced` 中部分数据源切换为 Tushare（非单源替换）。
4. 支持生产灰度、回退和观测。
5. 最终沉淀文档和会话归档。
6. 明确提出“按既定计划持续推进，不必反复确认”，并在风险可控前提下推进生产全量。

## 关键结论

1. 本项目不适合单源切换，最优是“主备并存”：
   - 结构化数据优先 Tushare
   - 实时/低延迟链路保留腾讯 + mootdx/ths
   - 失败自动回退
2. 在用户提供的前提（Tushare 10000积分）下，Tushare可作为高质量主源候选，但仍需保留回退。
3. 生产上可直接接入，但建议保留灰度与巡检闭环，避免隐性数据退化。
4. 在用户确认“可全量100%”后，策略上采用“全量优先 + 自动兜底回退 + 巡检告警”。

## 实施改动

### A. 主备路由与灰度能力

核心文件：
- `app/services/a_stock_enhanced/service.py`
- `app/services/a_stock_enhanced/config.py`
- `app/core/config.py`

落地点：
- `finance_snapshot`：新增 Tushare 主源逻辑（`stock_basic + income + fina_indicator`），并保留 mootdx 补缺。
- `northbound`：新增 Tushare `moneyflow_hsgt` 主源，回退 THS 接口。
- 新增可配置策略：
  - `A_STOCK_FINANCE_SOURCE=tushare|mootdx|hybrid`
  - `A_STOCK_NORTHBOUND_SOURCE=tushare|ths|hybrid`
  - `A_STOCK_TUSHARE_ENABLED=true|false`
- 新增灰度比例（稳定哈希分桶）：
  - `A_STOCK_FINANCE_TUSHARE_RATIO=0..100`
  - `A_STOCK_NORTHBOUND_TUSHARE_RATIO=0..100`
- 支持生产全量策略：
  - 将比例配置可直接设置为 `100`
  - 保留 fallback 分支，确保主源异常可自动切回

### B. 可观测性

- 在 `service.py` 增加命中日志：
  - `[a_stock_enhanced][finance] ...`
  - `[a_stock_enhanced][northbound] ...`
- 日志包含：`source`、`ratio`、`bucket`（finance）、`selected`、`count`（northbound）

### C. 巡检与自动化

新增脚本：
- `scripts/a_stock_gray_stats.py`
  - 支持文本输出 + `--json`
  - 支持阈值检测与退出码（finance<阈值返回2，northbound<阈值返回3）
- `scripts/check_a_stock_gray.sh`
  - 一键巡检包装脚本
  - 默认阈值提升至生产标准（90）
- `scripts/ops/install_a_stock_gray_cron.sh`
  - 自动安装 `crontab` 定时巡检任务
- `scripts/deployment/systemd/a-stock-gray-check.service`
- `scripts/deployment/systemd/a-stock-gray-check.timer`
  - systemd 定时巡检模板

### D. 手册文档

- 新增并持续更新：
  - `docs/guides/a_stock_enhanced_gray_release.md`
- 覆盖内容：
  - 配置项、灰度节奏、观测命令、统计脚本、阈值巡检、cron/systemd 自动化、回退方案

## 验证结果

- 相关 Python 文件均通过 `py_compile` 语法校验。
- 统计与巡检脚本执行正常；在“无样本日志”场景下按阈值返回预期退出码。

## 会话决策时间线（完整）

1. 用户先发起外部仓库借鉴调研诉求，并要求进入实施。
2. 用户连续追问 Tushare 价值、是否纳入主链路，以及与 AkShare 的稳定性/质量/完整性对比。
3. 用户明确要求“不是单源替换”，而是 `a_stock_enhanced` 内按字段/链路选择更合适的数据源。
4. 用户要求直接推进灰度方案，并追问“是否可直接接入生产”“是否可直接全量100%”。
5. 在确认“有兜底”后，用户同意推进全量策略，并要求“不要再问我，按计划持续往下走”。
6. 用户最后要求归档聊天记录并更新项目文档/手册，本次归档即覆盖该完整链路。

## 产出价值

1. 数据源切换从“手工替换”升级为“策略化路由 + 灰度 + 回退”。
2. 生产观测从“人工看日志”升级为“可量化巡检 + 自动化调度”。
3. 文档与会话闭环完整，便于后续交接与审计。
