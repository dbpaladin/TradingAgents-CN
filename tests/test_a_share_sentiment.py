import pandas as pd

from tradingagents.tools.analysis.a_share_sentiment import (
    AShareSentimentAnalyzer,
    normalize_a_share_symbol,
)
from tradingagents.utils.stock_utils import StockUtils


class _DummyAK:
    pass


def test_normalize_a_share_symbol():
    assert normalize_a_share_symbol("600519.SH") == "600519"
    assert normalize_a_share_symbol("000001.XSHE") == "000001"
    assert StockUtils.get_market_info("000001.SZ")["is_china"] is True


def test_build_snapshot_classifies_extreme_fear():
    analyzer = AShareSentimentAnalyzer(_DummyAK())
    data = {
        "zt": pd.DataFrame([{"代码": "000001", "连板数": 1, "封板资金": 1000, "成交额": 5000, "所属行业": "银行"}]),
        "prev_zt": pd.DataFrame([{"代码": "000002", "涨跌幅": -6.0}, {"代码": "000003", "涨跌幅": -2.0}]),
        "broken": pd.DataFrame([{"代码": str(i), "涨跌幅": -4.0} for i in range(20)]),
        "dt": pd.DataFrame([{"代码": str(i)} for i in range(15)]),
        "strong": pd.DataFrame([{"代码": "300001"}]),
        "lhb": pd.DataFrame(),
    }

    snapshot = analyzer.build_snapshot("2026-03-20", data)

    assert snapshot.cycle_stage == "冰点"
    assert snapshot.market_emotion == "extreme_fear"
    assert snapshot.risk_level == "高风险"


def test_render_markdown_includes_stock_focus():
    analyzer = AShareSentimentAnalyzer(_DummyAK())
    data = {
        "zt": pd.DataFrame(
            [
                {
                    "代码": "000001",
                    "名称": "平安银行",
                    "连板数": 3,
                    "封板资金": 300000000,
                    "成交额": 1000000000,
                    "炸板次数": 0,
                    "首次封板时间": "093000",
                    "所属行业": "银行",
                },
                {
                    "代码": "000002",
                    "名称": "万科A",
                    "连板数": 3,
                    "封板资金": 200000000,
                    "成交额": 1200000000,
                    "炸板次数": 1,
                    "首次封板时间": "094500",
                    "所属行业": "银行",
                },
            ]
        ),
        "prev_zt": pd.DataFrame([{"代码": "000010", "涨跌幅": 5.0}, {"代码": "000011", "涨跌幅": 3.0}]),
        "broken": pd.DataFrame([{"代码": "000012", "涨跌幅": 1.0}]),
        "dt": pd.DataFrame([{"代码": "000013"}]),
        "strong": pd.DataFrame([{"代码": "000001"}]),
        "lhb": pd.DataFrame([{"代码": "000001", "上榜次数": 4, "龙虎榜净买额": 12345678}]),
    }

    snapshot = analyzer.build_snapshot("2026-03-20", data)
    report = analyzer.render_markdown("000001.SZ", "2026-03-20", snapshot, data)

    assert "A股盘面情绪分析" in report
    assert "个股情绪定位" in report
    assert "估算龙头分" in report
    assert "龙虎榜上榜次数" in report
