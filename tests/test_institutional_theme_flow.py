from types import SimpleNamespace

from tradingagents.graph.conditional_logic import ConditionalLogic


def test_institutional_theme_conditional_routes_to_tools():
    logic = ConditionalLogic()
    last_message = SimpleNamespace(tool_calls=[{"name": "get_a_share_institutional_theme_opportunities"}])
    state = {
        "messages": [last_message],
        "institutional_theme_report": "",
        "institutional_theme_tool_call_count": 0,
    }

    assert logic.should_continue_institutional_theme(state) == "tools_institutional_theme"


def test_institutional_theme_conditional_finishes_with_report():
    logic = ConditionalLogic()
    last_message = SimpleNamespace(tool_calls=[])
    state = {
        "messages": [last_message],
        "institutional_theme_report": "y" * 220,
        "institutional_theme_tool_call_count": 1,
    }

    assert logic.should_continue_institutional_theme(state) == "Msg Clear Institutional_theme"
