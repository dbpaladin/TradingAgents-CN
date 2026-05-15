import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_create_msg_delete():
    messages_module = types.ModuleType("langchain_core.messages")

    class RemoveMessage:
        def __init__(self, id):
            self.id = id

    class HumanMessage:
        def __init__(self, content="", id=None):
            self.content = content
            self.id = id or "human"

    class BaseMessage:
        pass

    class ToolMessage:
        pass

    class AIMessage:
        pass

    messages_module.RemoveMessage = RemoveMessage
    messages_module.HumanMessage = HumanMessage
    messages_module.BaseMessage = BaseMessage
    messages_module.ToolMessage = ToolMessage
    messages_module.AIMessage = AIMessage
    sys.modules["langchain_core.messages"] = messages_module

    prompts_module = types.ModuleType("langchain_core.prompts")
    prompts_module.ChatPromptTemplate = object
    prompts_module.MessagesPlaceholder = object
    sys.modules["langchain_core.prompts"] = prompts_module

    tools_module = types.ModuleType("langchain_core.tools")
    tools_module.tool = lambda fn: fn
    sys.modules["langchain_core.tools"] = tools_module

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = object
    sys.modules["langchain_openai"] = langchain_openai

    pandas_module = types.ModuleType("pandas")
    sys.modules["pandas"] = pandas_module

    dateutil_module = types.ModuleType("dateutil")
    relativedelta_module = types.ModuleType("dateutil.relativedelta")

    class relativedelta:
        def __init__(self, *args, **kwargs):
            pass

    relativedelta_module.relativedelta = relativedelta
    sys.modules["dateutil"] = dateutil_module
    sys.modules["dateutil.relativedelta"] = relativedelta_module

    dataflows_pkg = types.ModuleType("tradingagents.dataflows")
    interface_module = types.ModuleType("tradingagents.dataflows.interface")
    dataflows_pkg.interface = interface_module
    sys.modules["tradingagents.dataflows"] = dataflows_pkg
    sys.modules["tradingagents.dataflows.interface"] = interface_module

    default_config = types.ModuleType("tradingagents.default_config")
    default_config.DEFAULT_CONFIG = {}
    sys.modules["tradingagents.default_config"] = default_config

    tool_logging = types.ModuleType("tradingagents.utils.tool_logging")
    tool_logging.log_tool_call = lambda *args, **kwargs: (lambda fn: fn)
    tool_logging.log_analysis_step = lambda *args, **kwargs: (lambda fn: fn)
    sys.modules["tradingagents.utils.tool_logging"] = tool_logging

    logging_manager = types.ModuleType("tradingagents.utils.logging_manager")

    class DummyLogger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

    logging_manager.get_logger = lambda name=None: DummyLogger()
    sys.modules["tradingagents.utils.logging_manager"] = logging_manager

    logging_init = types.ModuleType("tradingagents.utils.logging_init")
    logging_init.get_logger = lambda name=None: DummyLogger()
    sys.modules["tradingagents.utils.logging_init"] = logging_init

    path = Path(__file__).resolve().parents[1] / "tradingagents" / "agents" / "utils" / "agent_utils.py"
    spec = spec_from_file_location("agent_utils_under_test", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.create_msg_delete, HumanMessage, RemoveMessage


def test_create_msg_delete_can_write_news_fallback_state():
    create_msg_delete, HumanMessage, RemoveMessage = _load_create_msg_delete()

    def build_news_fallback(state):
        if state.get("news_report"):
            return {}
        return {"news_report": "## 601138 新闻分析降级报告\n\n- 问题：新闻正文缺失。\n"}

    delete_node = create_msg_delete(state_update_factory=build_news_fallback)
    state = {
        "messages": [HumanMessage(content="old-1", id="m1"), HumanMessage(content="old-2", id="m2")],
        "news_report": "",
    }

    output = delete_node(state)

    assert output["news_report"].startswith("## 601138 新闻分析降级报告")
    assert isinstance(output["messages"][-1], HumanMessage)
    assert output["messages"][-1].content == "Continue"
    assert all(isinstance(msg, RemoveMessage) for msg in output["messages"][:-1])
