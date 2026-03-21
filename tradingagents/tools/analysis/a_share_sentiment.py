from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import os
import time
import pandas as pd


_SENTIMENT_REPORT_CACHE: Dict[tuple[str, str], tuple[float, str]] = {}
_SENTIMENT_CACHE_TTL_SECONDS = 600


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
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


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def normalize_a_share_symbol(ticker: str) -> str:
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
    return normalize_a_share_symbol(ticker), trade_date


def get_cached_a_share_sentiment_report(
    ticker: str,
    trade_date: str,
    ttl_seconds: int = _SENTIMENT_CACHE_TTL_SECONDS,
) -> Optional[str]:
    item = _SENTIMENT_REPORT_CACHE.get(_cache_key(ticker, trade_date))
    if not item:
        return None
    cached_at, report = item
    if ttl_seconds > 0 and (time.time() - cached_at) > ttl_seconds:
        return None
    return report


def _set_cached_a_share_sentiment_report(ticker: str, trade_date: str, report: str) -> str:
    _SENTIMENT_REPORT_CACHE[_cache_key(ticker, trade_date)] = (time.time(), report)
    return report


@dataclass(frozen=True)
class AShareEmotionSnapshot:
    trade_date: str
    zt_count: int
    dt_count: int
    broken_count: int
    strong_count: int
    highest_board: int
    open_board_rate: float
    continuation_rate: float
    avg_limit_up_return: float
    avg_broken_return: float
    avg_seal_ratio: float
    leading_industries: List[str]
    cycle_stage: str
    cycle_score: float
    risk_level: str
    market_emotion: str
    limit_up_20cm_count: int
    limit_up_10cm_count: int
    new_high_strong_count: int
    top_theme_names: List[str]
    weak_theme_names: List[str]
    market_style: str
    participation_advice: str
    total_market_amount_billion: float
    up_count: int
    down_count: int
    flat_count: int
    avg_pct_chg: float
    median_pct_chg: float
    index_performance: Dict[str, Dict[str, float]]


class AShareSentimentAnalyzer:
    """
    使用东方财富/AKShare盘口数据构建轻量级 A 股情绪面分析。
    """

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
            "prev_zt": self._safe_fetch("stock_zt_pool_previous_em", date=date),
            "broken": self._safe_fetch("stock_zt_pool_zbgc_em", date=date),
            "dt": self._safe_fetch("stock_zt_pool_dtgc_em", date=date),
            "strong": self._safe_fetch("stock_zt_pool_strong_em", date=date),
            "lhb": self._safe_fetch("stock_lhb_stock_statistic_em", symbol="近一月"),
        }
        data.update(self._collect_tushare_market_context(date))
        return data

    def _collect_tushare_market_context(self, date: str) -> Dict[str, pd.DataFrame]:
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
                return self._query_tushare_market_context(api=api, date=date)
            except Exception:
                pass

        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

            provider = get_tushare_provider()
            if not getattr(provider, "api", None):
                return {}

            return self._query_tushare_market_context(api=provider.api, date=date)
        except Exception:
            return {}

    def _query_tushare_market_context(self, api: Any, date: str) -> Dict[str, pd.DataFrame]:
        market_daily = api.daily(
            trade_date=date,
            fields="ts_code,trade_date,pct_chg,amount,vol,close"
        )

        index_frames = []
        for ts_code, label in [
            ("000001.SH", "上证指数"),
            ("399001.SZ", "深证成指"),
            ("399006.SZ", "创业板指"),
        ]:
            try:
                df = api.index_daily(
                    ts_code=ts_code,
                    start_date=date,
                    end_date=date,
                )
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df = df.copy()
                    df["index_name"] = label
                    index_frames.append(df.head(1))
            except Exception:
                continue

        return {
            "market_daily": market_daily if isinstance(market_daily, pd.DataFrame) else pd.DataFrame(),
            "market_index": pd.concat(index_frames, ignore_index=True) if index_frames else pd.DataFrame(),
        }

    def _classify_cycle(
        self,
        zt_count: int,
        dt_count: int,
        broken_count: int,
        highest_board: int,
        continuation_rate: float,
        open_board_rate: float,
        strong_count: int,
    ) -> tuple[str, float, str, str]:
        score = 50.0
        score += min(zt_count, 120) * 0.35
        score += min(highest_board, 8) * 4.5
        score += continuation_rate * 22
        score += min(strong_count, 200) * 0.04
        score -= min(dt_count, 40) * 1.5
        score -= open_board_rate * 35
        score -= min(broken_count, 60) * 0.35
        score = max(0.0, min(100.0, round(score, 2)))

        if (dt_count >= 12 or open_board_rate >= 0.45) and highest_board <= 2:
            return "冰点", score, "高风险", "extreme_fear"
        if dt_count >= 8 or (open_board_rate >= 0.35 and continuation_rate < 0.45):
            return "退潮", score, "较高风险", "fear"
        if continuation_rate >= 0.65 and zt_count >= 45 and highest_board >= 5 and open_board_rate <= 0.18:
            return "高潮", score, "注意分化", "extreme_greed"
        if continuation_rate >= 0.55 and zt_count >= 28 and highest_board >= 3:
            return "发酵", score, "中等风险", "greed"
        if continuation_rate >= 0.48 and dt_count <= 6:
            return "修复", score, "可控风险", "neutral"
        return "分化", score, "中等偏高风险", "neutral"

    def build_snapshot(self, trade_date: str, data: Dict[str, pd.DataFrame]) -> AShareEmotionSnapshot:
        zt_df = data.get("zt", pd.DataFrame())
        prev_zt_df = data.get("prev_zt", pd.DataFrame())
        broken_df = data.get("broken", pd.DataFrame())
        dt_df = data.get("dt", pd.DataFrame())
        strong_df = data.get("strong", pd.DataFrame())
        market_daily_df = data.get("market_daily", pd.DataFrame())
        market_index_df = data.get("market_index", pd.DataFrame())

        zt_count = len(zt_df)
        dt_count = len(dt_df)
        broken_count = len(broken_df)
        strong_count = len(strong_df)
        highest_board = _to_int(zt_df.get("连板数", pd.Series(dtype=float)).max(), 0) if not zt_df.empty else 0

        total_attempts = zt_count + broken_count
        open_board_rate = (broken_count / total_attempts) if total_attempts else 0.0

        if not prev_zt_df.empty and "涨跌幅" in prev_zt_df.columns:
            continuation_rate = float((pd.to_numeric(prev_zt_df["涨跌幅"], errors="coerce") > 0).mean())
            avg_limit_up_return = float(pd.to_numeric(prev_zt_df["涨跌幅"], errors="coerce").fillna(0).mean())
        else:
            continuation_rate = 0.0
            avg_limit_up_return = 0.0

        if not broken_df.empty and "涨跌幅" in broken_df.columns:
            avg_broken_return = float(pd.to_numeric(broken_df["涨跌幅"], errors="coerce").fillna(0).mean())
        else:
            avg_broken_return = 0.0

        if not zt_df.empty and {"封板资金", "成交额"}.issubset(set(zt_df.columns)):
            seal_amount = pd.to_numeric(zt_df["封板资金"], errors="coerce").fillna(0)
            turnover = pd.to_numeric(zt_df["成交额"], errors="coerce").replace(0, pd.NA)
            avg_seal_ratio = float((seal_amount / turnover).fillna(0).mean())
        else:
            avg_seal_ratio = 0.0

        if not zt_df.empty and "所属行业" in zt_df.columns:
            industry_counts = zt_df["所属行业"].fillna("未知").value_counts().head(3)
            leading_industries = [f"{idx}({cnt})" for idx, cnt in industry_counts.items()]
        else:
            leading_industries = []

        if not zt_df.empty and "涨跌幅" in zt_df.columns:
            zt_pct = pd.to_numeric(zt_df["涨跌幅"], errors="coerce").fillna(0)
            limit_up_20cm_count = int((zt_pct >= 19.5).sum())
            limit_up_10cm_count = max(0, zt_count - limit_up_20cm_count)
        else:
            limit_up_20cm_count = 0
            limit_up_10cm_count = zt_count

        if not strong_df.empty and "是否新高" in strong_df.columns:
            new_high_strong_count = int((strong_df["是否新高"].fillna("否").astype(str) == "是").sum())
        else:
            new_high_strong_count = 0

        top_theme_names, weak_theme_names = self._build_theme_maps(zt_df, broken_df, dt_df)

        total_market_amount_billion = 0.0
        up_count = 0
        down_count = 0
        flat_count = 0
        avg_pct_chg = 0.0
        median_pct_chg = 0.0
        if not market_daily_df.empty and "pct_chg" in market_daily_df.columns:
            pct_series = pd.to_numeric(market_daily_df["pct_chg"], errors="coerce").fillna(0)
            amount_series = pd.to_numeric(market_daily_df.get("amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
            up_count = int((pct_series > 0).sum())
            down_count = int((pct_series < 0).sum())
            flat_count = int((pct_series == 0).sum())
            avg_pct_chg = float(pct_series.mean())
            median_pct_chg = float(pct_series.median())
            # Tushare daily amount 单位是千元，这里换算为亿元
            total_market_amount_billion = float(amount_series.sum() / 100000.0)

        index_performance: Dict[str, Dict[str, float]] = {}
        if not market_index_df.empty:
            for _, row in market_index_df.iterrows():
                label = str(row.get("index_name", row.get("ts_code", "指数")))
                index_performance[label] = {
                    "pct_chg": _to_float(row.get("pct_chg")),
                    "close": _to_float(row.get("close")),
                    "amount_billion": _to_float(row.get("amount")) / 100000.0,
                }

        if limit_up_20cm_count >= max(3, zt_count * 0.18):
            market_style = "高弹性题材活跃，短线风险偏好较高"
        elif highest_board >= 4 and continuation_rate >= 0.5:
            market_style = "连板接力主导，市场偏向龙头博弈"
        elif dt_count >= 10 and broken_count >= zt_count * 0.6:
            market_style = "高位退潮明显，资金偏防守"
        else:
            market_style = "风格分化，需围绕前排辨识度参与"

        cycle_stage, cycle_score, risk_level, market_emotion = self._classify_cycle(
            zt_count=zt_count,
            dt_count=dt_count,
            broken_count=broken_count,
            highest_board=highest_board,
            continuation_rate=continuation_rate,
            open_board_rate=open_board_rate,
            strong_count=strong_count,
        )

        if cycle_stage in {"冰点", "退潮"}:
            participation_advice = "以轻仓观察为主，优先等待分歧后确认，不追高。"
        elif cycle_stage in {"修复", "分化"}:
            participation_advice = "可小仓位围绕前排与回流方向试错，强调去弱留强。"
        elif cycle_stage == "发酵":
            participation_advice = "可以围绕主线前排和低位补涨参与，但要警惕跟风扩散过快。"
        else:
            participation_advice = "一致性较强，适合做核心龙头，但更要防范次日分化兑现。"

        return AShareEmotionSnapshot(
            trade_date=trade_date,
            zt_count=zt_count,
            dt_count=dt_count,
            broken_count=broken_count,
            strong_count=strong_count,
            highest_board=highest_board,
            open_board_rate=open_board_rate,
            continuation_rate=continuation_rate,
            avg_limit_up_return=avg_limit_up_return,
            avg_broken_return=avg_broken_return,
            avg_seal_ratio=avg_seal_ratio,
            leading_industries=leading_industries,
            cycle_stage=cycle_stage,
            cycle_score=cycle_score,
            risk_level=risk_level,
            market_emotion=market_emotion,
            limit_up_20cm_count=limit_up_20cm_count,
            limit_up_10cm_count=limit_up_10cm_count,
            new_high_strong_count=new_high_strong_count,
            top_theme_names=top_theme_names,
            weak_theme_names=weak_theme_names,
            market_style=market_style,
            participation_advice=participation_advice,
            total_market_amount_billion=total_market_amount_billion,
            up_count=up_count,
            down_count=down_count,
            flat_count=flat_count,
            avg_pct_chg=avg_pct_chg,
            median_pct_chg=median_pct_chg,
            index_performance=index_performance,
        )

    def _build_theme_maps(
        self,
        zt_df: pd.DataFrame,
        broken_df: pd.DataFrame,
        dt_df: pd.DataFrame,
    ) -> tuple[List[str], List[str]]:
        def _count_by_industry(df: pd.DataFrame) -> Dict[str, int]:
            if df.empty or "所属行业" not in df.columns:
                return {}
            series = df["所属行业"].fillna("未知").astype(str)
            return {str(k): int(v) for k, v in series.value_counts().items()}

        zt_map = _count_by_industry(zt_df)
        broken_map = _count_by_industry(broken_df)
        dt_map = _count_by_industry(dt_df)

        scores: Dict[str, float] = {}
        for industry, count in zt_map.items():
            scores[industry] = scores.get(industry, 0.0) + count * 1.0
        for industry, count in broken_map.items():
            scores[industry] = scores.get(industry, 0.0) - count * 0.7
        for industry, count in dt_map.items():
            scores[industry] = scores.get(industry, 0.0) - count * 1.0

        positive = sorted(
            [(k, v) for k, v in scores.items() if v > 0],
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        negative = sorted(
            [(k, v) for k, v in scores.items() if v < 0],
            key=lambda item: item[1],
        )[:3]

        top_theme_names = [f"{k}(强度{v:.1f})" for k, v in positive]
        weak_theme_names = [f"{k}(压力{abs(v):.1f})" for k, v in negative]
        return top_theme_names, weak_theme_names

    def _build_stock_focus(self, ticker: str, snapshot: AShareEmotionSnapshot, data: Dict[str, pd.DataFrame]) -> Optional[str]:
        symbol = normalize_a_share_symbol(ticker)
        zt_df = data.get("zt", pd.DataFrame())
        broken_df = data.get("broken", pd.DataFrame())
        strong_df = data.get("strong", pd.DataFrame())
        lhb_df = data.get("lhb", pd.DataFrame())

        target_row = pd.DataFrame()
        stock_status = "普通跟踪"

        if not zt_df.empty and "代码" in zt_df.columns:
            matched = zt_df[zt_df["代码"].astype(str) == symbol]
            if not matched.empty:
                target_row = matched.iloc[[0]]
                stock_status = "涨停池"

        if target_row.empty and not broken_df.empty and "代码" in broken_df.columns:
            matched = broken_df[broken_df["代码"].astype(str) == symbol]
            if not matched.empty:
                target_row = matched.iloc[[0]]
                stock_status = "炸板池"

        if target_row.empty and not strong_df.empty and "代码" in strong_df.columns:
            matched = strong_df[strong_df["代码"].astype(str) == symbol]
            if not matched.empty:
                target_row = matched.iloc[[0]]
                stock_status = "强势股池"

        lhb_row = pd.DataFrame()
        if not lhb_df.empty and "代码" in lhb_df.columns:
            lhb_matched = lhb_df[lhb_df["代码"].astype(str) == symbol]
            if not lhb_matched.empty:
                lhb_row = lhb_matched.iloc[[0]]

        if target_row.empty and lhb_row.empty:
            return None

        parts = ["### 个股情绪定位"]
        parts.append(f"- 当前状态: **{stock_status}**")

        if not target_row.empty:
            row = target_row.iloc[0]
            board_count = _to_int(row.get("连板数") or row.get("昨日连板数"), 0)
            industry = row.get("所属行业", "未知")
            first_board = row.get("首次封板时间") or row.get("昨日封板时间") or "未知"
            broken_times = _to_int(row.get("炸板次数"), 0)
            seal_ratio = 0.0
            turnover = _to_float(row.get("成交额"))
            seal_amount = _to_float(row.get("封板资金"))
            if turnover > 0:
                seal_ratio = seal_amount / turnover

            peers = 0
            if not zt_df.empty and "所属行业" in zt_df.columns:
                peers = int((zt_df["所属行业"] == industry).sum())

            competitors = 0
            if not zt_df.empty and "连板数" in zt_df.columns:
                competitors = max(0, int((pd.to_numeric(zt_df["连板数"], errors="coerce").fillna(0) == board_count).sum()) - 1)

            dragon_score = (
                min(board_count, 7) * 11
                + max(0, 25 - competitors * 6)
                + min(peers, 8) * 4
                + (12 if snapshot.market_emotion in {"greed", "extreme_greed"} and board_count >= 3 else 6)
                + min(seal_ratio * 50, 18)
                - broken_times * 4
            )
            dragon_score = max(0.0, min(100.0, round(dragon_score, 2)))

            parts.extend(
                [
                    f"- 连板高度: **{board_count} 板**",
                    f"- 所属行业: **{industry}**",
                    f"- 首次封板时间: **{first_board}**",
                    f"- 炸板次数: **{broken_times} 次**",
                    f"- 估算龙头分: **{dragon_score}/100**",
                ]
            )

        if not lhb_row.empty:
            row = lhb_row.iloc[0]
            parts.extend(
                [
                    f"- 龙虎榜上榜次数(近一月): **{_to_int(row.get('上榜次数'))} 次**",
                    f"- 龙虎榜净买额(近一月): **{_to_float(row.get('龙虎榜净买额')):,.0f}**",
                ]
            )

        return "\n".join(parts)

    def render_markdown(self, ticker: str, trade_date: str, snapshot: AShareEmotionSnapshot, data: Dict[str, pd.DataFrame]) -> str:
        cycle_hint_map = {
            "冰点": "优先观察首板和低位修复，不宜追高。",
            "修复": "可关注低位修复与板块回流的确认度。",
            "发酵": "主线扩散中，可跟踪前排辨识度与换手质量。",
            "高潮": "一致性偏高，重点防范次日分化和高位兑现。",
            "分化": "聚焦最强方向，避免跟风杂毛。",
            "退潮": "轻仓或空仓等待，优先规避高位补跌。",
        }
        index_lines = []
        for index_name in ["上证指数", "深证成指", "创业板指"]:
            if index_name in snapshot.index_performance:
                perf = snapshot.index_performance[index_name]
                index_lines.append(
                    f"- {index_name}: **{perf['pct_chg']:+.2f}%**，收于 **{perf['close']:.2f}**，成交额 **{perf['amount_billion']:.1f} 亿**"
                )

        lines = [
            "## A股盘面情绪分析（DragonJudge风格增强）",
            "",
            f"**分析日期**: {trade_date}",
            f"**周期阶段**: **{snapshot.cycle_stage}**",
            f"**情绪得分**: **{snapshot.cycle_score}/100**",
            f"**风险等级**: **{snapshot.risk_level}**",
            "",
            "### 市场总情绪",
            f"- 涨停家数: **{snapshot.zt_count}**",
            f"- 跌停家数: **{snapshot.dt_count}**",
            f"- 炸板家数: **{snapshot.broken_count}**",
            f"- 强势股池家数: **{snapshot.strong_count}**",
            f"- 最高连板: **{snapshot.highest_board} 板**",
            f"- 10cm涨停占比: **{snapshot.limit_up_10cm_count} 家**",
            f"- 20cm涨停占比: **{snapshot.limit_up_20cm_count} 家**",
            f"- 强势股创新高家数: **{snapshot.new_high_strong_count}**",
            f"- 炸板率: **{_format_pct(snapshot.open_board_rate)}**",
            f"- 昨日涨停晋级率: **{_format_pct(snapshot.continuation_rate)}**",
            f"- 昨日涨停平均表现: **{snapshot.avg_limit_up_return:.2f}%**",
            f"- 炸板股平均表现: **{snapshot.avg_broken_return:.2f}%**",
            f"- 平均封板资金/成交额: **{_format_pct(snapshot.avg_seal_ratio)}**",
            f"- 全市场上涨/下跌/平盘: **{snapshot.up_count}/{snapshot.down_count}/{snapshot.flat_count}**",
            f"- 全市场平均涨跌幅: **{snapshot.avg_pct_chg:+.2f}%**",
            f"- 全市场涨跌幅中位数: **{snapshot.median_pct_chg:+.2f}%**",
            f"- 两市成交额估算: **{snapshot.total_market_amount_billion:.1f} 亿**",
            "",
            "### 大盘指数环境",
            *(index_lines if index_lines else ["- 指数环境数据暂不可用"]),
            "",
            "### 主线/板块情绪",
            f"- 当前主导方向: **{'、'.join(snapshot.leading_industries) if snapshot.leading_industries else '暂无明显集中'}**",
            f"- 主线强势板块: **{'、'.join(snapshot.top_theme_names) if snapshot.top_theme_names else '未形成清晰主线'}**",
            f"- 承压板块: **{'、'.join(snapshot.weak_theme_names) if snapshot.weak_theme_names else '暂无明显系统性弱势板块'}**",
            "",
            "### 市场风格与参与建议",
            f"- 市场风格: **{snapshot.market_style}**",
            f"- 当前情绪特征: **{snapshot.cycle_stage}**，{cycle_hint_map.get(snapshot.cycle_stage, '关注前排强度与亏钱效应的变化。')}",
            f"- 参与建议: **{snapshot.participation_advice}**",
        ]

        stock_focus = self._build_stock_focus(ticker=ticker, snapshot=snapshot, data=data)
        if stock_focus:
            lines.extend(["", stock_focus])

        return "\n".join(lines).strip()


def build_a_share_sentiment_report(ticker: str, trade_date: str) -> str:
    cached = get_cached_a_share_sentiment_report(ticker=ticker, trade_date=trade_date)
    if cached:
        return cached

    import akshare as ak

    analyzer = AShareSentimentAnalyzer(ak)
    data = analyzer.collect(trade_date)
    snapshot = analyzer.build_snapshot(trade_date=trade_date, data=data)
    report = analyzer.render_markdown(
        ticker=ticker,
        trade_date=trade_date,
        snapshot=snapshot,
        data=data,
    )
    return _set_cached_a_share_sentiment_report(ticker=ticker, trade_date=trade_date, report=report)
