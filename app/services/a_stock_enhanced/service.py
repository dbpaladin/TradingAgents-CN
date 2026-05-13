from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from .announcements import AnnouncementsProvider
from .config import get_a_stock_enhanced_config
from .models import AnnouncementItem, EnhancedKlineBar, EnhancedQuote, F10Document, FinanceSnapshot, NorthboundIntradayPoint
from .mootdx_client import MootdxProvider
from .northbound import NorthboundProvider
from .tencent_quotes import TencentQuotesProvider
from .utils import coalesce, normalize_code


def _is_meaningful_number(value: Optional[float]) -> bool:
    return value is not None and abs(value) > 1e-12


class AStockEnhancedService:
    """Sidecar PoC service for A-share enhanced data.

    This service is intentionally not wired into the main data source manager.
    Callers must opt in explicitly.
    """

    def __init__(self) -> None:
        self.config = get_a_stock_enhanced_config()
        self.tencent = TencentQuotesProvider()
        self.mootdx = MootdxProvider()
        self.northbound = NorthboundProvider()
        self.announcements = AnnouncementsProvider()
        self._northbound_cache: List[NorthboundIntradayPoint] = []
        self._northbound_cache_ts: float = 0.0
        self._northbound_lock = asyncio.Lock()

    def get_quote_enhanced(self, code: str) -> Optional[EnhancedQuote]:
        code6 = normalize_code(code)
        tencent_quote = self.tencent.fetch_quotes([code6]).get(code6)
        mootdx_quote = self.mootdx.get_realtime_quote(code6)
        if tencent_quote is None and mootdx_quote is None:
            return None

        quote = EnhancedQuote(code=code6, source="a_stock_enhanced")
        if tencent_quote:
            quote.name = tencent_quote.name
            quote.price = tencent_quote.price
            quote.pre_close = tencent_quote.pre_close
            quote.open = tencent_quote.open
            quote.high = tencent_quote.high
            quote.low = tencent_quote.low
            quote.pct_chg = tencent_quote.pct_chg
            quote.change_amt = tencent_quote.change_amt
            quote.amount = tencent_quote.amount
            quote.turnover_rate = tencent_quote.turnover_rate
            quote.pe_ttm = tencent_quote.pe_ttm
            quote.pe_static = tencent_quote.pe_static
            quote.pb = tencent_quote.pb
            quote.total_mv = tencent_quote.total_mv
            quote.circ_mv = tencent_quote.circ_mv
            quote.limit_up = tencent_quote.limit_up
            quote.limit_down = tencent_quote.limit_down
            quote.vol_ratio = tencent_quote.vol_ratio
            quote.raw["tencent"] = tencent_quote.raw
        if mootdx_quote:
            # Prefer mootdx trade-layer values when present.
            if _is_meaningful_number(mootdx_quote.price):
                quote.price = mootdx_quote.price
            if _is_meaningful_number(mootdx_quote.pre_close):
                quote.pre_close = mootdx_quote.pre_close
            if _is_meaningful_number(mootdx_quote.open):
                quote.open = mootdx_quote.open
            if _is_meaningful_number(mootdx_quote.high):
                quote.high = mootdx_quote.high
            if _is_meaningful_number(mootdx_quote.low):
                quote.low = mootdx_quote.low
            if _is_meaningful_number(mootdx_quote.volume):
                quote.volume = mootdx_quote.volume
            if _is_meaningful_number(mootdx_quote.amount):
                quote.amount = mootdx_quote.amount
            quote.raw["mootdx"] = mootdx_quote.raw
        return quote

    def get_quotes_enhanced(self, codes: List[str]) -> Dict[str, EnhancedQuote]:
        return {
            normalize_code(code): quote
            for code in codes
            if (quote := self.get_quote_enhanced(code)) is not None
        }

    def get_kline_enhanced(self, code: str, period: str = "day", limit: int = 120) -> List[EnhancedKlineBar]:
        return self.mootdx.get_kline(code=code, period=period, limit=limit)

    def get_finance_snapshot(self, code: str) -> Optional[FinanceSnapshot]:
        return self.mootdx.get_finance_snapshot(code=code)

    def get_f10_document(self, code: str, category: str) -> Optional[F10Document]:
        return self.mootdx.get_f10_document(code=code, category=category)

    async def get_northbound_intraday(self, force_refresh: bool = False) -> List[NorthboundIntradayPoint]:
        async with self._northbound_lock:
            now = time.time()
            if (
                not force_refresh
                and self._northbound_cache
                and (now - self._northbound_cache_ts) < self.config.northbound_ttl_seconds
            ):
                return self._northbound_cache
            items = await asyncio.to_thread(self.northbound.get_intraday)
            self._northbound_cache = items
            self._northbound_cache_ts = time.time()
            return items

    def get_announcements(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
    ) -> List[AnnouncementItem]:
        return self.announcements.get_announcements(
            code=code,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )


_a_stock_enhanced_service: Optional[AStockEnhancedService] = None


def get_a_stock_enhanced_service() -> AStockEnhancedService:
    global _a_stock_enhanced_service
    if _a_stock_enhanced_service is None:
        _a_stock_enhanced_service = AStockEnhancedService()
    return _a_stock_enhanced_service
