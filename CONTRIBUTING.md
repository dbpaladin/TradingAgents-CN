# 贡献指南

欢迎提交代码、文档、测试、问题反馈和改进建议。

## 提交前请先确认

1. 功能、配置、部署、运维行为是否发生变化
2. 如果发生变化，是否同步更新了相关文档
3. 是否补充了必要测试

## 文档更新要求

当改动涉及以下内容时，请同步更新文档：

- 新功能或功能下线
- 用户可见行为变化
- 配置项、环境变量、默认值变化
- 部署、启动、停止、代理、容器、端口变化
- 会影响结果、稳定性或排障流程的修复

最低建议是至少更新其中一项：

- `README.md`
- `docs/README.md`
- `docs/releases/CHANGELOG.md`
- 对应专题文档

详细规则见：

- `docs/maintenance/documentation-update-policy.md`

## 本地检查

可以在提交前运行：

```bash
python scripts/ci/check_docs_update.py
```

如果你准备提交一个大改动，建议显式对比主分支：

```bash
python scripts/ci/check_docs_update.py --base origin/main --head HEAD
```
