from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
import json
import re

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

    normalized = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        hit = normalized.get(candidate.strip().lower())
        if hit:
            return hit

    return None


def _safe_ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


@dataclass(frozen=True)
class InstitutionalThemeCandidate:
    name: str
    category: str
    board_change_pct: float
    breadth_score: float
    early_strength_score: float
    news_catalyst_score: float
    institutional_layout_score: float
    overheating_score: float
    stage: str
    rationale: str
    leaders: List[str]
    test_positions: List[str]
    target_in_theme: bool
    target_role: str


@dataclass(frozen=True)
class InstitutionalThemeSummary:
    trade_date: str
    dominant_signal: str
    suggested_action: str
    candidates: List[Dict[str, Any]]
    target_stock: Dict[str, Any]


class AShareInstitutionalThemeAnalyzer:
    """识别机构可能正在提前布局的A股题材。"""

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
            "broken": self._safe_fetch("stock_zt_pool_zbgc_em", date=date),
            "strong": self._safe_fetch("stock_zt_pool_strong_em", date=date),
            "concept_boards": self._safe_fetch("stock_board_concept_name_em"),
            "industry_boards": self._safe_fetch("stock_board_industry_name_em"),
        }

    def _fetch_board_constituents(self, board_name: str, category: str) -> pd.DataFrame:
        if category == "concept":
            return self._safe_fetch("stock_board_concept_cons_em", symbol=board_name)
        return self._safe_fetch("stock_board_industry_cons_em", symbol=board_name)

    def _extract_boards(self, board_df: pd.DataFrame, category: str, limit: int = 12) -> List[Dict[str, Any]]:
        if board_df is None or board_df.empty:
            return []

        name_col = _pick_column(board_df, ["板块名称", "名称", "name"])
        change_col = _pick_column(board_df, ["涨跌幅", "涨跌幅%", "涨跌幅(%)"])
        amount_col = _pick_column(board_df, ["成交额", "成交金额", "总成交额"])
        if not name_col or not change_col:
            return []

        rows: List[Dict[str, Any]] = []
        for _, row in board_df.iterrows():
            name = str(row.get(name_col, "")).strip()
            if not name:
                continue
            rows.append(
                {
                    "name": name,
                    "category": category,
                    "change_pct": _to_float(row.get(change_col), 0.0),
                    "turnover": _to_float(row.get(amount_col), 0.0) if amount_col else 0.0,
                }
            )

        rows.sort(key=lambda item: (item["change_pct"], item["turnover"]), reverse=True)
        return rows[:limit]

    def _fallback_candidates_from_pools(
        self,
        zt_df: pd.DataFrame,
        strong_df: pd.DataFrame,
        broken_df: pd.DataFrame,
        target_symbol: str,
    ) -> List[InstitutionalThemeCandidate]:
        def _group(frame: pd.DataFrame) -> Dict[str, pd.DataFrame]:
            industry_col = _pick_column(frame, ["所属行业", "行业"])
            if not industry_col or frame.empty:
                return {}
            result: Dict[str, pd.DataFrame] = {}
            for industry, part in frame.groupby(industry_col):
                name = str(industry).strip()
                if name and name != "nan":
                    result[name] = part.copy()
            return result

        zt_map = _group(zt_df)
        strong_map = _group(strong_df)
        broken_map = _group(broken_df)
        industries = set(zt_map) | set(strong_map) | set(broken_map)
        code_candidates = ["代码", "证券代码", "symbol"]
        change_candidates = ["涨跌幅", "涨跌幅%", "涨跌幅(%)"]

        candidates: List[InstitutionalThemeCandidate] = []
        for industry in industries:
            zt_part = zt_map.get(industry, pd.DataFrame())
            strong_part = strong_map.get(industry, pd.DataFrame())
            broken_part = broken_map.get(industry, pd.DataFrame())

            codes: Set[str] = set()
            for frame in [zt_part, strong_part]:
                code_col = _pick_column(frame, code_candidates)
                if code_col and not frame.empty:
                    codes.update(
                        {
                            _normalize_symbol(str(code))
                            for code in frame[code_col].astype(str).tolist()
                            if str(code).strip()
                        }
                    )

            change_values = []
            for frame in [zt_part, strong_part, broken_part]:
                change_col = _pick_column(frame, change_candidates)
                if change_col and not frame.empty:
                    change_values.extend(pd.to_numeric(frame[change_col], errors="coerce").fillna(0).tolist())
            avg_change = float(sum(change_values) / len(change_values)) if change_values else 0.0

            news_info = self._search_news_mentions(industry)
            breadth_score = min(100.0, max(0.0, 20 + len(codes) * 6 + avg_change * 3))
            early_strength_score = min(100.0, max(0.0, 18 + len(strong_part) * 12 + avg_change * 4))
            news_catalyst_score = min(100.0, max(0.0, 10 + news_info["count"] * 2 + news_info["recent_count"] * 5))
            overheating_score = min(100.0, max(0.0, len(zt_part) * 12 + len(broken_part) * 9 + max(avg_change - 7, 0) * 6))
            institutional_layout_score = min(
                100.0,
                max(
                    0.0,
                    breadth_score * 0.28
                    + early_strength_score * 0.38
                    + news_catalyst_score * 0.24
                    + max(0.0, 25 - overheating_score) * 0.10,
                ),
            )

            if institutional_layout_score >= 68 and overheating_score <= 42 and len(zt_part) <= 2:
                stage = "试盘期"
            elif institutional_layout_score >= 58:
                stage = "酝酿期"
            else:
                stage = "观察期"

            leaders = []
            for frame in [zt_part, strong_part]:
                code_col = _pick_column(frame, code_candidates)
                if code_col and not frame.empty:
                    leaders.extend(
                        [_normalize_symbol(str(code)) for code in frame[code_col].astype(str).tolist() if str(code).strip()]
                    )
            leaders = list(dict.fromkeys(leaders))[:3]
            target_in_theme = target_symbol in codes
            target_role = "先手核心" if target_in_theme and target_symbol in leaders else ("趋势跟随" if target_in_theme else "非成员")

            candidates.append(
                InstitutionalThemeCandidate(
                    name=industry,
                    category="industry",
                    board_change_pct=round(avg_change, 2),
                    breadth_score=round(breadth_score, 2),
                    early_strength_score=round(early_strength_score, 2),
                    news_catalyst_score=round(news_catalyst_score, 2),
                    institutional_layout_score=round(institutional_layout_score, 2),
                    overheating_score=round(overheating_score, 2),
                    stage=stage,
                    rationale=f"板块榜单源不可用，改用涨停/强势池行业聚合估算。近14日相关新闻提及 {news_info['count']} 次。",
                    leaders=leaders,
                    test_positions=[code for code in leaders if code != target_symbol][:4],
                    target_in_theme=target_in_theme,
                    target_role=target_role,
                )
            )

        candidates.sort(
            key=lambda item: (item.institutional_layout_score, item.news_catalyst_score, item.early_strength_score, -item.overheating_score),
            reverse=True,
        )
        return candidates[:5]

    def _search_news_mentions(self, keyword: str) -> Dict[str, Any]:
        try:
            from tradingagents.config.database_manager import get_database_manager, get_mongodb_client

            client = get_mongodb_client()
            if not client:
                return {"count": 0, "recent_count": 0, "sources": []}

            db_name = get_database_manager().mongodb_config.get("database", "tradingagents")
            collection = client[db_name].stock_news
            now_dt = datetime.now()
            fourteen_days_ago = now_dt - timedelta(days=14)
            three_days_ago = now_dt - timedelta(days=3)
            regex = re.escape(keyword)

            query = {
                "publish_time": {"$gte": fourteen_days_ago},
                "$or": [
                    {"title": {"$regex": regex, "$options": "i"}},
                    {"content": {"$regex": regex, "$options": "i"}},
                    {"summary": {"$regex": regex, "$options": "i"}},
                ],
            }

            docs = list(collection.find(query, {"source": 1, "publish_time": 1}).sort("publish_time", -1).limit(80))
            if not docs:
                return {"count": 0, "recent_count": 0, "sources": []}

            recent_count = 0
            source_counter: Dict[str, int] = {}
            for doc in docs:
                source = doc.get("source", "unknown")
                source_counter[source] = source_counter.get(source, 0) + 1
                publish_time = doc.get("publish_time")
                if isinstance(publish_time, datetime) and publish_time >= three_days_ago:
                    recent_count += 1

            sources = [name for name, _count in sorted(source_counter.items(), key=lambda item: item[1], reverse=True)[:3]]
            return {"count": len(docs), "recent_count": recent_count, "sources": sources}
        except Exception:
            return {"count": 0, "recent_count": 0, "sources": []}

    def _build_candidate(
        self,
        board: Dict[str, Any],
        constituent_df: pd.DataFrame,
        zt_codes: Set[str],
        strong_codes: Set[str],
        broken_codes: Set[str],
        target_symbol: str,
    ) -> Optional[InstitutionalThemeCandidate]:
        if constituent_df is None or constituent_df.empty:
            return None

        code_col = _pick_column(constituent_df, ["代码", "证券代码", "symbol"])
        change_col = _pick_column(constituent_df, ["涨跌幅", "涨跌幅%", "涨跌幅(%)"])
        if not code_col:
            return None

        codes = [
            _normalize_symbol(str(code))
            for code in constituent_df[code_col].astype(str).tolist()
            if str(code).strip()
        ]
        if not codes:
            return None

        code_set = set(codes)
        limit_up_members = sorted(code_set & zt_codes)
        strong_members = sorted(code_set & strong_codes)
        broken_members = sorted(code_set & broken_codes)

        change_series = pd.to_numeric(constituent_df[change_col], errors="coerce").fillna(0) if change_col else pd.Series([0] * len(codes))
        up_count = int((change_series > 0).sum())
        avg_change = float(change_series.mean()) if len(change_series) else 0.0
        breadth_ratio = _safe_ratio(up_count, len(codes))
        early_strength_ratio = _safe_ratio(len(strong_members), len(codes))
        overheating_ratio = _safe_ratio(len(limit_up_members) + len(broken_members), max(len(codes), 1))

        news_info = self._search_news_mentions(board["name"])

        breadth_score = min(100.0, max(0.0, 20 + breadth_ratio * 55 + avg_change * 3.5))
        early_strength_score = min(
            100.0,
            max(0.0, 18 + len(strong_members) * 10 + board["change_pct"] * 4 + early_strength_ratio * 28 - len(limit_up_members) * 2),
        )
        news_catalyst_score = min(
            100.0,
            max(0.0, 10 + news_info["count"] * 2.0 + news_info["recent_count"] * 5.0),
        )
        overheating_score = min(
            100.0,
            max(0.0, len(limit_up_members) * 13 + len(broken_members) * 9 + max(board["change_pct"] - 6, 0) * 7 + overheating_ratio * 30),
        )
        institutional_layout_score = min(
            100.0,
            max(
                0.0,
                breadth_score * 0.28
                + early_strength_score * 0.34
                + news_catalyst_score * 0.24
                + max(0.0, 25 - overheating_score) * 0.14,
            ),
        )

        if institutional_layout_score >= 72 and overheating_score <= 42 and len(limit_up_members) <= 2:
            stage = "试盘期"
            rationale = "板块已有资金试探，强势股先行，但市场一致性尚未完全形成。"
        elif institutional_layout_score >= 64 and news_catalyst_score >= 24 and len(limit_up_members) <= 1:
            stage = "酝酿期"
            rationale = "催化在增强，板块广度和强势信号开始抬升，适合提前跟踪。"
        elif len(limit_up_members) >= 3 and breadth_score >= 65:
            stage = "扩散期"
            rationale = "板块进入扩散确认，更多是跟随确认而非纯提前埋伏。"
        else:
            stage = "观察期"
            rationale = "信号存在但仍偏弱，适合放入候选池持续跟踪。"

        leaders = limit_up_members[:3] or strong_members[:3]
        test_positions = [code for code in strong_members if code not in leaders][:4]
        target_in_theme = target_symbol in code_set
        if not target_in_theme:
            target_role = "非成员"
        elif target_symbol in leaders:
            target_role = "先手核心"
        elif target_symbol in test_positions:
            target_role = "试盘前排"
        elif target_symbol in strong_members:
            target_role = "趋势跟随"
        else:
            target_role = "边缘观察"

        return InstitutionalThemeCandidate(
            name=board["name"],
            category=board["category"],
            board_change_pct=round(board["change_pct"], 2),
            breadth_score=round(breadth_score, 2),
            early_strength_score=round(early_strength_score, 2),
            news_catalyst_score=round(news_catalyst_score, 2),
            institutional_layout_score=round(institutional_layout_score, 2),
            overheating_score=round(overheating_score, 2),
            stage=stage,
            rationale=f"{rationale} 近14日相关新闻提及 {news_info['count']} 次，近3日 {news_info['recent_count']} 次。",
            leaders=leaders,
            test_positions=test_positions,
            target_in_theme=target_in_theme,
            target_role=target_role,
        )

    def build_summary(self, ticker: str, trade_date: str, data: Dict[str, pd.DataFrame]) -> InstitutionalThemeSummary:
        target_symbol = _normalize_symbol(ticker)
        zt_df = data.get("zt", pd.DataFrame())
        strong_df = data.get("strong", pd.DataFrame())
        broken_df = data.get("broken", pd.DataFrame())
        concept_boards = data.get("concept_boards", pd.DataFrame())
        industry_boards = data.get("industry_boards", pd.DataFrame())

        def _codes(df: pd.DataFrame) -> Set[str]:
            code_col = _pick_column(df, ["代码", "证券代码", "symbol"])
            if not code_col:
                return set()
            return {
                _normalize_symbol(str(code))
                for code in df[code_col].astype(str).tolist()
                if str(code).strip()
            }

        zt_codes = _codes(zt_df)
        strong_codes = _codes(strong_df)
        broken_codes = _codes(broken_df)

        board_pool = self._extract_boards(concept_boards, "concept", 8) + self._extract_boards(industry_boards, "industry", 6)
        candidates: List[InstitutionalThemeCandidate] = []
        for board in board_pool:
            cons_df = self._fetch_board_constituents(board["name"], board["category"])
            candidate = self._build_candidate(board, cons_df, zt_codes, strong_codes, broken_codes, target_symbol)
            if candidate:
                candidates.append(candidate)

        if not candidates:
            candidates = self._fallback_candidates_from_pools(
                zt_df=zt_df,
                strong_df=strong_df,
                broken_df=broken_df,
                target_symbol=target_symbol,
            )

        candidates.sort(
            key=lambda item: (
                item.institutional_layout_score,
                item.news_catalyst_score,
                item.early_strength_score,
                -item.overheating_score,
            ),
            reverse=True,
        )
        top_candidates = candidates[:5]

        if not top_candidates:
            dominant_signal = "暂无明显机构布局题材"
            suggested_action = "当前更适合等待明确催化和先手信号。"
        else:
            best = top_candidates[0]
            if best.stage == "酝酿期":
                dominant_signal = f"{best.name} 进入酝酿期"
                suggested_action = "适合纳入前瞻跟踪池，等待核心票放量确认。"
            elif best.stage == "试盘期":
                dominant_signal = f"{best.name} 出现试盘痕迹"
                suggested_action = "可以围绕前排核心做小仓位先手，避免追逐后排。"
            elif best.stage == "扩散期":
                dominant_signal = f"{best.name} 已进入扩散确认"
                suggested_action = "更多属于确认交易，不再是纯提前埋伏。"
            else:
                dominant_signal = f"{best.name} 仍处观察阶段"
                suggested_action = "继续观察催化与强势股承接，暂不急于提前布局。"

        target_memberships = [item for item in top_candidates if item.target_in_theme]
        if target_memberships:
            target = target_memberships[0]
            target_payload = {
                "ticker": ticker,
                "candidate_themes": [item.name for item in target_memberships[:3]],
                "role": target.target_role,
                "best_stage": target.stage,
                "institutional_layout_score": target.institutional_layout_score,
                "suitable_for_early_positioning": target.stage in {"酝酿期", "试盘期"},
            }
        else:
            target_payload = {
                "ticker": ticker,
                "candidate_themes": [],
                "role": "独立逻辑/未进入候选布局题材",
                "best_stage": "观察期",
                "institutional_layout_score": 20.0,
                "suitable_for_early_positioning": False,
            }

        return InstitutionalThemeSummary(
            trade_date=trade_date,
            dominant_signal=dominant_signal,
            suggested_action=suggested_action,
            candidates=[asdict(item) for item in top_candidates],
            target_stock=target_payload,
        )

    def render_markdown(self, ticker: str, summary: InstitutionalThemeSummary) -> str:
        lines = [
            "## A股机构布局题材识别",
            "",
            f"**分析日期**: {summary.trade_date}",
            f"**主导信号**: **{summary.dominant_signal}**",
            f"**建议动作**: **{summary.suggested_action}**",
            "",
            "### 目标股前瞻定位",
            f"- 股票代码: **{ticker}**",
            f"- 候选题材: **{'、'.join(summary.target_stock.get('candidate_themes', [])) or '暂无'}**",
            f"- 角色: **{summary.target_stock.get('role', '未知')}**",
            f"- 最优阶段: **{summary.target_stock.get('best_stage', '观察期')}**",
            f"- 机构布局评分: **{summary.target_stock.get('institutional_layout_score', 0)}/100**",
            f"- 是否适合提前布局: **{'是' if summary.target_stock.get('suitable_for_early_positioning') else '否'}**",
            "",
            "### 前瞻候选题材 Top5",
        ]

        for idx, item in enumerate(summary.candidates, 1):
            lines.extend(
                [
                    f"#### {idx}. {item['name']} ({'概念' if item['category'] == 'concept' else '行业'})",
                    f"- 阶段: **{item['stage']}**",
                    f"- 板块涨跌幅: **{item['board_change_pct']:.2f}%**",
                    f"- 机构布局分: **{item['institutional_layout_score']}**",
                    f"- 广度分: **{item['breadth_score']}**",
                    f"- 先手强度分: **{item['early_strength_score']}**",
                    f"- 催化分: **{item['news_catalyst_score']}**",
                    f"- 过热分: **{item['overheating_score']}**",
                    f"- 先手核心: **{'、'.join(item['leaders']) if item['leaders'] else '暂无'}**",
                    f"- 试盘前排: **{'、'.join(item['test_positions']) if item['test_positions'] else '暂无'}**",
                    f"- 逻辑说明: {item['rationale']}",
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


def build_a_share_institutional_theme_report(ticker: str, trade_date: str) -> str:
    import akshare as ak

    analyzer = AShareInstitutionalThemeAnalyzer(ak)
    data = analyzer.collect(trade_date)
    summary = analyzer.build_summary(ticker=ticker, trade_date=trade_date, data=data)
    return analyzer.render_markdown(ticker=ticker, summary=summary)
