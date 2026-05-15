from __future__ import annotations

import logging
from typing import List, Optional

from .config import get_a_stock_enhanced_config
from .models import AnnouncementItem
from .utils import normalize_code

logger = logging.getLogger(__name__)


class AnnouncementsProvider:
    source_name = "cninfo_akshare"

    def __init__(self) -> None:
        self.config = get_a_stock_enhanced_config()

    def get_announcements(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
    ) -> List[AnnouncementItem]:
        if not self.config.enabled or not self.config.announcements_enabled:
            return []
        code6 = normalize_code(code)
        try:
            import akshare as ak

            kwargs = {
                "symbol": code6,
                "market": "沪深京",
            }
            if start_date:
                kwargs["start_date"] = start_date.replace("-", "")
            if end_date:
                kwargs["end_date"] = end_date.replace("-", "")
            df = ak.stock_zh_a_disclosure_report_cninfo(**kwargs)
            if df is None or getattr(df, "empty", True):
                return []
            items: List[AnnouncementItem] = []
            for _, row in df.head(limit).iterrows():
                items.append(
                    AnnouncementItem(
                        code=code6,
                        title=str(row.get("公告标题") or row.get("title") or ""),
                        publish_time=str(row.get("公告时间") or row.get("time") or ""),
                        url=str(row.get("公告链接") or row.get("url") or ""),
                        source=self.source_name,
                        raw=row.to_dict() if hasattr(row, "to_dict") else {},
                    )
                )
            return items
        except Exception as exc:
            logger.warning("announcements fetch failed for %s: %s", code6, exc)
            return []
