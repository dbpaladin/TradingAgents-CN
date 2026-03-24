from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import json

import os
import time

import pandas as pd


_FUND_FLOW_REPORT_CACHE: Dict[tuple[str, str], tuple[float, str]] = {}
_FUND_FLOW_CACHE_TTL_SECONDS = 600


def _normalize_symbol(ticker: str) -> str:
    return (
        (ticker or "")
        .upper()
        .replace(".SH", "")
        .replace(".SZ", "")
        .replace(".SS", "")
        .replace(".XSHG", "")
        .replace(".XSHE", "")
        .strip()
    )


def _cache_key(ticker: str, trade_date: str) -> tuple[str, str]:
    return _normalize_symbol(ticker), trade_date


def get_cached_a_share_fund_flow_report(
    ticker: str,
    trade_date: str,
    ttl_seconds: int = _FUND_FLOW_CACHE_TTL_SECONDS,
) -> Optional[str]:
    item = _FUND_FLOW_REPORT_CACHE.get(_cache_key(ticker, trade_date))
    if not item:
        return None
    cached_at, report = item
    if ttl_seconds > 0 and (time.time() - cached_at) > ttl_seconds:
        return None
    return report


def _set_cached_a_share_fund_flow_report(ticker: str, trade_date: str, report: str) -> str:
    _FUND_FLOW_REPORT_CACHE[_cache_key(ticker, trade_date)] = (time.time(), report)
    return report


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _pick_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None

    normalized = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
        hit = normalized.get(candidate.strip().lower())
        if hit:
            return hit
    return None


def _find_first_numeric(row: pd.Series, candidates: List[str]) -> float:
    for candidate in candidates:
        value = row.get(candidate)
        if value is not None:
            return _to_float(value)
    return 0.0


@dataclass(frozen=True)
class AShareFundFlowSummary:
    trade_date: str
    ticker: str
    stock_status: str
    capital_style: str
    action_bias: str
    lhb_count: int
    lhb_net_amount: float
    institutional_signal: str
    northbound_signal: str
    margin_signal: str
    market_liquidity_score: float
    risk_flag: str
    evidence_completeness_score: float
    evidence_completeness_label: str
    data_quality_note: str
    evidence: List[str]
    missing_evidence: List[str]
    target_metrics: Dict[str, Any]


class AShareFundFlowAnalyzer:
    """使用 AKShare/Tushare 构建 A 股资金面报告。"""

    def __init__(self, ak_module: Any):
        self.ak = ak_module

    def _safe_fetch(self, func_name: str, **kwargs) -> pd.DataFrame:
        func = getattr(self.ak, func_name, None)
        if not callable(func):
            return pd.DataFrame()
        try:
            df = func(**kwargs)
            if isinstance(df, pd.DataFrame):
                return df.copy()
        except Exception:
            return pd.DataFrame()
        return pd.DataFrame()

    def collect(self, trade_date: str) -> Dict[str, pd.DataFrame]:
        date = trade_date.replace("-", "")
        data = {
            "zt": self._safe_fetch("stock_zt_pool_em", date=date),
            "broken": self._safe_fetch("stock_zt_pool_zbgc_em", date=date),
            "strong": self._safe_fetch("stock_zt_pool_strong_em", date=date),
            "lhb": self._safe_fetch("stock_lhb_stock_statistic_em", symbol="近一月"),
        }
        data.update(self._collect_tushare_context(date))
        return data

    def _collect_tushare_context(self, date: str) -> Dict[str, pd.DataFrame]:
        token = os.getenv("TUSHARE_TOKEN")
        endpoint = os.getenv("TUSHARE_ENDPOINT")

        if token:
            try:
                import tushare as ts

                ts.set_token(token)
                api = ts.pro_api()
                api._DataApi__token = token
                if endpoint:
                    api._DataApi__http_url = endpoint
                return self._query_tushare_context(api, date)
            except Exception:
                pass

        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

            provider = get_tushare_provider()
            if getattr(provider, "api", None):
                return self._query_tushare_context(provider.api, date)
        except Exception:
            pass

        return {}

    def _query_tushare_context(self, api: Any, date: str) -> Dict[str, pd.DataFrame]:
        result: Dict[str, pd.DataFrame] = {}

        for key, fn_name, kwargs in [
            ("moneyflow", "moneyflow", {"trade_date": date}),
            ("margin_detail", "margin_detail", {"trade_date": date}),
            ("hk_hold", "hk_hold", {"trade_date": date}),
        ]:
            try:
                fn = getattr(api, fn_name, None)
                if callable(fn):
                    df = fn(**kwargs)
                    if isinstance(df, pd.DataFrame):
                        result[key] = df.copy()
            except Exception:
                continue

        return result

    def _detect_stock_status(self, ticker: str, data: Dict[str, pd.DataFrame]) -> str:
        symbol = _normalize_symbol(ticker)
        for key, label in [("zt", "涨停池"), ("strong", "强势股池"), ("broken", "炸板池")]:
            df = data.get(key, pd.DataFrame())
            code_col = _pick_column(df, ["代码", "证券代码", "symbol"])
            if code_col and not df.empty:
                matched = df[df[code_col].astype(str) == symbol]
                if not matched.empty:
                    return label
        return "普通状态"

    def _extract_lhb_row(self, ticker: str, data: Dict[str, pd.DataFrame]) -> pd.Series:
        symbol = _normalize_symbol(ticker)
        lhb_df = data.get("lhb", pd.DataFrame())
        code_col = _pick_column(lhb_df, ["代码", "证券代码", "symbol"])
        if code_col and not lhb_df.empty:
            matched = lhb_df[lhb_df[code_col].astype(str) == symbol]
            if not matched.empty:
                return matched.iloc[0]
        return pd.Series(dtype=object)

    def _extract_moneyflow_row(self, ticker: str, data: Dict[str, pd.DataFrame]) -> pd.Series:
        symbol = _normalize_symbol(ticker)
        df = data.get("moneyflow", pd.DataFrame())
        code_col = _pick_column(df, ["ts_code", "股票代码", "代码"])
        if not code_col or df.empty:
            return pd.Series(dtype=object)

        normalized_series = (
            df[code_col]
            .astype(str)
            .str.upper()
            .str.replace(".SH", "", regex=False)
            .str.replace(".SZ", "", regex=False)
        )
        matched = df[normalized_series == symbol]
        if matched.empty:
            return pd.Series(dtype=object)
        return matched.iloc[0]

    def _extract_margin_row(self, ticker: str, data: Dict[str, pd.DataFrame]) -> pd.Series:
        symbol = _normalize_symbol(ticker)
        df = data.get("margin_detail", pd.DataFrame())
        code_col = _pick_column(df, ["ts_code", "股票代码", "标的代码"])
        if not code_col or df.empty:
            return pd.Series(dtype=object)

        normalized_series = (
            df[code_col]
            .astype(str)
            .str.upper()
            .str.replace(".SH", "", regex=False)
            .str.replace(".SZ", "", regex=False)
        )
        matched = df[normalized_series == symbol]
        if matched.empty:
            return pd.Series(dtype=object)
        return matched.iloc[0]

    def _extract_hk_hold_row(self, ticker: str, data: Dict[str, pd.DataFrame]) -> pd.Series:
        symbol = _normalize_symbol(ticker)
        df = data.get("hk_hold", pd.DataFrame())
        code_col = _pick_column(df, ["ts_code", "代码", "股票代码"])
        if not code_col or df.empty:
            return pd.Series(dtype=object)

        normalized_series = (
            df[code_col]
            .astype(str)
            .str.upper()
            .str.replace(".SH", "", regex=False)
            .str.replace(".SZ", "", regex=False)
        )
        matched = df[normalized_series == symbol]
        if matched.empty:
            return pd.Series(dtype=object)
        return matched.iloc[0]

    def build_summary(self, ticker: str, trade_date: str, data: Dict[str, pd.DataFrame]) -> AShareFundFlowSummary:
        stock_status = self._detect_stock_status(ticker, data)
        lhb_row = self._extract_lhb_row(ticker, data)
        moneyflow_row = self._extract_moneyflow_row(ticker, data)
        margin_row = self._extract_margin_row(ticker, data)
        hk_hold_row = self._extract_hk_hold_row(ticker, data)
        symbol = _normalize_symbol(ticker)

        lhb_count = _to_int(lhb_row.get("上榜次数"), 0) if not lhb_row.empty else 0
        lhb_net_amount = _to_float(lhb_row.get("龙虎榜净买额"), 0.0) if not lhb_row.empty else 0.0

        institutional_buy_times = _to_int(
            lhb_row.get("买方机构次数") if not lhb_row.empty else None,
            0,
        )
        institutional_sell_times = _to_int(
            lhb_row.get("卖方机构次数") if not lhb_row.empty else None,
            0,
        )

        main_net_amount = 0.0
        if not moneyflow_row.empty:
            main_net_amount = _find_first_numeric(
                moneyflow_row,
                [
                    "net_mf_amount",
                    "主力净流入",
                    "主力净流入额",
                    "buy_lg_amount",
                    "buy_elg_amount",
                ],
            )

        financing_change = 0.0
        securities_change = 0.0
        if not margin_row.empty:
            financing_change = _find_first_numeric(
                margin_row,
                ["rzmre", "融资买入额", "融资余额", "融资净买入额"],
            )
            securities_change = _find_first_numeric(
                margin_row,
                ["rqmcl", "融券卖出量", "融券余量", "融券净卖出"],
            )

        northbound_change = 0.0
        if not hk_hold_row.empty:
            northbound_change = _find_first_numeric(
                hk_hold_row,
                ["vol_chg", "持股数变化", "持股变动", "share_number_change"],
            )

        zt_count = len(data.get("zt", pd.DataFrame()))
        broken_count = len(data.get("broken", pd.DataFrame()))
        strong_count = len(data.get("strong", pd.DataFrame()))
        liquidity_score = max(
            0.0,
            min(
                100.0,
                round(
                    min(zt_count, 80) * 0.7
                    + min(strong_count, 120) * 0.25
                    - min(broken_count, 60) * 0.5
                    + (8 if lhb_net_amount > 0 else -5 if lhb_net_amount < 0 else 0),
                    2,
                ),
            ),
        )

        evidence: List[str] = []
        missing_evidence: List[str] = []
        if lhb_count > 0:
            evidence.append(f"近一月龙虎榜上榜 {lhb_count} 次")
        else:
            missing_evidence.append("龙虎榜上榜记录")
        if abs(lhb_net_amount) > 0:
            direction = "净流入" if lhb_net_amount > 0 else "净流出"
            evidence.append(f"龙虎榜口径 {direction} {lhb_net_amount:,.0f}")
        if abs(main_net_amount) > 0:
            direction = "流入" if main_net_amount > 0 else "流出"
            evidence.append(f"主力资金口径 {direction} {main_net_amount:,.0f}")
        elif moneyflow_row.empty:
            missing_evidence.append("主力资金明细")
        if abs(northbound_change) > 0:
            direction = "增持" if northbound_change > 0 else "减持"
            evidence.append(f"北向持股变动显示 {direction}")
        elif hk_hold_row.empty:
            missing_evidence.append("北向持股变动")
        if financing_change > 0:
            evidence.append("融资侧偏积极")
        elif financing_change < 0:
            evidence.append("融资侧偏谨慎")
        elif margin_row.empty:
            missing_evidence.append("融资融券明细")
        if stock_status != "普通状态":
            evidence.append(f"个股位于{stock_status}")
        if not evidence:
            evidence.append("当前可直接提取的资金面明细有限，需结合后续交易日继续跟踪")

        if institutional_buy_times > institutional_sell_times and institutional_buy_times > 0:
            institutional_signal = "机构席位偏多"
        elif institutional_sell_times > institutional_buy_times and institutional_sell_times > 0:
            institutional_signal = "机构席位偏空"
        elif lhb_count > 0:
            institutional_signal = "有龙虎榜活跃，但机构席位特征不明显"
        else:
            institutional_signal = "暂无明显机构席位痕迹"

        if northbound_change > 0:
            northbound_signal = "北向资金偏增持"
        elif northbound_change < 0:
            northbound_signal = "北向资金偏减持"
        elif hk_hold_row.empty:
            northbound_signal = "北向数据未命中（可能为非互联互通标的、当日未披露或接口缺失）"
        else:
            northbound_signal = "北向资金当日变动接近中性"

        if financing_change > 0 and securities_change >= 0:
            margin_signal = "融资情绪偏暖"
        elif financing_change < 0 or securities_change > 0:
            margin_signal = "融资融券情绪偏谨慎"
        elif margin_row.empty:
            margin_signal = "融资融券数据缺失或当日未更新"
        else:
            margin_signal = "融资融券信号中性"

        if lhb_net_amount > 0 and main_net_amount > 0 and stock_status in {"涨停池", "强势股池"}:
            capital_style = "游资接力与增量资金共振"
            action_bias = "可跟踪强势延续，但不宜追逐后排"
            risk_flag = "中等"
        elif lhb_net_amount < 0 and stock_status == "炸板池":
            capital_style = "高位资金兑现明显"
            action_bias = "优先防守，等待分歧释放后再评估"
            risk_flag = "较高"
        elif institutional_signal == "机构席位偏多" or northbound_change > 0:
            capital_style = "机构型资金偏温和介入"
            action_bias = "更适合回踩观察，不必按游资节奏追高"
            risk_flag = "中等"
        elif lhb_count > 0:
            capital_style = "短线活跃资金参与，但分歧仍在"
            action_bias = "只适合盯前排辨识度，后排弹性需谨慎"
            risk_flag = "中等偏高"
        else:
            capital_style = "资金面暂无鲜明主导方"
            action_bias = "以基本面和趋势确认优先，资金面仅作辅助"
            risk_flag = "中等"

        target_metrics = {
            "lhb_count": lhb_count,
            "lhb_net_amount": round(lhb_net_amount, 2),
            "main_net_amount": round(main_net_amount, 2),
            "northbound_change": round(northbound_change, 2),
            "financing_change": round(financing_change, 2),
            "institutional_buy_times": institutional_buy_times,
            "institutional_sell_times": institutional_sell_times,
            "has_lhb_record": not lhb_row.empty,
            "has_moneyflow_record": not moneyflow_row.empty,
            "has_margin_record": not margin_row.empty,
            "has_northbound_record": not hk_hold_row.empty,
            "symbol": symbol,
        }

        available_slots = sum(
            [
                int(not lhb_row.empty),
                int(not moneyflow_row.empty),
                int(not margin_row.empty),
                int(not hk_hold_row.empty),
            ]
        )
        evidence_completeness_score = round(available_slots / 4 * 100, 2)
        if evidence_completeness_score >= 75:
            evidence_completeness_label = "高"
        elif evidence_completeness_score >= 50:
            evidence_completeness_label = "中"
        else:
            evidence_completeness_label = "低"

        if missing_evidence:
            data_quality_note = (
                "存在资金证据缺口："
                + "、".join(missing_evidence)
                + "。这些缺口只应降低置信度，不能直接等同于资金偏空；"
                  "若已有龙虎榜/主力资金正负方向信号，应与缺口信息分开表述。"
            )
        else:
            data_quality_note = "关键资金证据较完整，可将资金面结论作为较高权重参考。"

        return AShareFundFlowSummary(
            trade_date=trade_date,
            ticker=ticker,
            stock_status=stock_status,
            capital_style=capital_style,
            action_bias=action_bias,
            lhb_count=lhb_count,
            lhb_net_amount=round(lhb_net_amount, 2),
            institutional_signal=institutional_signal,
            northbound_signal=northbound_signal,
            margin_signal=margin_signal,
            market_liquidity_score=liquidity_score,
            risk_flag=risk_flag,
            evidence_completeness_score=evidence_completeness_score,
            evidence_completeness_label=evidence_completeness_label,
            data_quality_note=data_quality_note,
            evidence=evidence,
            missing_evidence=missing_evidence,
            target_metrics=target_metrics,
        )

    def render_markdown(self, summary: AShareFundFlowSummary) -> str:
        lines = [
            "## A股资金面分析",
            "",
            f"**分析日期**: {summary.trade_date}",
            f"**资金风格判断**: **{summary.capital_style}**",
            f"**行动偏向**: **{summary.action_bias}**",
            f"**风险标记**: **{summary.risk_flag}**",
            "",
            "### 目标股资金画像",
            f"- 股票代码: **{summary.ticker}**",
            f"- 当前状态: **{summary.stock_status}**",
            f"- 市场流动性评分: **{summary.market_liquidity_score}/100**",
            f"- 资金证据完整度: **{summary.evidence_completeness_score}/100 ({summary.evidence_completeness_label})**",
            f"- 机构信号: **{summary.institutional_signal}**",
            f"- 北向信号: **{summary.northbound_signal}**",
            f"- 融资融券信号: **{summary.margin_signal}**",
            "",
            "### 龙虎榜与短线资金",
            f"- 龙虎榜上榜次数(近一月): **{summary.lhb_count} 次**",
            f"- 龙虎榜净买额(近一月): **{summary.lhb_net_amount:,.0f}**",
            "",
            "### 关键证据",
        ]

        for item in summary.evidence:
            lines.append(f"- {item}")

        lines.extend(
            [
                "",
                "### 数据缺口与解释边界",
                f"- {summary.data_quality_note}",
            ]
        )
        if summary.missing_evidence:
            lines.append(f"- 当前缺失项: **{' / '.join(summary.missing_evidence)}**")
        else:
            lines.append("- 当前缺失项: **无明显关键缺口**")

        lines.extend(
            [
                "",
                "### 结构化摘要(JSON)",
                "```json",
                json.dumps(asdict(summary), ensure_ascii=False, indent=2),
                "```",
            ]
        )
        return "\n".join(lines).strip()


def build_a_share_fund_flow_report(ticker: str, trade_date: str) -> str:
    cached = get_cached_a_share_fund_flow_report(ticker=ticker, trade_date=trade_date)
    if cached:
        return cached

    try:
        import akshare as ak
    except Exception as e:
        return (
            f"# {ticker} A股资金面分析\n\n"
            f"资金面工具初始化失败: {e}\n\n"
            "当前环境缺少 akshare 依赖，无法拉取龙虎榜和盘口资金数据。"
        )

    analyzer = AShareFundFlowAnalyzer(ak)
    data = analyzer.collect(trade_date)
    summary = analyzer.build_summary(ticker=ticker, trade_date=trade_date, data=data)
    report = analyzer.render_markdown(summary)
    return _set_cached_a_share_fund_flow_report(ticker=ticker, trade_date=trade_date, report=report)
