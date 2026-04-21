import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_news_analyst_module():
    langchain_core_prompts = types.ModuleType("langchain_core.prompts")

    class ChatPromptTemplate:
        @classmethod
        def from_messages(cls, messages):
            return cls()

        def partial(self, **kwargs):
            return self

        def __or__(self, other):
            return other

    class MessagesPlaceholder:
        def __init__(self, variable_name):
            self.variable_name = variable_name

    langchain_core_prompts.ChatPromptTemplate = ChatPromptTemplate
    langchain_core_prompts.MessagesPlaceholder = MessagesPlaceholder
    sys.modules["langchain_core.prompts"] = langchain_core_prompts

    langchain_core_messages = types.ModuleType("langchain_core.messages")

    class AIMessage:
        def __init__(self, content="", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

    langchain_core_messages.AIMessage = AIMessage
    sys.modules["langchain_core.messages"] = langchain_core_messages

    logging_init = types.ModuleType("tradingagents.utils.logging_init")

    class DummyLogger:
        def info(self, *a, **k): pass
        def debug(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass

    logging_init.get_logger = lambda name: DummyLogger()
    sys.modules["tradingagents.utils.logging_init"] = logging_init

    tool_logging = types.ModuleType("tradingagents.utils.tool_logging")
    tool_logging.log_analyst_module = lambda name: (lambda fn: fn)
    sys.modules["tradingagents.utils.tool_logging"] = tool_logging

    unified_news_tool = types.ModuleType("tradingagents.tools.unified_news_tool")

    def create_unified_news_tool(toolkit):
        def tool(**kwargs):
            return "mock news"
        tool.name = "get_stock_news_unified"
        return tool

    unified_news_tool.create_unified_news_tool = create_unified_news_tool
    sys.modules["tradingagents.tools.unified_news_tool"] = unified_news_tool

    stock_utils = types.ModuleType("tradingagents.utils.stock_utils")

    class StockUtils:
        @staticmethod
        def get_market_info(ticker):
            return {"market_name": "中国A股", "is_china": True, "is_hk": False, "is_us": False}

    stock_utils.StockUtils = StockUtils
    sys.modules["tradingagents.utils.stock_utils"] = stock_utils

    google_tool_handler = types.ModuleType("tradingagents.agents.utils.google_tool_handler")

    class GoogleToolCallHandler:
        @staticmethod
        def is_google_model(llm):
            return False

    google_tool_handler.GoogleToolCallHandler = GoogleToolCallHandler
    sys.modules["tradingagents.agents.utils.google_tool_handler"] = google_tool_handler

    interface_module = types.ModuleType("tradingagents.dataflows.interface")
    interface_module.get_china_stock_info_unified = lambda ticker: "股票名称: 工业富联\n"
    sys.modules["tradingagents.dataflows.interface"] = interface_module

    path = Path(__file__).resolve().parents[1] / "tradingagents" / "agents" / "analysts" / "news_analyst.py"
    spec = spec_from_file_location("news_analyst_under_test", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DummyResult:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class DummyBoundLLM:
    def __init__(self, result):
        self._result = result

    def invoke(self, payload):
        return self._result


class DummyLLM:
    def __init__(self, result):
        self._result = result
        self.__class__.__name__ = "DummyLLM"

    def bind_tools(self, tools):
        return DummyBoundLLM(self._result)


def test_news_analyst_passthroughs_tool_calls_without_empty_report():
    module = _load_news_analyst_module()
    result = DummyResult(content="", tool_calls=[{"name": "get_stock_news_unified", "args": {"stock_code": "601138"}}])
    llm = DummyLLM(result)
    node = module.create_news_analyst(llm, toolkit=None)

    output = node({
        "trade_date": "2026-04-20",
        "company_of_interest": "601138",
        "session_id": "test",
        "messages": [],
        "news_tool_call_count": 0,
    })

    assert "news_report" not in output
    assert output["news_tool_call_count"] == 1
    assert output["messages"][0].tool_calls
