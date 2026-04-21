import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

langchain_openai_stub = types.ModuleType("langchain_openai")
langchain_openai_stub.ChatOpenAI = object
sys.modules["langchain_openai"] = langchain_openai_stub

logging_init_stub = types.ModuleType("tradingagents.utils.logging_init")


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


logging_init_stub.get_logger = lambda name: DummyLogger()
sys.modules["tradingagents.utils.logging_init"] = logging_init_stub

tool_logging_stub = types.ModuleType("tradingagents.utils.tool_logging")
tool_logging_stub.log_graph_module = lambda name: (lambda fn: fn)
sys.modules["tradingagents.utils.tool_logging"] = tool_logging_stub

prompt_context_stub = types.ModuleType("tradingagents.agents.utils.prompt_context")
prompt_context_stub.compact_text = lambda text, max_chars, label: text
sys.modules["tradingagents.agents.utils.prompt_context"] = prompt_context_stub

stock_utils_stub = types.ModuleType("tradingagents.utils.stock_utils")


class StockUtils:
    @staticmethod
    def get_market_info(symbol):
        return {
            "market_name": "中国A股",
            "currency_name": "人民币",
            "currency_symbol": "¥",
            "is_china": True,
        }


stock_utils_stub.StockUtils = StockUtils
sys.modules["tradingagents.utils.stock_utils"] = stock_utils_stub


MODULE_PATH = Path(__file__).resolve().parents[1] / "tradingagents" / "graph" / "signal_processing.py"
SPEC = spec_from_file_location("signal_processing_under_test", MODULE_PATH)
MODULE = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
SignalProcessor = MODULE.SignalProcessor


class DummyLLM:
    def __init__(self, response_text: str):
        self.response_text = response_text

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        return SimpleNamespace(content=self.response_text)


def test_signal_processor_prefers_core_target_and_repairs_hold_conflict():
    llm = DummyLLM(
        '{"action":"持有","target_price":55,"confidence":0.78,"risk_score":0.65,"reasoning":"技术偏强但建议减仓观察"}'
    )
    processor = SignalProcessor(llm)

    signal = """
    最终建议：持有
    持仓者建议：61–62.5分批减仓锁利，保留≤20%观察仓。
    空仓者建议：不追高，等待确认。
    当前价格：61.51
    核心目标价（基准情景）：55元
    """

    result = processor.process_signal(signal, "601138")

    assert result["target_price"] == 55.0
    assert result["action"] == "卖出"
    assert "持仓者：61–62.5分批减仓锁利" in result["execution_advice"]
    assert "空仓者：不追高，等待确认" in result["execution_advice"]


def test_signal_processor_extracts_benchmark_target_from_text_when_json_missing():
    llm = DummyLLM(
        '{"action":"卖出","target_price":null,"confidence":0.7,"risk_score":0.5,"reasoning":"按原文抽取"}'
    )
    processor = SignalProcessor(llm)

    signal = """
    最终建议：卖出
    当前价格：61.51
    目标价格分析：未来1-3个月核心合理区间是53-58，基准目标价55。
    """

    result = processor.process_signal(signal, "601138")

    assert result["action"] == "卖出"
    assert result["target_price"] == 55.0


def test_signal_processor_repairs_hold_when_execution_requires_exit():
    llm = DummyLLM(
        '{"action":"持有","target_price":63,"confidence":0.7,"risk_score":0.65,"reasoning":"减仓观察"}'
    )
    processor = SignalProcessor(llm)

    signal = """
    最终建议：持有
    当前价格：61.10
    持仓者建议：现有仓位先降至0–2成；反弹至62.5–63.3优先减/清；收盘跌破59.7清仓。
    空仓者建议：等待确认，否则继续观望。
    核心目标价（基准情景）：63元
    """

    result = processor.process_signal(signal, "601138")

    assert result["action"] == "卖出"
    assert "修正为“卖出”" in result["consistency_note"]
    assert "持仓者：现有仓位先降至0–2成" in result["execution_advice"]
    assert "空仓者：等待确认" in result["execution_advice"]


def test_signal_processor_prefers_benchmark_target_over_stop_loss_price():
    llm = DummyLLM(
        '{"action":"持有","target_price":56.13,"confidence":0.7,"risk_score":0.5,"reasoning":"基于综合分析的投资建议"}'
    )
    processor = SignalProcessor(llm)

    signal = """
    最终建议：持有
    当前价格：61.41
    止损位：¥56.13（跌破需果断止损）
    基准情景目标价：¥65
    保守情景：¥50-55
    乐观情景：¥70-80
    """

    result = processor.process_signal(signal, "601138")

    assert result["action"] == "持有"
    assert result["target_price"] == 65.0
