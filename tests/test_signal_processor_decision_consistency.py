import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

langchain_openai_stub = types.ModuleType("langchain_openai")
langchain_openai_stub.ChatOpenAI = object
sys.modules.setdefault("langchain_openai", langchain_openai_stub)


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
