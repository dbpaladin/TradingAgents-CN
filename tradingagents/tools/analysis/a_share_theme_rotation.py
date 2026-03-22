from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set
import json

import pandas as pd


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
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(float(value))
    except Exception:
        return default


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


def _pick_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None

    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    normalized_map = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        hit = normalized_map.get(candidate.strip().lower())
        if hit:
            return hit

    return None


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


@dataclass(frozen=True)
class ThemeScore:
    name: str
    category: str
    board_change_pct: float
    constituent_count: int
    up_count: int
    limit_up_count: int
    strong_count: int
    broken_count: int
    leaders: List[str]
    front_rows: List[str]
    followers: List[str]
    heat_score: float
    continuity_score: float
    breadth_score: float
    fade_score: float
    target_in_theme: bool
    target_role: str


@dataclass(frozen=True)
class ThemeRotationSummary:
    trade_date: str
    market_stage: str
    rotation_signal: str
    active_theme_count: int
    dominant_theme: str
    top_themes: List[Dict[str, Any]]
    target_stock: Dict[str, Any]


class AShareThemeRotationAnalyzer:
    """使用 AKShare/东方财富板块与情绪池数据构建题材轮动报告。"""

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
        return {
            "zt": self._safe_fetch("stock_zt_pool_em", date=date),
            "prev_zt": self._safe_fetch("stock_zt_pool_previous_em", date=date),
            "broken": self._safe_fetch("stock_zt_pool_zbgc_em", date=date),
            "strong": self._safe_fetch("stock_zt_pool_strong_em", date=date),
            "concept_boards": self._safe_fetch("stock_board_concept_name_em"),
            "industry_boards": self._safe_fetch("stock_board_industry_name_em"),
        }

    def _fetch_board_constituents(self, board_name: str, category: str) -> pd.DataFrame:
        if not board_name:
            return pd.DataFrame()

        if category == "concept":
            return self._safe_fetch("stock_board_concept_cons_em", symbol=board_name)
        return self._safe_fetch("stock_board_industry_cons_em", symbol=board_name)

    def _extract_board_rows(self, board_df: pd.DataFrame, category: str, limit: int = 8) -> List[Dict[str, Any]]:
        if board_df is None or board_df.empty:
            return []

        name_col = _pick_column(board_df, ["板块名称", "名称", "name"])
        change_col = _pick_column(board_df, ["涨跌幅", "涨跌幅%", "涨跌幅(%)"])
        amount_col = _pick_column(board_df, ["成交额", "成交金额", "总成交额"])

        if not name_col or not change_col:
            return []

        rows: List[Dict[str, Any]] = []
        for _, row in board_df.iterrows():
            board_name = str(row.get(name_col, "")).strip()
            if not board_name:
                continue
            change_pct = _to_float(row.get(change_col), 0.0)
            turnover = _to_float(row.get(amount_col), 0.0) if amount_col else 0.0
            rows.append(
                {
                    "name": board_name,
                    "category": category,
                    "change_pct": change_pct,
                    "turnover": turnover,
                }
            )

        rows.sort(key=lambda item: (item["change_pct"], item["turnover"]), reverse=True)
        return rows[:limit]

    def _fallback_theme_scores(
        self,
        zt_df: pd.DataFrame,
        prev_zt_df: pd.DataFrame,
        broken_df: pd.DataFrame,
        strong_df: pd.DataFrame,
        target_symbol: str,
    ) -> List[ThemeScore]:
        industry_col = None
        for frame in [zt_df, strong_df, broken_df]:
            industry_col = _pick_column(frame, ["所属行业", "行业"])
            if industry_col:
                break
        if not industry_col:
            return []

        code_candidates = ["代码", "证券代码", "symbol"]
        change_candidates = ["涨跌幅", "涨跌幅%", "涨跌幅(%)"]

        industries = set()
        for frame in [zt_df, strong_df, broken_df]:
            col = _pick_column(frame, ["所属行业", "行业"])
            if col and not frame.empty:
                industries.update(
                    {
                        str(value).strip()
                        for value in frame[col].astype(str).tolist()
                        if str(value).strip() and str(value).strip() != "nan"
                    }
                )

        scores: List[ThemeScore] = []
        for industry in industries:
            zt_part = zt_df[zt_df[_pick_column(zt_df, ["所属行业", "行业"])] == industry] if not zt_df.empty and _pick_column(zt_df, ["所属行业", "行业"]) else pd.DataFrame()
            strong_part = strong_df[strong_df[_pick_column(strong_df, ["所属行业", "行业"])] == industry] if not strong_df.empty and _pick_column(strong_df, ["所属行业", "行业"]) else pd.DataFrame()
            broken_part = broken_df[broken_df[_pick_column(broken_df, ["所属行业", "行业"])] == industry] if not broken_df.empty and _pick_column(broken_df, ["所属行业", "行业"]) else pd.DataFrame()
            prev_part = prev_zt_df[prev_zt_df[_pick_column(prev_zt_df, ["所属行业", "行业"])] == industry] if not prev_zt_df.empty and _pick_column(prev_zt_df, ["所属行业", "行业"]) else pd.DataFrame()

            code_set: Set[str] = set()
            leaders: List[str] = []
            front_rows: List[str] = []
            followers: List[str] = []
            for frame, collector in [(zt_part, leaders), (strong_part, front_rows), (prev_part, followers)]:
                code_col = _pick_column(frame, code_candidates)
                if code_col and not frame.empty:
                    codes = [_normalize_symbol(str(code)) for code in frame[code_col].astype(str).tolist() if str(code).strip()]
                    code_set.update(codes)
                    collector.extend(codes[:3 if collector is leaders else 5])

            avg_change = 0.0
            change_values = []
            for frame in [zt_part, strong_part, broken_part]:
                change_col = _pick_column(frame, change_candidates)
                if change_col and not frame.empty:
                    change_values.extend(pd.to_numeric(frame[change_col], errors="coerce").fillna(0).tolist())
            if change_values:
                avg_change = float(sum(change_values) / len(change_values))

            metrics = {
                "constituent_count": max(len(code_set), len(leaders) + len(front_rows)),
                "up_count": len(code_set),
                "limit_up_count": len(zt_part),
                "strong_count": len(strong_part),
                "broken_count": len(broken_part),
                "prev_zt_count": len(prev_part),
                "leaders": list(dict.fromkeys(leaders))[:3],
                "front_rows": [code for code in dict.fromkeys(front_rows) if code not in leaders][:3],
                "followers": [code for code in dict.fromkeys(followers) if code not in leaders and code not in front_rows][:5],
                "target_in_theme": target_symbol in code_set,
            }
            scores.append(
                self._score_theme(
                    board_name=industry,
                    category="industry",
                    board_change_pct=avg_change,
                    metrics=metrics,
                    target_symbol=target_symbol,
                )
            )

        scores.sort(
            key=lambda item: (item.heat_score, item.continuity_score, item.breadth_score, -item.fade_score),
            reverse=True,
        )
        return scores[:5]

    def _constituent_metrics(
        self,
        constituent_df: pd.DataFrame,
        zt_codes: Set[str],
        strong_codes: Set[str],
        broken_codes: Set[str],
        prev_zt_codes: Set[str],
        target_symbol: str,
    ) -> Dict[str, Any]:
        if constituent_df is None or constituent_df.empty:
            return {
                "codes": set(),
                "constituent_count": 0,
                "up_count": 0,
                "limit_up_count": 0,
                "strong_count": 0,
                "broken_count": 0,
                "prev_zt_count": 0,
                "leaders": [],
                "front_rows": [],
                "followers": [],
                "target_in_theme": False,
            }

        code_col = _pick_column(constituent_df, ["代码", "证券代码", "symbol", "代码"])
        change_col = _pick_column(constituent_df, ["涨跌幅", "涨跌幅%", "涨跌幅(%)"])

        if not code_col:
            return {
                "codes": set(),
                "constituent_count": 0,
                "up_count": 0,
                "limit_up_count": 0,
                "strong_count": 0,
                "broken_count": 0,
                "prev_zt_count": 0,
                "leaders": [],
                "front_rows": [],
                "followers": [],
                "target_in_theme": False,
            }

        codes = {
            _normalize_symbol(str(code))
            for code in constituent_df[code_col].astype(str).tolist()
            if str(code).strip()
        }
        codes.discard("")

        limit_up_members = sorted(codes & zt_codes)
        strong_members = sorted(codes & strong_codes)
        broken_members = sorted(codes & broken_codes)
        prev_zt_members = sorted(codes & prev_zt_codes)

        up_count = 0
        if change_col:
            change_series = pd.to_numeric(constituent_df[change_col], errors="coerce").fillna(0)
            up_count = int((change_series > 0).sum())

        leaders = limit_up_members[:3] or strong_members[:3]
        front_rows = [code for code in strong_members if code not in leaders][:3]
        followers = [code for code in prev_zt_members if code not in leaders and code not in front_rows][:5]

        return {
            "codes": codes,
            "constituent_count": len(codes),
            "up_count": up_count,
            "limit_up_count": len(limit_up_members),
            "strong_count": len(strong_members),
            "broken_count": len(broken_members),
            "prev_zt_count": len(prev_zt_members),
            "leaders": leaders,
            "front_rows": front_rows,
            "followers": followers,
            "target_in_theme": target_symbol in codes,
        }

    def _score_theme(
        self,
        board_name: str,
        category: str,
        board_change_pct: float,
        metrics: Dict[str, Any],
        target_symbol: str,
    ) -> ThemeScore:
        constituent_count = metrics["constituent_count"]
        up_count = metrics["up_count"]
        limit_up_count = metrics["limit_up_count"]
        strong_count = metrics["strong_count"]
        broken_count = metrics["broken_count"]
        prev_zt_count = metrics["prev_zt_count"]

        breadth_ratio = _safe_ratio(up_count, constituent_count)
        leadership_ratio = _safe_ratio(limit_up_count + strong_count, max(constituent_count, 1))
        fade_ratio = _safe_ratio(broken_count, limit_up_count + broken_count + 1)
        continuity_ratio = _safe_ratio(strong_count + prev_zt_count, max(limit_up_count + 1, 1))

        heat_score = min(
            100.0,
            max(
                0.0,
                45
                + board_change_pct * 5.0
                + limit_up_count * 7.0
                + strong_count * 4.5
                + breadth_ratio * 18.0,
            ),
        )
        continuity_score = min(
            100.0,
            max(
                0.0,
                30
                + continuity_ratio * 25.0
                + strong_count * 5.0
                + prev_zt_count * 3.0
                - broken_count * 3.5,
            ),
        )
        breadth_score = min(
            100.0,
            max(
                0.0,
                15
                + breadth_ratio * 55.0
                + min(constituent_count, 30) * 0.8
                + leadership_ratio * 18.0,
            ),
        )
        fade_score = min(
            100.0,
            max(
                0.0,
                broken_count * 8.0
                + fade_ratio * 38.0
                - strong_count * 2.5
                - board_change_pct * 2.0,
            ),
        )

        leaders = metrics["leaders"]
        front_rows = metrics["front_rows"]
        followers = metrics["followers"]
        target_in_theme = metrics["target_in_theme"]

        if not target_in_theme:
            target_role = "非题材成员"
        elif target_symbol in leaders:
            target_role = "龙头核心"
        elif target_symbol in front_rows:
            target_role = "前排核心"
        elif target_symbol in followers:
            target_role = "补涨跟随"
        elif strong_count > 0 or limit_up_count > 0:
            target_role = "题材跟风"
        else:
            target_role = "边缘成员"

        return ThemeScore(
            name=board_name,
            category=category,
            board_change_pct=round(board_change_pct, 2),
            constituent_count=constituent_count,
            up_count=up_count,
            limit_up_count=limit_up_count,
            strong_count=strong_count,
            broken_count=broken_count,
            leaders=leaders,
            front_rows=front_rows,
            followers=followers,
            heat_score=round(heat_score, 2),
            continuity_score=round(continuity_score, 2),
            breadth_score=round(breadth_score, 2),
            fade_score=round(fade_score, 2),
            target_in_theme=target_in_theme,
            target_role=target_role,
        )

    def _classify_market_stage(self, top_themes: List[ThemeScore]) -> tuple[str, str]:
        if not top_themes:
            return "混沌", "缺少足够的题材主线"

        leader = top_themes[0]
        avg_fade = sum(item.fade_score for item in top_themes[:3]) / min(len(top_themes), 3)
        avg_heat = sum(item.heat_score for item in top_themes[:3]) / min(len(top_themes), 3)
        avg_continuity = sum(item.continuity_score for item in top_themes[:3]) / min(len(top_themes), 3)

        if avg_heat >= 82 and avg_continuity >= 72 and avg_fade <= 35:
            return "主线强化", f"{leader.name} 带动市场强化，适合围绕核心辨识度做交易。"
        if avg_heat >= 72 and avg_continuity >= 60:
            return "发酵扩散", f"{leader.name} 正在扩散，前排和趋势强度优于后排。"
        if avg_fade >= 58:
            return "高位分歧", f"{leader.name} 仍有热度，但分歧增大，需警惕退潮。"
        if avg_heat <= 55 and avg_fade >= 40:
            return "退潮切换", "主线不清晰，轮动偏快，宜降低追高。"
        return "弱轮动", "题材并行但集中度一般，更适合精选个股而非追逐板块。"

    def build_summary(self, ticker: str, trade_date: str, data: Dict[str, pd.DataFrame]) -> ThemeRotationSummary:
        target_symbol = _normalize_symbol(ticker)

        zt_df = data.get("zt", pd.DataFrame())
        prev_zt_df = data.get("prev_zt", pd.DataFrame())
        broken_df = data.get("broken", pd.DataFrame())
        strong_df = data.get("strong", pd.DataFrame())
        concept_boards_df = data.get("concept_boards", pd.DataFrame())
        industry_boards_df = data.get("industry_boards", pd.DataFrame())

        code_col_candidates = ["代码", "证券代码", "symbol"]
        zt_codes = set()
        strong_codes = set()
        broken_codes = set()
        prev_zt_codes = set()

        for frame, holder in [
            (zt_df, zt_codes),
            (strong_df, strong_codes),
            (broken_df, broken_codes),
            (prev_zt_df, prev_zt_codes),
        ]:
            code_col = _pick_column(frame, code_col_candidates)
            if code_col:
                holder.update(
                    {
                        _normalize_symbol(str(code))
                        for code in frame[code_col].astype(str).tolist()
                        if str(code).strip()
                    }
                )
                holder.discard("")

        board_candidates = (
            self._extract_board_rows(concept_boards_df, "concept", limit=6)
            + self._extract_board_rows(industry_boards_df, "industry", limit=4)
        )

        scored_themes: List[ThemeScore] = []
        for board in board_candidates:
            constituent_df = self._fetch_board_constituents(board["name"], board["category"])
            metrics = self._constituent_metrics(
                constituent_df=constituent_df,
                zt_codes=zt_codes,
                strong_codes=strong_codes,
                broken_codes=broken_codes,
                prev_zt_codes=prev_zt_codes,
                target_symbol=target_symbol,
            )
            if metrics["constituent_count"] == 0:
                continue
            scored_themes.append(
                self._score_theme(
                    board_name=board["name"],
                    category=board["category"],
                    board_change_pct=board["change_pct"],
                    metrics=metrics,
                    target_symbol=target_symbol,
                )
            )

        if not scored_themes:
            scored_themes = self._fallback_theme_scores(
                zt_df=zt_df,
                prev_zt_df=prev_zt_df,
                broken_df=broken_df,
                strong_df=strong_df,
                target_symbol=target_symbol,
            )

        scored_themes.sort(
            key=lambda item: (
                item.heat_score,
                item.continuity_score,
                item.breadth_score,
                -item.fade_score,
            ),
            reverse=True,
        )

        top_themes = scored_themes[:5]
        market_stage, rotation_signal = self._classify_market_stage(top_themes)

        target_memberships = [item for item in scored_themes if item.target_in_theme]
        target_memberships.sort(
            key=lambda item: (item.heat_score, item.continuity_score, -item.fade_score),
            reverse=True,
        )

        if target_memberships:
            main_theme = target_memberships[0]
            mainline_name = top_themes[0].name if top_themes else ""
            role_map = {
                "龙头核心": "主线核心" if main_theme.name == mainline_name else "非主线",
                "前排核心": "主线核心" if main_theme.name == mainline_name else "非主线",
                "补涨跟随": "主线外延" if main_theme.name == mainline_name else "非主线",
                "题材跟风": "主线外延" if main_theme.name == mainline_name else "非主线",
                "边缘成员": "主线外延" if main_theme.name == mainline_name else "非主线",
            }
            normalized_role = role_map.get(main_theme.target_role, "非主线")
            target_payload = {
                "ticker": ticker,
                "theme_tags": [item.name for item in target_memberships[:3]],
                "role": normalized_role,
                "raw_role": main_theme.target_role,
                "is_mainline": main_theme.name == (top_themes[0].name if top_themes else ""),
                "leader_score": round(
                    min(100.0, main_theme.heat_score * 0.35 + main_theme.continuity_score * 0.4 + (100 - main_theme.fade_score) * 0.25),
                    2,
                ),
                "risk_flags": [
                    flag
                    for flag, ok in [
                        ("高位分歧", main_theme.fade_score >= 55),
                        ("非绝对主线", main_theme.name != (top_themes[0].name if top_themes else "")),
                        ("板块扩散不足", main_theme.breadth_score < 45),
                    ]
                    if ok
                ] or ["暂无显著题材风险"],
            }
        else:
            target_payload = {
                "ticker": ticker,
                "theme_tags": [],
                "role": "非主线",
                "raw_role": "独立逻辑/非主线",
                "is_mainline": False,
                "leader_score": 25.0,
                "risk_flags": ["未进入主线题材核心池"],
            }

        top_theme_payload = []
        for item in top_themes:
            payload = asdict(item)
            payload["target_stock_in_theme"] = item.target_in_theme
            top_theme_payload.append(payload)

        return ThemeRotationSummary(
            trade_date=trade_date,
            market_stage=market_stage,
            rotation_signal=rotation_signal,
            active_theme_count=len(top_themes),
            dominant_theme=top_themes[0].name if top_themes else "暂无明确主线",
            top_themes=top_theme_payload,
            target_stock=target_payload,
        )

    def render_markdown(self, ticker: str, summary: ThemeRotationSummary) -> str:
        lines = [
            "## A股题材热点与轮动分析",
            "",
            f"**分析日期**: {summary.trade_date}",
            f"**市场阶段**: **{summary.market_stage}**",
            f"**轮动信号**: **{summary.rotation_signal}**",
            f"**当前主线**: **{summary.dominant_theme}**",
            "",
            "### 目标股题材定位",
            f"- 股票代码: **{ticker}**",
            f"- 所属题材: **{'、'.join(summary.target_stock.get('theme_tags', [])) or '暂无主线题材归属，偏独立逻辑'}**",
            f"- 角色定位: **{summary.target_stock.get('role', '未知')}**",
            f"- 是否主线: **{'是' if summary.target_stock.get('is_mainline') else '否'}**",
            f"- 龙头/核心评分: **{summary.target_stock.get('leader_score', 0)}/100**",
            f"- 原始角色: **{summary.target_stock.get('raw_role', '未知')}**",
            f"- 风险提示: **{'、'.join(summary.target_stock.get('risk_flags', []))}**",
            "",
            "### 角色说明",
            "- `主线核心`：位于当前主线板块的龙头或前排核心，资金辨识度高。",
            "- `主线外延`：与当前主线存在明确产业链/板块关联，但不是涨停前排或资金核心。",
            "- `非主线`：未进入当前主线题材交易框架，更多依赖独立逻辑。",
            "",
            "### 主线题材 Top5",
        ]

        for idx, theme in enumerate(summary.top_themes, 1):
            lines.extend(
                [
                    f"#### {idx}. {theme['name']} ({'概念' if theme['category'] == 'concept' else '行业'})",
                    f"- 板块涨跌幅: **{theme['board_change_pct']:.2f}%**",
                    f"- 热度分: **{theme['heat_score']}**",
                    f"- 持续性分: **{theme['continuity_score']}**",
                    f"- 扩散度分: **{theme['breadth_score']}**",
                    f"- 退潮风险分: **{theme['fade_score']}**",
                    f"- 涨停/强势/炸板: **{theme['limit_up_count']}/{theme['strong_count']}/{theme['broken_count']}**",
                    f"- 龙头观察: **{'、'.join(theme['leaders']) if theme['leaders'] else '暂无显著龙头'}**",
                    f"- 前排梯队: **{'、'.join(theme['front_rows']) if theme['front_rows'] else '暂无'}**",
                    f"- 跟风/补涨: **{'、'.join(theme['followers']) if theme['followers'] else '暂无'}**",
                    f"- 目标股定位: **{theme['target_role'] if theme['target_in_theme'] else '不在该题材'}**",
                    "",
                ]
            )

        lines.extend(
            [
                "### 结构化摘要(JSON)",
                "```json",
                json.dumps(asdict(summary), ensure_ascii=False, indent=2),
                "```",
            ]
        )

        return "\n".join(lines).strip()


def build_a_share_theme_rotation_report(ticker: str, trade_date: str) -> str:
    import akshare as ak

    analyzer = AShareThemeRotationAnalyzer(ak)
    data = analyzer.collect(trade_date)
    summary = analyzer.build_summary(ticker=ticker, trade_date=trade_date, data=data)
    return analyzer.render_markdown(ticker=ticker, summary=summary)
