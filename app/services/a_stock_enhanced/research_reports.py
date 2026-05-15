from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .config import get_a_stock_enhanced_config
from .models import ResearchReportItem
from .utils import normalize_code

logger = logging.getLogger(__name__)


class ResearchReportsProvider:
    """East China (Dongcai) research reports provider.

    Uses akshare interface to fetch research reports for A-share stocks.
    """
    source_name = "em_research_reports"

    def __init__(self) -> None:
        self.config = get_a_stock_enhanced_config()

    def get_reports(
        self,
        code: str,
        limit: int = 10,
    ) -> List[ResearchReportItem]:
        """Fetch research reports for a given stock code."""
        if not self.config.enabled or not self.config.research_reports_enabled:
            return []
        code6 = normalize_code(code)
        try:
            import akshare as ak

            df = ak.stock_research_report_em(symbol=code6)
            if df is None or getattr(df, "empty", True):
                return []

            items: List[ResearchReportItem] = []
            for _, row in df.head(limit).iterrows():
                raw = row.to_dict() if hasattr(row, "to_dict") else {}
                items.append(
                    ResearchReportItem(
                        code=code6,
                        title=str(
                            row.get("title")
                            or row.get("报告名称")
                            or row.get("研报标题")
                            or row.get("infoCode")
                            or ""
                        ),
                        org=str(
                            row.get("orgSName")
                            or row.get("org")
                            or row.get("机构")
                            or ""
                        ),
                        publish_date=str(
                            row.get("publishDate")
                            or row.get("publish_date")
                            or row.get("日期")
                            or ""
                        ),
                        rating=str(
                            row.get("emRatingName")
                            or row.get("rating")
                            or row.get("东财评级")
                            or row.get("评级")
                            or ""
                        ),
                        last_rating=str(
                            row.get("lastEmRatingName")
                            or row.get("last_rating")
                            or row.get("上次评级")
                            or ""
                        ),
                        rating_change=str(
                            row.get("ratingChange")
                            or row.get("rating_change")
                            or row.get("评级变化")
                            or ""
                        ),
                        eps_forecast_1y=self._safe_num(
                            row.get("predictThisYearEps")
                            or row.get("2026-盈利预测-收益")
                            or row.get("本年盈利预测")
                        ),
                        eps_forecast_2y=self._safe_num(
                            row.get("predictNextYearEps")
                            or row.get("2027-盈利预测-收益")
                            or row.get("次年盈利预测")
                        ),
                        eps_forecast_3y=self._safe_num(
                            row.get("predictNextTwoYearEps")
                            or row.get("2028-盈利预测-收益")
                            or row.get("后年盈利预测")
                        ),
                        source=self.source_name,
                        raw=raw,
                    )
                )
            return items
        except Exception as exc:
            logger.warning("research reports fetch failed for %s: %s", code6, exc)
            return []

    @staticmethod
    def _safe_num(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
