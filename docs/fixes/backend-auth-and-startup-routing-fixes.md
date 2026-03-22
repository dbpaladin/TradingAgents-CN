# 后端认证、启动与路由修复说明

## 概述

2026-03-19 这几次提交主要修复的是接入层和启动层问题，影响范围虽然不大，但很容易直接导致“服务起不来”或“接口不可用”。

本说明用于补齐以下几类改动的背景：

- 注册接口缺失
- `redirect_slashes` / `strict_slashes` 相关兼容问题
- 启动期 backfill 阻塞导致的热重载卡死
- 健康检查与前端依赖链路调整

## 1. 注册接口补齐

后端认证路由现在已经提供：

- `POST /api/auth/login`
- `POST /api/auth/register`

其中注册接口位于认证路由中，主要用于创建用户并记录注册日志。

适用场景：

- 首次初始化账号
- 测试环境快速注册
- 前端认证流程联调

如果你的前端或自动化脚本曾经依赖注册接口但收到 `405` 或 `404`，应优先确认是否已切换到当前后端版本。

## 2. 路由斜杠兼容修复

此前在 FastAPI 路由行为上做过一轮修正，目标是避免：

- 非预期的 `405 Method Not Allowed`
- 由于无效参数导致的启动失败
- 前端与代理层访问同一路径时行为不一致

当前做法是：

- 移除无效的 `strict_slashes` 用法
- 明确 `redirect_slashes` 的行为
- 减少由于尾斜杠和代理转发造成的路径歧义

如果你在代理层或脚本层固定写了带斜杠/不带斜杠的 URL，升级后建议统一按当前接口路径校验一次。

## 3. 启动期 backfill 改为后台任务

为了避免启动阶段直接等待行情补数，后端已经把启动期 backfill 调整为后台托管任务。

这样做的目的：

- 避免应用启动阶段长时间阻塞
- 避免开发环境热重载时卡住
- 在外部数据源暂时异常时，尽量不影响 API 本身启动

当前行为特点：

- 应用会先完成主要启动流程
- backfill 在后台执行
- 关闭应用或 reload 时，会统一取消这类启动后台任务

这也是最近修复 “backend reload hang” 的关键一环。

## 4. 健康检查与前端依赖链路调整

Docker / 前端侧这几次修正的目的，是让健康检查更贴近真实可用性：

- 前端容器检查 `/health`
- 后端容器检查 `/api/health`
- 前端不再强依赖错误的后端检查方式来判断自身是否可用

这样可以减少：

- 容器明明能用却一直显示 unhealthy
- 前端服务因为后端尚未就绪而被误判失败
- 部署排障时前后端问题混在一起

## 建议排查顺序

如果你遇到“服务能启动但页面/接口异常”，建议按下面顺序排查：

1. `curl http://localhost:8000/api/health`
2. 确认认证接口路径是否为 `/api/auth/login` 和 `/api/auth/register`
3. 检查前端请求路径是否仍依赖旧的绝对地址或错误尾斜杠
4. 查看后端启动日志里是否有启动期 backfill 警告

## 相关文档

- `docs/deployment/docker/frontend-api-proxy-update.md`
- `docs/deployment/operations/service_control.md`
- `docs/fixes/backend-reload-hang-fix.md`
- `docs/releases/CHANGELOG.md`
