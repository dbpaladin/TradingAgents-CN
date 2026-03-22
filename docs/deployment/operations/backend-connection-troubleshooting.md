# 后端连接失败排查与修复说明

## 适用场景

当前端页面出现“后端服务连接失败”或服务脚本显示后端健康检查失败时，优先参考本文档。

## 已修复的问题

本轮已确认并修复以下问题：

- 后端启动时可能被外部环境变量 `PORT` 干扰，导致监听端口偏离 `8000`
- 前端健康检查过于敏感，单次失败就会误报后端断连
- 配置接口重复直读数据库，放大了设置页与首屏加载时的抖动
- `/api/system/config/validate` 原先使用同步 PyMongo，会阻塞事件循环

## 当前行为

### 启动层

- `scripts/backend_service.sh` 现在会显式注入：
  - `HOST`
  - `PORT`
  - `API_HOST`
  - `API_PORT`
- 默认后端端口固定为 `8000`

### 前端探测层

- 健康检查超时放宽到 5 秒
- 使用 `no-store` 和时间戳避免缓存干扰
- 必须连续失败 2 次才显示“后端连接失败”
- 页面会持续轮询健康状态，恢复后能更快消除错误提示

### 配置接口层

- `get_system_config()` 使用短 TTL 缓存
- `get_llm_providers()` 使用短 TTL 缓存
- 配置写入、厂家增删改后会主动失效缓存
- 首屏配置完整性校验改为单会话只执行一次

## 排查命令

```bash
./scripts/app_services.sh status
./scripts/app_services.sh logs backend
curl http://127.0.0.1:8000/api/health
ss -ltnp | rg ':8000|:3000'
```

## 正常基线

以下结果可视为已恢复正常：

- `./scripts/backend_service.sh status` 返回 `Health check OK`
- `curl http://127.0.0.1:8000/api/health` 返回 200
- 后端监听在 `0.0.0.0:8000`
- `/api/health` 通常为毫秒级
- `/api/config/settings` 与 `/api/config/llm` 在缓存命中后通常为毫秒级
- `/api/system/config/validate` 首次慢于健康检查，但应稳定在秒级以内

## 常见处理

- 终端关闭导致后端退出：执行 `./scripts/app_services.sh restart`
- 启动后监听端口不对：检查服务脚本是否为最新版本，并重新执行 `./scripts/backend_service.sh restart`
- 页面红字未消失但后端正常：等待前端下一轮健康检查，或刷新页面
- 设置页加载偏慢：优先检查 MongoDB 连通性和配置接口日志
