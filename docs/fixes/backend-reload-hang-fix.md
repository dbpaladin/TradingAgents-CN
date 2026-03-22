# 后端热重载卡死修复

## 问题

前端偶发提示“无法连接到后端服务”，但实际观察到：

- `8000` 端口仍在监听
- `/api/health` 超时
- `webapi.log` 停在 `Waiting for background tasks to complete`

这类问题在启用了私有 `TUSHARE_ENDPOINT`、并且启动期会立即触发数据同步时更容易出现。

## 根因

`app/main.py` 的 `lifespan(...)` 在启动阶段直接创建了两个后台任务：

1. 启动期行情回填
2. 启动期股票基础信息同步

原实现使用裸 `asyncio.create_task(...)`，但在应用关闭时没有：

- 跟踪这些任务
- 主动取消这些任务
- 限时等待这些任务退出

因此一旦发生 `uvicorn --reload`、手动重启、文件变更触发 reload，旧 worker 会在 shutdown 阶段继续等待这些网络任务完成，导致进程卡死，最终表现为服务“假存活”。

## 修复方案

文件：`app/main.py`

### 1. 引入启动任务统一管理

新增：

- `_create_managed_startup_task(...)`
- `_cancel_managed_startup_tasks(...)`

作用：

- 记录启动阶段创建的后台任务
- 在 shutdown 阶段统一取消
- 限时等待任务退出

### 2. 替换裸 `asyncio.create_task(...)`

将以下逻辑改为受管任务：

- 启动期行情回填
- 启动期股票基础信息同步

### 3. 补充取消信号处理

在任务执行过程中显式处理 `asyncio.CancelledError`，确保 reload 或退出时任务能快速响应取消。

## 修复效果

- 私有 `TUSHARE_ENDPOINT` 保持不变，兼容现有第三方 Tushare 源配置。
- 启动期同步任务不再阻塞旧 worker 退出。
- 热重载和手动重启时不再长时间卡在 `Waiting for background tasks to complete`。
- 前端 `/api/health` 恢复稳定。

## 验证

### 语法校验

```bash
python -m py_compile app/main.py
```

### 重载退出验证

启动：

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

在启动期后台同步仍在进行时发送中断，日志确认：

- 启动任务被取消
- 调度器正常关闭
- 数据库连接正常关闭
- `Application shutdown complete`

### 健康检查验证

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:3000/api/health
```

两个接口均返回成功。

## 关联归档

- `docs/archive/chats/2026-03-22-backend-reload-hang-fix.md`
