# 会话归档：后端重载卡死导致前端误报无法连接

- 日期：2026-03-22
- 主题：修复 FastAPI 后端在热重载/重启时卡死，导致前端提示“无法连接到后端服务”
- 执行方式：定位根因、修改代码、完成可复现验证

## 背景

用户使用私有 `TUSHARE_ENDPOINT` 替换官方 endpoint，这一配置本身是正常的，但系统经常出现以下现象：

1. 前端弹出“后端服务连接失败”。
2. `8000` 端口仍然在监听。
3. `/api/health` 长时间超时。
4. 日志停在 `Waiting for background tasks to complete`。

## 根因

问题不在私有 Tushare endpoint 本身，而在应用生命周期管理：

1. `app/main.py` 的 `lifespan(...)` 启动阶段会直接创建两个后台任务：
   - 启动期行情回填
   - 启动期股票基础信息同步
2. 这些任务原来通过裸 `asyncio.create_task(...)` 启动，没有纳入统一管理。
3. 当 `uvicorn --reload` 或进程重启时，旧 worker 进入 shutdown。
4. 由于这些后台任务仍在执行 Tushare / AKShare / BaoStock 网络请求，旧 worker 无法及时退出。
5. 最终表现为：
   - 旧进程卡在 shutdown
   - 端口/父进程状态看似还在
   - 新 worker 无法稳定接管
   - 前端健康检查超时并误判为“连不上后端”

## 修改内容

文件：
- `app/main.py`
- `app/services/multi_source_basics_sync_service.py`
- `app/services/quotes_ingestion_service.py`

核心修改：

1. 新增启动任务管理辅助函数：
   - `_create_managed_startup_task(...)`
   - `_cancel_managed_startup_tasks(...)`
2. 将以下启动阶段后台任务纳入统一管理：
   - `startup_quotes_backfill`
   - `startup_stock_basics_sync`
3. 在 shutdown 阶段主动取消仍在运行的启动任务，并限时等待退出。
4. 为任务补充 `asyncio.CancelledError` 处理和更清晰的日志。

后续补充修改：

5. 将启动期与补数链路中的同步数据源调用迁移到 `asyncio.to_thread(...)`：
   - 避免私有 Tushare endpoint 探测直接阻塞事件循环
   - 避免后台任务把主服务端口监听和健康检查拖慢

## 关键结论

- 私有 `TUSHARE_ENDPOINT` 仍然保留，不需要回退到官方 endpoint。
- 真正的问题是“启动任务没有在 shutdown/reload 时被取消”。
- 修复后，即使后台同步仍在运行，进程也可以正常退出并完成重载。

## 验证

### 1. 语法校验

已执行：

```bash
python -m py_compile app/main.py app/services/multi_source_basics_sync_service.py app/services/quotes_ingestion_service.py
```

### 2. 可复现验证

已执行：

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

在启动期同步任务运行中手动发送中断信号，日志结果显示：

- 应用进入 `Shutting down`
- 执行 `🧹 开始取消 1 个启动后台任务`
- 输出 `🛑 启动期股票基础信息同步任务收到取消信号`
- 输出 `Application shutdown complete`

说明旧 worker 不再卡死在：

```text
Waiting for background tasks to complete
```

### 3. 当前服务健康检查

已验证以下接口恢复正常：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:3000/api/health
```

均返回成功 JSON。

## 备注

- 工作区中存在与本次修复无关的 `reports/` 目录变更。
- 本次提交不会包含这些无关文件。
