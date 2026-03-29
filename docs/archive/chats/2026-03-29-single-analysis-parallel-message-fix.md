# 会话归档：单股分析并行消息污染修复

- 日期：2026-03-29
- 主题：单股分析在并行分析师场景下报错，修复消息状态污染与工具调用闭环问题
- 执行方式：日志排障 + 同参数复现 + 图执行链路修复 + 回归测试 + 文档归档

## 用户诉求

1. 单股分析这两天出现报错，需要修复。
2. 怀疑与近期代码改动有关。
3. 修复完成后归档聊天记录并更新相关文档。

## 诊断结论

本次问题并非单纯的数据源失败，而是近期“分析师并行化”改动误伤了正式单股分析链路。

核心链路如下：

- `tradingagents/graph/setup.py` 将正式分析图改成了分析师并行扇出
- `tradingagents/agents/utils/agent_utils.py` 为规避并行 `RemoveMessage` 冲突，将 `Msg Clear` 改为返回空字典
- 多个分析师因此共享并持续累积同一份 `messages`
- 后续某个分析师再次调用 LLM 时，带入了其他分支的 function call，却没有对应 tool output
- OpenAI 兼容接口最终报错：
  - `No tool output found for function call ...`

这也是为什么服务层表面上会看到 `NoneType` 或通用“分析失败”，但真实根因其实是消息污染。

## 已实施修改

### 1) 正式分析图恢复串行

文件：`tradingagents/graph/setup.py`

- `setup_graph()` 恢复为串行分析师链路
- 每个分析师完成后再进入下一个分析师
- 最后一位分析师完成后再汇入 `Bull Researcher`

### 2) 消息清理改为双模式

文件：`tradingagents/agents/utils/agent_utils.py`

- `create_msg_delete(parallel_safe=False)` 默认执行真实消息清理
- `create_msg_delete(parallel_safe=True)` 仅在并行安全模式下返回 `{}`
- 回测轻量图使用并行安全模式
- 正式分析图使用默认清理模式

### 3) 回归测试补齐

文件：`tests/test_msg_delete_behavior.py`

- 覆盖默认清理行为
- 覆盖并行安全行为

## 验证结果

执行测试：

- `./.venv/bin/pytest -q tests/test_msg_delete_behavior.py tests/test_validation_fix.py tests/test_import_fix.py -q`

结果：

- 9 个测试通过

同时使用线上同类参数（A股 `300054`、多分析师、`gpt-5.2`）进行同步复现，确认修复前的真实报错就是并行消息污染触发的 tool-output 缺失。

## 影响范围说明

- **正式单股分析**：已改回串行，优先保证正确性与稳定性
- **回测轻量图**：继续保留并行结构，不回退性能优化
- **后续并行化方向**：若要让正式分析重新并行，需要把消息状态拆成“按分析师隔离”的结构，而不是继续共用全局 `messages`
