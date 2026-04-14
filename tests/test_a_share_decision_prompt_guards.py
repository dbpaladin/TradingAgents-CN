from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_trader_prompt_contains_conflict_and_low_sample_guards():
    content = _read("tradingagents/agents/trader/trader.py")

    assert "低样本弱证据" in content
    assert "持仓者减仓观察、空仓者等待确认" in content
    assert "至少两类独立负面证据同时成立" in content
    assert "保守/基准/乐观三种估值情景" in content


def test_risk_manager_prompt_contains_conflict_and_low_sample_guards():
    content = _read("tradingagents/agents/managers/risk_manager.py")

    assert "低样本弱证据" in content
    assert "持仓者减仓观察 / 空仓者等待确认" in content
    assert "至少两类独立负面证据同时成立" in content
    assert "保守/基准/乐观三种估值情景" in content


def test_fundamentals_prompt_requires_three_scenarios():
    content = _read("tradingagents/agents/analysts/fundamentals_analyst.py")

    assert "保守/基准/乐观三种估值情景" in content
    assert "基准情景目标价" in content
    assert "不允许只给单一静态目标价" in content


def test_fund_flow_prompt_mentions_low_sample_weak_evidence():
    content = _read("tradingagents/agents/analysts/fund_flow_analyst.py")

    assert "低样本弱证据" in content
    assert "数据源体检" in content
