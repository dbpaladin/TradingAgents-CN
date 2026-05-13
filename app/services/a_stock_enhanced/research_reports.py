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
                items.append(
                    ResearchReportItem(
                        code=code6,
                        title=str(row.get("title") or row.get("infoCode") or ""),
                        org=str(row.get("orgSName") or row.get("org") or ""),
                        publish_date=str(row.get("publishDate") or row.get("publish_date") or ""),
                        rating=str(row.get("emRatingName") or row.get("rating") or ""),
                        last_rating=str(row.get("lastEmRatingName") or row.get("last_rating") or ""),
                        rating_change=str(row.get("ratingChange") or row.get("rating_change") or ""),
                        eps_forecast_1y=self._safe_num(row.get("predictThisYearEps")),
                        eps_forecast_2y=self._safe_num(row.get("predictNextYearEps")),
                        eps_forecast_3y=self._safe_num(row.get("predictNextTwoYearEps")),
                        source=self.source_name,
                        raw=row.to_dict() if hasattr(row, "to_dict") else {},
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