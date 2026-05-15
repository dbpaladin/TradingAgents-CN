# A-Stock Enhanced 灰度发布指南

本文档用于指导 `a_stock_enhanced` 的 Tushare 灰度发布、观测与回退。

## 1. 配置项

在 `.env` 中设置：

```env
# 总开关
A_STOCK_TUSHARE_ENABLED=true

# 数据源策略
# finance: tushare | mootdx | hybrid
A_STOCK_FINANCE_SOURCE=hybrid
# northbound: tushare | ths | hybrid
A_STOCK_NORTHBOUND_SOURCE=hybrid

# 灰度比例（仅在 hybrid 下生效）
A_STOCK_FINANCE_TUSHARE_RATIO=20
A_STOCK_NORTHBOUND_TUSHARE_RATIO=20
```

说明：
- `*_RATIO` 范围 `0-100`
- `0` 表示不走 Tushare，`100` 表示全量走 Tushare
- 服务重启后生效

## 2. 灰度步骤

推荐分阶段：

1. 第一阶段（10%-20%）
2. 第二阶段（50%）
3. 第三阶段（100%）

每个阶段至少观察 1 个交易日，再进入下一阶段。

## 3. 日志观测

系统会输出两类日志：
- `[a_stock_enhanced][finance]`
- `[a_stock_enhanced][northbound]`

快速查看：

```bash
rg "\[a_stock_enhanced\]\[(finance|northbound)\]" logs -n
```

## 4. 命中率统计

使用脚本：

```bash
python scripts/a_stock_gray_stats.py --hours 24
```

JSON 输出（便于接监控）：

```bash
python scripts/a_stock_gray_stats.py --hours 24 --json
```

阈值巡检（低于阈值返回非 0）：

```bash
python scripts/a_stock_gray_stats.py \
  --hours 24 \
  --min-finance-tushare-ratio 15 \
  --min-northbound-tushare-ratio 15
```

退出码：
- `2`：finance tushare ratio 低于阈值
- `3`：northbound tushare ratio 低于阈值

### 一键巡检脚本（适合 CI / crontab）

```bash
bash scripts/check_a_stock_gray.sh
```

可通过环境变量覆盖默认值：

```bash
A_STOCK_GRAY_CHECK_HOURS=24 \
A_STOCK_GRAY_FINANCE_MIN_RATIO=90 \
A_STOCK_GRAY_NORTHBOUND_MIN_RATIO=90 \
bash scripts/check_a_stock_gray.sh
```

### 自动安装 crontab（每 30 分钟）

```bash
bash scripts/ops/install_a_stock_gray_cron.sh /abs/path/to/TradingAgents-CN
```

可选覆盖：

```bash
CRON_SCHEDULE="*/15 * * * *" \
CHECK_HOURS=24 \
FINANCE_MIN=90 \
NORTHBOUND_MIN=90 \
bash scripts/ops/install_a_stock_gray_cron.sh /abs/path/to/TradingAgents-CN
```

### systemd timer（推荐生产）

模板文件：
- `scripts/deployment/systemd/a-stock-gray-check.service`
- `scripts/deployment/systemd/a-stock-gray-check.timer`

步骤：

1. 替换 `a-stock-gray-check.service` 中的 `REPLACE_USER` 与 `REPLACE_REPO_ROOT`
2. 复制到系统目录并启用 timer：

```bash
sudo cp scripts/deployment/systemd/a-stock-gray-check.service /etc/systemd/system/
sudo cp scripts/deployment/systemd/a-stock-gray-check.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now a-stock-gray-check.timer
sudo systemctl status a-stock-gray-check.timer
```

生产建议（全量 100% 目标）：
- 默认阈值建议保持在 `90`（已作为脚本默认值）
- 如果希望更严格，可提升到 `95`

## 5. 回退方案

快速回退到旧链路：

```env
A_STOCK_FINANCE_SOURCE=mootdx
A_STOCK_NORTHBOUND_SOURCE=ths
```

或仅关闭 Tushare：

```env
A_STOCK_TUSHARE_ENABLED=false
```

修改后重启服务即可。
