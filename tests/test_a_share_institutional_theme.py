import pandas as pd

from tradingagents.tools.analysis.a_share_institutional_theme import AShareInstitutionalThemeAnalyzer


class FakeAK:
    def stock_zt_pool_em(self, date: str):
        return pd.DataFrame(
            [
                {"代码": "300001"},
                {"代码": "601669"},
            ]
        )

    def stock_zt_pool_zbgc_em(self, date: str):
        return pd.DataFrame([{"代码": "000003"}])

    def stock_zt_pool_strong_em(self, date: str):
        return pd.DataFrame(
            [
                {"代码": "601669"},
                {"代码": "600001"},
                {"代码": "000002"},
            ]
        )

    def stock_board_concept_name_em(self):
        return pd.DataFrame(
            [
                {"板块名称": "央企重组", "涨跌幅": 2.8, "成交额": 70000000},
                {"板块名称": "低空经济", "涨跌幅": 6.3, "成交额": 120000000},
            ]
        )

    def stock_board_industry_name_em(self):
        return pd.DataFrame(
            [
                {"板块名称": "建筑装饰", "涨跌幅": 2.2, "成交额": 65000000},
            ]
        )

    def stock_board_concept_cons_em(self, symbol: str):
        if symbol == "央企重组":
            return pd.DataFrame(
                [
                    {"代码": "601669", "涨跌幅": 5.5},
                    {"代码": "600001", "涨跌幅": 4.2},
                    {"代码": "000002", "涨跌幅": 1.8},
                    {"代码": "000003", "涨跌幅": -0.6},
                ]
            )
        if symbol == "低空经济":
            return pd.DataFrame(
                [
                    {"代码": "300001", "涨跌幅": 10.0},
                    {"代码": "300002", "涨跌幅": 7.5},
                    {"代码": "300003", "涨跌幅": 5.2},
                ]
            )
        return pd.DataFrame()

    def stock_board_industry_cons_em(self, symbol: str):
        if symbol == "建筑装饰":
            return pd.DataFrame(
                [
                    {"代码": "601669", "涨跌幅": 5.5},
                    {"代码": "600001", "涨跌幅": 4.2},
                    {"代码": "002001", "涨跌幅": 1.0},
                ]
            )
        return pd.DataFrame()


class FakeAnalyzer(AShareInstitutionalThemeAnalyzer):
    def _search_news_mentions(self, keyword: str):
        if keyword == "央企重组":
            return {"count": 6, "recent_count": 3, "sources": ["证券时报"]}
        if keyword == "低空经济":
            return {"count": 18, "recent_count": 10, "sources": ["财联社"]}
        return {"count": 2, "recent_count": 0, "sources": []}


def test_institutional_theme_identifies_early_candidate():
    analyzer = FakeAnalyzer(FakeAK())
    data = analyzer.collect("2026-03-21")

    summary = analyzer.build_summary("601669", "2026-03-21", data)

    assert summary.candidates
    assert summary.target_stock["ticker"] == "601669"
    assert summary.target_stock["institutional_layout_score"] > 0
    assert "央企重组" in [item["name"] for item in summary.candidates]


def test_institutional_theme_report_contains_candidate_sections():
    analyzer = FakeAnalyzer(FakeAK())
    data = analyzer.collect("2026-03-21")
    summary = analyzer.build_summary("601669", "2026-03-21", data)

    report = analyzer.render_markdown("601669", summary)

    assert "A股机构布局题材识别" in report
    assert "前瞻候选题材 Top5" in report
    assert "结构化摘要(JSON)" in report
