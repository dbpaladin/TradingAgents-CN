# 文档更新策略

## 目标

把“代码改完后想起来再补文档”改成“提交前就知道该补哪些文档”。

这份规则重点覆盖四类高影响改动：

- 功能行为变化
- 部署或启动方式变化
- 配置项变化
- 面向用户或运维的操作变化

## 基本原则

以下任一情况发生时，提交中应当同时包含至少一份相关文档更新：

1. 新增或删除用户可见功能
2. 修改已有功能的行为、入口、参数、默认值或限制
3. 修改部署、启动、停止、代理、容器、端口或服务管理方式
4. 修改配置项、环境变量、密钥来源、优先级或配置解析逻辑
5. 修复会影响用户结果、系统稳定性、运维流程的缺陷

## 最低要求

满足上面任一条件时，至少更新以下文档中的一个：

- `README.md`
- `docs/releases/CHANGELOG.md`
- `docs/README.md`
- 对应专题文档，例如 `docs/configuration/`、`docs/deployment/`、`docs/frontend/`、`docs/features/`、`docs/fixes/`

如果改动较大，建议同时更新：

- 一个入口文档
- 一个专题文档
- 一条变更记录

## 路径到文档的推荐映射

### 后端与核心分析逻辑

代码路径：

- `app/`
- `tradingagents/`
- `cli/`
- `main.py`

优先更新：

- `docs/features/`
- `docs/fixes/`
- `docs/usage/`
- `docs/releases/CHANGELOG.md`

### 前端与交互流程

代码路径：

- `frontend/`
- `web/`

优先更新：

- `docs/frontend/`
- `docs/features/`
- `docs/usage/`
- `docs/releases/CHANGELOG.md`

### 部署与运维

代码路径：

- `docker/`
- `nginx/`
- `docker-compose*.yml`
- `Dockerfile*`
- `scripts/startup/`
- 服务管理脚本

优先更新：

- `docs/deployment/`
- `docs/docker/`
- `docs/guides/docker-deployment-guide.md`
- `docs/releases/CHANGELOG.md`

### 配置系统

代码路径：

- `config/`
- `.env.example`
- `app/core/`
- 配置相关服务

优先更新：

- `config/README.md`
- `docs/configuration/`
- `docs/guides/config-management-guide.md`
- `docs/releases/CHANGELOG.md`

## 当前自动检查

仓库已增加轻量检查脚本：

```bash
python scripts/ci/check_docs_update.py
```

默认比较 `HEAD~1..HEAD`。也可以显式指定范围：

```bash
python scripts/ci/check_docs_update.py --base origin/main --head HEAD
```

该检查会在以下情况下失败：

- 识别到高影响代码路径发生变化
- 但本次改动中没有任何文档文件更新

## 不强制补长文的情况

以下情况通常不需要单独写详细文档，但仍建议至少补一条简短变更说明：

- 纯重构且无行为变化
- 仅测试代码变更
- 锁文件更新
- 内部调试文件、报表、历史会话归档

## 提交前自检

提交前建议快速确认：

1. 这次改动是否改变了用户看到的行为？
2. 这次改动是否影响部署、配置、启动或排障？
3. 文档入口是否能让后来的人快速知道变化？
4. `docs/releases/CHANGELOG.md` 是否至少留下了可追踪记录？
