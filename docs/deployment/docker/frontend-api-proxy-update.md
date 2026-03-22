# Docker 前端代理与健康检查更新说明

## 概述

最近一轮 Docker 部署链路做了几项关键调整，目标是让前端、后端、Nginx 和健康检查的行为更一致，减少“页面能打开但 API 不通”或“容器健康检查误判”的问题。

## 关键变化

### 前端改用相对 API 路径

Docker 前端容器现在默认使用相对 API 路径：

```env
VITE_API_BASE_URL=
```

这样做的好处：

- 前端不再把后端地址写死为某个宿主机端口
- 更适合通过 Nginx 或统一域名反向代理
- 可以减少环境切换时的地址漂移问题

## Nginx 代理规则

当前 `docker/nginx.conf` 中，`/api` 会被转发到后端容器：

- `/api/*` -> `http://backend:8000`

这意味着在浏览器侧只需要访问：

- 前端页面：`/`
- 后端接口：`/api/*`

而不是在前端代码里直接写死 `http://localhost:8000`

## 健康检查修正

### 前端健康检查

前端容器当前使用：

- `/health`

该路径由 Nginx 直接返回 `200 ok`，用于快速确认静态页面和 Nginx 本身可用。

### 后端健康检查

后端容器当前使用：

- `/api/health`

用于确认 FastAPI 服务是否已经就绪。

## 推荐验证步骤

部署后建议至少验证以下 4 项：

```bash
docker-compose ps
docker-compose logs -f backend
docker-compose logs -f frontend
curl http://localhost:8000/api/health
```

如果前端经 Nginx 对外，还建议在浏览器开发者工具中确认：

- 页面请求 `/api/*` 时是否返回 200
- 是否仍存在写死到 `localhost:8000` 的请求

## 常见故障

### 页面能打开，但接口全是 404/502

优先检查：

- Nginx 是否正确加载了 `docker/nginx.conf`
- `backend` 服务是否已经健康
- 前端是否仍残留绝对 API 地址

### 容器一直不健康

优先检查：

- 前端 `/health` 是否可访问
- 后端 `/api/health` 是否可访问
- `docker-compose.yml` 中健康检查路径是否与实际服务一致

## 适用场景

这套方式适合：

- Docker Compose 本地部署
- Nginx 统一入口部署
- 后续切换到同域名反向代理的测试或生产环境
