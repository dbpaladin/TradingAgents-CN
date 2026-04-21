#!/usr/bin/env python3
"""
测试条件逻辑修复 - 防止分析师节点无限循环

测试场景：
1. 报告未生成时，有 tool_calls 应该继续执行工具
2. 报告已生成时，即使有 tool_calls 也应该停止循环
3. 报告长度不足时，应该继续执行
4. 报告长度足够时，应该停止循环
"""

from unittest.mock import Mock
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


def load_conditional_logic():
    agent_states = types.ModuleType("tradingagents.agents.utils.agent_states")
    agent_states.AgentState = dict
    sys.modules["tradingagents.agents.utils.agent_states"] = agent_states

    logging_init = types.ModuleType("tradingagents.utils.logging_init")

    class DummyLogger:
        def debug(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    logging_init.get_logger = lambda name: DummyLogger()
    sys.modules["tradingagents.utils.logging_init"] = logging_init

    path = Path(__file__).resolve().parents[1] / "tradingagents" / "graph" / "conditional_logic.py"
    spec = spec_from_file_location("conditional_logic_under_test", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.ConditionalLogic


def create_mock_message(has_tool_calls=False):
    """创建模拟消息"""
    message = Mock()
    message.content = ""
    if has_tool_calls:
        message.tool_calls = [{"name": "test_tool", "args": {}}]
    else:
        message.tool_calls = []
    return message


def test_fundamentals_no_report_with_tool_calls():
    """测试：基本面分析 - 没有报告，有 tool_calls -> 应该继续执行工具"""
    ConditionalLogic = load_conditional_logic()
    logic = ConditionalLogic()
    state = {
        "messages": [create_mock_message(has_tool_calls=True)],
        "fundamentals_report": ""
    }
    
    result = logic.should_continue_fundamentals(state)
    assert result == "tools_fundamentals", "没有报告时应该执行工具"
    print("✅ 测试通过：没有报告时继续执行工具")


def test_fundamentals_has_report_with_tool_calls():
    """测试：基本面分析 - 有报告，有 tool_calls -> 应该停止循环"""
    ConditionalLogic = load_conditional_logic()
    logic = ConditionalLogic()
    state = {
        "messages": [create_mock_message(has_tool_calls=True)],
        "fundamentals_report": "这是一个完整的基本面分析报告" * 10  # 长度 > 100
    }
    
    result = logic.should_continue_fundamentals(state)
    assert result == "Msg Clear Fundamentals", "有报告时应该停止循环"
    print("✅ 测试通过：有报告时停止循环")


def test_all_analysts():
    """测试：所有分析师的行为一致性"""
    ConditionalLogic = load_conditional_logic()
    logic = ConditionalLogic()
    message = create_mock_message(has_tool_calls=True)
    long_report = "完整的分析报告" * 20
    
    # 测试所有分析师
    analysts = [
        ("market", "market_report", logic.should_continue_market, "Msg Clear Market", "tools_market"),
        ("social", "sentiment_report", logic.should_continue_social, "Msg Clear Social", "tools_social"),
        ("news", "news_report", logic.should_continue_news, "Msg Clear News", "tools_news"),
        ("fundamentals", "fundamentals_report", logic.should_continue_fundamentals, "Msg Clear Fundamentals", "tools_fundamentals"),
    ]
    
    for analyst_name, report_field, check_func, expected_clear, expected_tools in analysts:
        # 有报告时应该停止
        state = {
            "messages": [message],
            report_field: long_report
        }
        result = check_func(state)
        assert result == expected_clear, f"{analyst_name} 分析师有报告时应该停止循环"
        
        # 没有报告时应该继续
        state[report_field] = ""
        result = check_func(state)
        assert result == expected_tools, f"{analyst_name} 分析师没有报告时应该执行工具"
    
    print("✅ 测试通过：所有分析师行为一致")


def test_news_reaches_limit_without_report_returns_clear_branch():
    """测试：新闻分析达到工具上限但报告为空时，应走图中已注册的清理分支。"""
    ConditionalLogic = load_conditional_logic()
    logic = ConditionalLogic()
    state = {
        "messages": [create_mock_message(has_tool_calls=True)],
        "news_report": "",
        "news_tool_call_count": 3,
    }

    result = logic.should_continue_news(state)
    assert result == "Msg Clear News", "新闻报告为空且达到上限时应走清理分支，避免非法分支返回"
    print("✅ 测试通过：新闻达到上限但无报告时走清理分支")


def _run_conditional_logic_fix_checks():
    """运行条件逻辑回归检查。"""
    print("🔧 测试条件逻辑修复 - 防止分析师节点无限循环\n")
    
    try:
        test_fundamentals_no_report_with_tool_calls()
        test_fundamentals_has_report_with_tool_calls()
        test_all_analysts()
        
        print("\n🎉 所有测试通过！")
        print("\n📋 修复内容:")
        print("✅ 添加了报告完成检查")
        print("✅ 防止了无限循环")
        print("✅ 所有分析师节点都已修复")
        return True
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return False
    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_conditional_logic_fix():
    """主测试函数 - 运行所有测试"""
    assert _run_conditional_logic_fix_checks()


if __name__ == "__main__":
    # 运行测试
    success = _run_conditional_logic_fix_checks()
    exit(0 if success else 1)
