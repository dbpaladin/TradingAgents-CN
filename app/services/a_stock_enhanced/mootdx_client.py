from __future__ import annotations

import logging
from typing import List, Optional

from .config import get_a_stock_enhanced_config
from .models import EnhancedKlineBar, EnhancedQuote, F10Document, FinanceSnapshot
from .utils import coalesce, normalize_code, safe_float

logger = logging.getLogger(__name__)


class MootdxProvider:
    source_name = "mootdx"

    def __init__(self) -> None:
        self.config = get_a_stock_enhanced_config()
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.config.enabled or not self.config.mootdx_enabled:
            return None
        try:
            from mootdx.quotes import Quotes

            self._client = Quotes.factory(market="std")
            return self._client
        except Exception as exc:
            logger.warning("mootdx init failed: %s", exc)
            return None

    def get_realtime_quote(self, code: str) -> Optional[EnhancedQuote]:
        client = self._get_client()
        if client is None:
            return None
        code6 = normalize_code(code)
        try:
            df = client.quotes(symbol=[code6])
            if df is None or getattr(df, "empty", True):
                return None
            row = df.iloc[0]
            return EnhancedQuote(
                code=code6,
                price=safe_float(row.get("price")),
                pre_close=safe_float(row.get("last_close")),
                open=safe_float(row.get("open")),
                high=safe_float(row.get("high")),
                low=safe_float(row.get("low")),
                volume=safe_float(row.get("vol")),
                amount=safe_float(row.get("amount")),
                source=self.source_name,
                raw=row.to_dict() if hasattr(row, "to_dict") else {},
            )
        except Exception as exc:
            logger.warning("mootdx quote failed for %s: %s", code6, exc)
            return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120) -> List[EnhancedKlineBar]:
        client = self._get_client()
        if client is None:
            return []
        code6 = normalize_code(code)
        category_map = {
            "day": 4,
            "week": 5,
            "month": 6,
            "1m": 7,
            "5m": 8,
            "15m": 9,
            "30m": 10,
            "60m": 11,
        }
        category = category_map.get(period, 4)
        try:
            df = client.bars(symbol=code6, category=category, offset=limit)
            if df is None or getattr(df, "empty", True):
                return []
            items: List[EnhancedKlineBar] = []
            for _, row in df.tail(limit).iterrows():
                time_text = coalesce(
                    row.get("datetime"),
                    row.get("date"),
                )
                if time_text is None:
                    year = row.get("year")
                    month = row.get("month")
                    day = row.get("day")
                    hour = row.get("hour")
                    minute = row.get("minute")
                    if year and month and day:
                        if hour is not None and minute is not None:
                            time_text = f"{int(year):04d}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d}"
                        else:
                            time_text = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                items.append(
                    EnhancedKlineBar(
                        code=code6,
                        time=str(time_text or ""),
                        open=safe_float(row.get("open")),
                        high=safe_float(row.get("high")),
                        low=safe_float(row.get("low")),
                        close=safe_float(row.get("close")),
                        volume=safe_float(row.get("vol")),
                        amount=safe_float(row.get("amount")),
                        period=period,
                        source=self.source_name,
                    )
                )
            return items
        except Exception as exc:
            logger.warning("mootdx kline failed for %s: %s", code6, exc)
            return []

    def get_finance_snapshot(self, code: str) -> Optional[FinanceSnapshot]:
        client = self._get_client()
        if client is None:
            return None
        code6 = normalize_code(code)
        try:
            df = client.finance(symbol=code6)
            if df is None or getattr(df, "empty", True):
                return None
            row = df.iloc[0]
            return FinanceSnapshot(
                code=code6,
                report_date=str(row.get("updated_date") or ""),
                revenue=safe_float(row.get("zhuyingshouru")),
                net_profit=safe_float(row.get("jinglirun")),
                total_share=safe_float(row.get("zongguben")),
                float_share=safe_float(row.get("liutongguben")),
                bps=safe_float(row.get("meigujingzichan")),
                undistributed_profit=safe_float(row.get("weifenpeilirun")),
                source=self.source_name,
                raw=row.to_dict() if hasattr(row, "to_dict") else {},
            )
        except Exception as exc:
            logger.warning("mootdx finance failed for %s: %s", code6, exc)
            return None

    def get_f10_document(self, code: str, category: str) -> Optional[F10Document]:
        client = self._get_client()
        if client is None:
            return None
        code6 = normalize_code(code)
        try:
            text = client.F10(symbol=code6, name=category)
            if text is None:
                return None
            content = str(text)
            title = content.splitlines()[0].strip() if content.splitlines() else category
            return F10Document(
                code=code6,
                category=category,
                title=title,
                content=content,
                source=self.source_name,
            )
        except Exception as exc:
            logger.warning("mootdx F10 failed for %s/%s: %s", code6, category, exc)
            return None
