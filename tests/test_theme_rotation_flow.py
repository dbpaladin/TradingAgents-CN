from types import SimpleNamespace

from tradingagents.graph.conditional_logic import ConditionalLogic


def test_theme_rotation_conditional_routes_to_tools_when_needed():
    logic = ConditionalLogic()
    last_message = SimpleNamespace(tool_calls=[{"name": "get_a_share_theme_rotation"}])
    state = {
        "messages": [last_message],
        "theme_rotation_report": "",
        "theme_rotation_tool_call_count": 0,
    }

    assert logic.should_continue_theme_rotation(state) == "tools_theme_rotation"


def test_theme_rotation_conditional_finishes_when_report_ready():
    logic = ConditionalLogic()
    last_message = SimpleNamespace(tool_calls=[])
    state = {
        "messages": [last_message],
        "theme_rotation_report": "x" * 200,
        "theme_rotation_tool_call_count": 1,
    }

    assert logic.should_continue_theme_rotation(state) == "Msg Clear Theme_rotation"
