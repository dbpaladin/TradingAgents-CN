import pandas as pd

from tradingagents.tools.analysis.a_share_theme_rotation import AShareThemeRotationAnalyzer


class FakeAK:
    def stock_zt_pool_em(self, date: str):
        return pd.DataFrame(
            [
                {"代码": "601669"},
                {"代码": "600001"},
                {"代码": "300001"},
            ]
        )

    def stock_zt_pool_previous_em(self, date: str):
        return pd.DataFrame(
            [
                {"代码": "601669"},
                {"代码": "600001"},
                {"代码": "000002"},
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
                {"板块名称": "中字头", "涨跌幅": 4.2, "成交额": 100000000},
                {"板块名称": "AI应用", "涨跌幅": 2.1, "成交额": 80000000},
            ]
        )

    def stock_board_industry_name_em(self):
        return pd.DataFrame(
            [
                {"板块名称": "建筑装饰", "涨跌幅": 3.5, "成交额": 90000000},
            ]
        )

    def stock_board_concept_cons_em(self, symbol: str):
        if symbol == "中字头":
            return pd.DataFrame(
                [
                    {"代码": "601669", "涨跌幅": 10.0},
                    {"代码": "600001", "涨跌幅": 9.5},
                    {"代码": "000002", "涨跌幅": 5.0},
                    {"代码": "000003", "涨跌幅": -1.0},
                ]
            )
        if symbol == "AI应用":
            return pd.DataFrame(
                [
                    {"代码": "300001", "涨跌幅": 8.0},
                    {"代码": "300002", "涨跌幅": 3.0},
                    {"代码": "300003", "涨跌幅": -2.0},
                ]
            )
        return pd.DataFrame()

    def stock_board_industry_cons_em(self, symbol: str):
        if symbol == "建筑装饰":
            return pd.DataFrame(
                [
                    {"代码": "601669", "涨跌幅": 10.0},
                    {"代码": "600001", "涨跌幅": 9.5},
                    {"代码": "002001", "涨跌幅": 2.0},
                ]
            )
        return pd.DataFrame()


def test_theme_rotation_summary_identifies_mainline_and_target_role():
    analyzer = AShareThemeRotationAnalyzer(FakeAK())
    data = analyzer.collect("2026-03-21")

    summary = analyzer.build_summary("601669", "2026-03-21", data)

    assert summary.dominant_theme == "中字头"
    assert summary.target_stock["is_mainline"] is True
    assert summary.target_stock["role"] in {"龙头核心", "前排核心"}
    assert summary.top_themes
    assert summary.top_themes[0]["heat_score"] >= summary.top_themes[1]["heat_score"]


def test_theme_rotation_report_contains_structured_summary():
    analyzer = AShareThemeRotationAnalyzer(FakeAK())
    data = analyzer.collect("2026-03-21")
    summary = analyzer.build_summary("601669", "2026-03-21", data)

    report = analyzer.render_markdown("601669", summary)

    assert "A股题材热点与轮动分析" in report
    assert "结构化摘要(JSON)" in report
    assert "中字头" in report
