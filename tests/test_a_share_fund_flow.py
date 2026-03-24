import pandas as pd

from tradingagents.tools.analysis.a_share_fund_flow import AShareFundFlowAnalyzer


class FakeAK:
    def stock_zt_pool_em(self, date: str):
        return pd.DataFrame([{"代码": "000001"}])

    def stock_zt_pool_zbgc_em(self, date: str):
        return pd.DataFrame([{"代码": "000002"}])

    def stock_zt_pool_strong_em(self, date: str):
        return pd.DataFrame([{"代码": "000001"}])

    def stock_lhb_stock_statistic_em(self, symbol: str):
        return pd.DataFrame(
            [
                {
                    "代码": "000001",
                    "上榜次数": 3,
                    "龙虎榜净买额": 25600000,
                    "买方机构次数": 2,
                    "卖方机构次数": 0,
                }
            ]
        )


class FakeFundFlowAnalyzer(AShareFundFlowAnalyzer):
    def _collect_tushare_context(self, date: str):
        return {
            "moneyflow": pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "net_mf_amount": 18800000},
                ]
            ),
            "margin_detail": pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "融资买入额": 5200000, "融券卖出量": 0},
                ]
            ),
            "hk_hold": pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "持股数变化": 120000},
                ]
            ),
        }


def test_fund_flow_summary_detects_positive_capital_signals():
    analyzer = FakeFundFlowAnalyzer(FakeAK())
    data = analyzer.collect("2026-03-21")

    summary = analyzer.build_summary("000001.SZ", "2026-03-21", data)

    assert summary.stock_status == "涨停池"
    assert summary.lhb_count == 3
    assert summary.institutional_signal == "机构席位偏多"
    assert summary.northbound_signal == "北向资金偏增持"
    assert summary.margin_signal == "融资情绪偏暖"
    assert summary.evidence_completeness_score == 100.0
    assert "龙虎榜" in "".join(summary.evidence)


def test_fund_flow_report_contains_core_sections():
    analyzer = FakeFundFlowAnalyzer(FakeAK())
    data = analyzer.collect("2026-03-21")
    summary = analyzer.build_summary("000001.SZ", "2026-03-21", data)

    report = analyzer.render_markdown(summary)

    assert "A股资金面分析" in report
    assert "目标股资金画像" in report
    assert "龙虎榜与短线资金" in report
    assert "数据缺口与解释边界" in report
    assert "结构化摘要(JSON)" in report


def test_fund_flow_summary_marks_missing_data_as_gap_not_bearish():
    analyzer = AShareFundFlowAnalyzer(FakeAK())
    data = analyzer.collect("2026-03-21")

    summary = analyzer.build_summary("000001.SZ", "2026-03-21", data)

    assert summary.evidence_completeness_score < 100
    assert "主力资金明细" in summary.missing_evidence
    assert "北向持股变动" in summary.missing_evidence
    assert "融资融券明细" in summary.missing_evidence
    assert "只应降低置信度" in summary.data_quality_note
    assert summary.northbound_signal.startswith("北向数据未命中")
    assert summary.margin_signal == "融资融券数据缺失或当日未更新"
