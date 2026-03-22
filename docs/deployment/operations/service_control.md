# 🎛️ TradingAgents-CN 服务启动控制指南

## 📋 概述

TradingAgents-CN 系统包含多个后台服务和定时任务，您可以通过配置文件灵活控制哪些服务启动，哪些服务不启动。

## 🔧 配置方式

### 1. 主要配置文件

- **`.env` 文件**: 主要配置文件，优先级最高
- **`app/core/config.py`**: 默认配置，当 `.env` 中没有配置时使用

### 2. 配置生效方式

修改配置后需要重启应用：
```bash
# 停止应用 (Ctrl+C)
# 重新启动
python -m app
```

### 3. 推荐的统一命令

日常只需要记两条脚本：

```bash
# Docker 依赖服务（MongoDB / Redis）
./scripts/docker_services.sh start

# 应用服务（后端 + 前端）
./scripts/app_services.sh start
```

对应的停止、重启、状态、日志也保持一致：

```bash
./scripts/docker_services.sh stop
./scripts/docker_services.sh restart
./scripts/docker_services.sh status
./scripts/docker_services.sh logs

./scripts/app_services.sh stop
./scripts/app_services.sh restart
./scripts/app_services.sh status
./scripts/app_services.sh logs
./scripts/app_services.sh logs backend
./scripts/app_services.sh logs frontend
```

### 4. 说明

- `./scripts/app_services.sh` 已经统一管理后端和前端，不需要再单独记后端脚本
- `./scripts/docker_services.sh` 只管理 Docker 中的 MongoDB / Redis
- 后端内部仍然使用守护方式启动，因此不会因为当前终端关闭而一起退出
- 如需开发热重载，可临时使用：

```bash
BACKEND_RELOAD=1 ./scripts/app_services.sh restart
```

### 5. 已移除的旧入口脚本

为避免混淆，`scripts/startup/` 中历史遗留的 `start_*` 入口脚本已移除。

- 应用统一入口：`./scripts/app_services.sh`
- Docker 依赖入口：`./scripts/docker_services.sh`
- 如需单独操作后端，可使用：`./scripts/backend_service.sh`

不要再使用旧的 `start_backend.py`、`start_web.py`、`start_simple.sh` 等历史脚本名。

## 🚀 可控制的服务类型

## 🌐 当前启动拓扑

最近已统一为“两层脚本 + 相对 API 路径”的管理方式：

- `./scripts/docker_services.sh`：只负责 MongoDB / Redis
- `./scripts/app_services.sh`：统一负责后端和前端
- 前端通过相对 API 路径访问后端，便于经 Nginx 或代理统一转发

推荐顺序：

```bash
./scripts/docker_services.sh start
./scripts/app_services.sh start
```

常见检查：

```bash
./scripts/docker_services.sh status
./scripts/app_services.sh status
./scripts/app_services.sh logs backend
./scripts/app_services.sh logs frontend
```

如果只是本地开发想启用后端热重载：

```bash
BACKEND_RELOAD=1 ./scripts/app_services.sh restart
```

注意：

- 热重载模式更适合开发排查，不建议作为长期运行方式
- 如果启动阶段伴随数据同步任务，热重载下更要关注首轮日志是否阻塞
- 修改 `.env` 后，需要重启对应服务才会重新加载配置

### 📊 基础服务

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SYNC_STOCK_BASICS_ENABLED` | `true` | 股票基础信息同步 |
| `QUOTES_INGEST_ENABLED` | `true` | 实时行情入库任务 |
| `QUOTES_INGEST_INTERVAL_SECONDS` | `30` | 行情入库间隔（秒） |

### 📈 Tushare 数据服务

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `TUSHARE_UNIFIED_ENABLED` | `true` | Tushare服务总开关 |
| `TUSHARE_BASIC_INFO_SYNC_ENABLED` | `true` | 基础信息同步 |
| `TUSHARE_QUOTES_SYNC_ENABLED` | `true` | 行情同步 |
| `TUSHARE_HISTORICAL_SYNC_ENABLED` | `true` | 历史数据同步 |
| `TUSHARE_FINANCIAL_SYNC_ENABLED` | `true` | 财务数据同步 |
| `TUSHARE_STATUS_CHECK_ENABLED` | `true` | 状态检查 |

### 📊 AKShare 数据服务

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `AKSHARE_UNIFIED_ENABLED` | `true` | AKShare服务总开关 |
| `AKSHARE_BASIC_INFO_SYNC_ENABLED` | `true` | 基础信息同步 |
| `AKSHARE_QUOTES_SYNC_ENABLED` | `true` | 行情同步 |
| `AKSHARE_HISTORICAL_SYNC_ENABLED` | `true` | 历史数据同步 |
| `AKSHARE_FINANCIAL_SYNC_ENABLED` | `true` | 财务数据同步 |
| `AKSHARE_STATUS_CHECK_ENABLED` | `true` | 状态检查 |

### 📋 BaoStock 数据服务

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `BAOSTOCK_UNIFIED_ENABLED` | `true` | BaoStock服务总开关 |
| `BAOSTOCK_BASIC_INFO_SYNC_ENABLED` | `true` | 基础信息同步 |
| `BAOSTOCK_QUOTES_SYNC_ENABLED` | `true` | 行情同步 |
| `BAOSTOCK_HISTORICAL_SYNC_ENABLED` | `true` | 历史数据同步 |
| `BAOSTOCK_STATUS_CHECK_ENABLED` | `true` | 状态检查 |

## ⏰ 定时任务配置

### CRON 表达式格式

```
* * * * *
│ │ │ │ │
│ │ │ │ └─── 星期几 (0-7, 0和7都表示周日)
│ │ │ └───── 月份 (1-12)
│ │ └─────── 日期 (1-31)
│ └───────── 小时 (0-23)
└─────────── 分钟 (0-59)
```

### 常用 CRON 示例

| CRON表达式 | 说明 |
|------------|------|
| `0 2 * * *` | 每日凌晨2点 |
| `*/5 9-15 * * 1-5` | 工作日9-15点每5分钟 |
| `0 16 * * 1-5` | 工作日16点 |
| `0 3 * * 0` | 每周日凌晨3点 |
| `0 * * * *` | 每小时整点 |

## 🎯 常见配置场景

### 场景1: 开发环境（最小化服务）

```env
# 只启用基础服务
SYNC_STOCK_BASICS_ENABLED=true
QUOTES_INGEST_ENABLED=false

# 禁用所有数据源同步
TUSHARE_UNIFIED_ENABLED=false
AKSHARE_UNIFIED_ENABLED=false
BAOSTOCK_UNIFIED_ENABLED=false
```

### 场景2: 生产环境（全功能）

```env
# 启用所有服务（默认配置）
SYNC_STOCK_BASICS_ENABLED=true
QUOTES_INGEST_ENABLED=true
TUSHARE_UNIFIED_ENABLED=true
AKSHARE_UNIFIED_ENABLED=true
BAOSTOCK_UNIFIED_ENABLED=true
```

### 场景3: 只使用 Tushare

```env
# 只启用 Tushare 服务
TUSHARE_UNIFIED_ENABLED=true
AKSHARE_UNIFIED_ENABLED=false
BAOSTOCK_UNIFIED_ENABLED=false
```

### 场景4: 禁用频繁任务

```env
# 禁用高频任务，只保留每日任务
QUOTES_INGEST_ENABLED=false
TUSHARE_QUOTES_SYNC_ENABLED=false
AKSHARE_QUOTES_SYNC_ENABLED=false
BAOSTOCK_QUOTES_SYNC_ENABLED=false
```

## 🔍 服务状态监控

### 查看启动日志

启动应用时会显示哪些服务已启用：

```
📅 Stock basics sync scheduled daily at 06:30 (Asia/Shanghai)
⏱ 实时行情入库任务已启动: 每 30s
🔄 配置Tushare统一数据同步任务...
📅 Tushare基础信息同步已配置: 0 2 * * *
📈 Tushare行情同步已配置: */5 9-15 * * 1-5
...
```

### API 健康检查

访问健康检查端点查看服务状态：
```
GET http://localhost:8000/api/health
```

如果你通过 Nginx 或统一入口访问前端，建议同时确认：

- 前端页面是否正常打开
- 浏览器网络请求中的 `/api/*` 是否返回 200
- 反向代理是否把 API 请求正确转发到后端

## ⚠️ 注意事项

1. **重启生效**: 修改配置后必须重启应用才能生效
2. **依赖关系**: 某些服务之间有依赖关系，建议保持基础服务启用
3. **资源消耗**: 启用的服务越多，系统资源消耗越大
4. **API限制**: 注意各数据源的API调用限制，避免超限
5. **时区设置**: 确保 `TIMEZONE` 设置正确，影响定时任务执行时间

## 🛠️ 故障排除

### 服务未启动

1. 检查配置项是否正确设置为 `true`
2. 查看启动日志是否有错误信息
3. 确认相关API密钥是否配置正确
4. 如果使用自定义 `TUSHARE_ENDPOINT`，确认对应域名可达且未被代理误转发

### 定时任务未执行

1. 检查CRON表达式格式是否正确
2. 确认时区设置是否正确
3. 查看应用日志中的任务执行记录

### 性能问题

1. 适当调整任务执行频率
2. 禁用不必要的服务
3. 开发环境优先使用统一脚本，不要再混用旧的 `dev_services.sh`
4. 若后端启动卡住，优先检查启动期同步任务和外部数据源连接
3. 监控系统资源使用情况
