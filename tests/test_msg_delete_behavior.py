from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from tradingagents.agents.utils.agent_utils import create_msg_delete


def test_create_msg_delete_clears_messages_by_default():
    delete_messages = create_msg_delete()
    state = {
        "messages": [
            HumanMessage(content="hello", id="msg-1"),
            AIMessage(content="world", id="msg-2"),
        ]
    }

    result = delete_messages(state)

    assert "messages" in result
    assert len(result["messages"]) == 3
    assert isinstance(result["messages"][0], RemoveMessage)
    assert result["messages"][0].id == "msg-1"
    assert isinstance(result["messages"][1], RemoveMessage)
    assert result["messages"][1].id == "msg-2"
    assert isinstance(result["messages"][2], HumanMessage)
    assert result["messages"][2].content == "Continue"


def test_create_msg_delete_parallel_safe_mode_skips_removal():
    delete_messages = create_msg_delete(parallel_safe=True)
    state = {
        "messages": [
            HumanMessage(content="hello", id="msg-1"),
            AIMessage(content="world", id="msg-2"),
        ]
    }

    assert delete_messages(state) == {}
