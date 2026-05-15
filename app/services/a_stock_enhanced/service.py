from __future__ import annotations

import asyncio
import logging
import hashlib
import time
from typing import Any, Dict, List, Optional

from .announcements import AnnouncementsProvider
from .config import get_a_stock_enhanced_config
from .models import AnnouncementItem, EnhancedKlineBar, EnhancedQuote, F10Document, FinanceSnapshot, NorthboundIntradayPoint, ResearchReportItem
from .mootdx_client import MootdxProvider
from .northbound import NorthboundProvider
from .research_reports import ResearchReportsProvider
from .tencent_quotes import TencentQuotesProvider
from .utils import coalesce, normalize_code, safe_float


logger = logging.getLogger(__name__)


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
        self.research_reports = ResearchReportsProvider()
        self._northbound_cache: List[NorthboundIntradayPoint] = []
        self._northbound_cache_ts: float = 0.0
        self._northbound_lock = asyncio.Lock()
        self._tushare_provider = None
        self._tushare_ready: Optional[bool] = None
        self._tushare_lock = asyncio.Lock()
        self._finance_source = self._normalize_source(
            self.config.finance_source, allowed={"tushare", "mootdx", "hybrid"}, default="hybrid"
        )
        self._northbound_source = self._normalize_source(
            self.config.northbound_source, allowed={"tushare", "ths", "hybrid"}, default="hybrid"
        )

    @staticmethod
    def _normalize_source(value: str, allowed: set[str], default: str) -> str:
        text = (value or "").strip().lower()
        return text if text in allowed else default

    @staticmethod
    def _in_gray_bucket(key: str, ratio: int) -> bool:
        if ratio <= 0:
            return False
        if ratio >= 100:
            return True
        digest = hashlib.md5(str(key).encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bucket < ratio

    @staticmethod
    def _bucket_value(key: str) -> int:
        digest = hashlib.md5(str(key).encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100

    @staticmethod
    def _to_ts_code(code: str) -> str:
        code6 = normalize_code(code)
        if code6.startswith(("6", "9")):
            return f"{code6}.SH"
        if code6.startswith("8"):
            return f"{code6}.BJ"
        return f"{code6}.SZ"

    def _get_tushare_provider_sync(self):
        if not self.config.tushare_enabled:
            return None
        if self._tushare_ready is False:
            return None
        if self._tushare_provider is not None and self._tushare_ready:
            return self._tushare_provider
        try:
            from tradingagents.dataflows.providers.china.tushare import TushareProvider

            provider = TushareProvider()
            if provider.connect_sync():
                self._tushare_provider = provider
                self._tushare_ready = True
                return provider
        except Exception:
            pass
        self._tushare_ready = False
        return None

    async def _get_tushare_provider_async(self):
        if not self.config.tushare_enabled:
            return None
        if self._tushare_ready is False:
            return None
        if self._tushare_provider is not None and self._tushare_ready:
            return self._tushare_provider
        async with self._tushare_lock:
            if self._tushare_provider is not None and self._tushare_ready:
                return self._tushare_provider
            try:
                from tradingagents.dataflows.providers.china.tushare import TushareProvider

                provider = TushareProvider()
                ok = await provider.connect()
                if ok:
                    self._tushare_provider = provider
                    self._tushare_ready = True
                    return provider
            except Exception:
                pass
            self._tushare_ready = False
            return None

    def _get_finance_snapshot_from_tushare(self, code: str) -> Optional[FinanceSnapshot]:
        provider = self._get_tushare_provider_sync()
        if provider is None or provider.api is None:
            return None

        code6 = normalize_code(code)
        ts_code = self._to_ts_code(code6)
        raw: Dict[str, Any] = {}
        try:
            basic_df = provider.api.stock_basic(
                ts_code=ts_code,
                fields="ts_code,name,total_share,float_share",
            )
            if basic_df is not None and not basic_df.empty:
                raw["stock_basic"] = basic_df.iloc[0].to_dict()
        except Exception:
            pass

        try:
            income_df = provider.api.income(ts_code=ts_code, limit=1)
            if income_df is not None and not income_df.empty:
                raw["income"] = income_df.iloc[0].to_dict()
        except Exception:
            pass

        try:
            fina_df = provider.api.fina_indicator(ts_code=ts_code, limit=1)
            if fina_df is not None and not fina_df.empty:
                raw["fina_indicator"] = fina_df.iloc[0].to_dict()
        except Exception:
            pass

        if not raw:
            return None

        basic = raw.get("stock_basic", {})
        income = raw.get("income", {})
        fina = raw.get("fina_indicator", {})
        report_date = (
            str(coalesce(fina.get("end_date"), income.get("end_date"), "")) if (fina or income) else None
        )
        revenue = safe_float(coalesce(income.get("total_revenue"), income.get("revenue")))
        net_profit = safe_float(coalesce(income.get("n_income_attr_p"), income.get("n_income")))
        bps = safe_float(fina.get("bps"))
        undistributed_profit = safe_float(coalesce(fina.get("undist_profit_ps"), fina.get("retainedps")))

        snapshot = FinanceSnapshot(
            code=code6,
            name=basic.get("name"),
            report_date=report_date,
            revenue=revenue,
            net_profit=net_profit,
            total_share=safe_float(basic.get("total_share")),
            float_share=safe_float(basic.get("float_share")),
            bps=bps,
            undistributed_profit=undistributed_profit,
            source="tushare",
            raw=raw,
        )
        return snapshot

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
        code6 = normalize_code(code)
        source = self._finance_source
        ratio = max(0, min(100, int(self.config.finance_tushare_ratio)))
        tushare_snapshot = None
        mootdx_snapshot = None
        bucket = self._bucket_value(code6)

        should_try_tushare = source == "tushare" or (
            source == "hybrid" and bucket < ratio
        )
        if should_try_tushare:
            tushare_snapshot = self._get_finance_snapshot_from_tushare(code6)
        if source in {"mootdx", "hybrid"}:
            mootdx_snapshot = self.mootdx.get_finance_snapshot(code=code6)

        if source == "tushare":
            selected = "tushare" if tushare_snapshot else ("mootdx_fallback" if mootdx_snapshot else "none")
            logger.info(
                "[a_stock_enhanced][finance] code=%s source=%s ratio=%s bucket=%s selected=%s",
                code6, source, ratio, bucket, selected
            )
            return tushare_snapshot or mootdx_snapshot
        if source == "mootdx":
            selected = "mootdx" if mootdx_snapshot else ("tushare_fallback" if tushare_snapshot else "none")
            logger.info(
                "[a_stock_enhanced][finance] code=%s source=%s ratio=%s bucket=%s selected=%s",
                code6, source, ratio, bucket, selected
            )
            return mootdx_snapshot or tushare_snapshot

        if tushare_snapshot and mootdx_snapshot:
            if tushare_snapshot.name is None:
                tushare_snapshot.name = mootdx_snapshot.name
            if tushare_snapshot.revenue is None:
                tushare_snapshot.revenue = mootdx_snapshot.revenue
            if tushare_snapshot.net_profit is None:
                tushare_snapshot.net_profit = mootdx_snapshot.net_profit
            if tushare_snapshot.total_share is None:
                tushare_snapshot.total_share = mootdx_snapshot.total_share
            if tushare_snapshot.float_share is None:
                tushare_snapshot.float_share = mootdx_snapshot.float_share
            if tushare_snapshot.bps is None:
                tushare_snapshot.bps = mootdx_snapshot.bps
            if tushare_snapshot.undistributed_profit is None:
                tushare_snapshot.undistributed_profit = mootdx_snapshot.undistributed_profit
            tushare_snapshot.raw["mootdx_fallback"] = mootdx_snapshot.raw
            logger.info(
                "[a_stock_enhanced][finance] code=%s source=%s ratio=%s bucket=%s selected=hybrid(tushare+fallback)",
                code6, source, ratio, bucket
            )
            return tushare_snapshot
        selected = "tushare" if tushare_snapshot else ("mootdx" if mootdx_snapshot else "none")
        logger.info(
            "[a_stock_enhanced][finance] code=%s source=%s ratio=%s bucket=%s selected=%s",
            code6, source, ratio, bucket, selected
        )
        return tushare_snapshot or mootdx_snapshot

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
            items: List[NorthboundIntradayPoint] = []
            source = self._northbound_source
            ratio = max(0, min(100, int(self.config.northbound_tushare_ratio)))

            async def _from_tushare() -> List[NorthboundIntradayPoint]:
                provider = await self._get_tushare_provider_async()
                if not provider or provider.api is None:
                    return []
                try:
                    trade_date = time.strftime("%Y%m%d")
                    df = await asyncio.to_thread(
                        provider.api.moneyflow_hsgt,
                        trade_date=trade_date,
                    )
                    if df is None or getattr(df, "empty", True):
                        return []
                    row = df.iloc[0]
                    hgt_value = safe_float(row.get("hgt"))
                    sgt_value = safe_float(row.get("sgt"))
                    total = safe_float(row.get("north_money"))
                    if total is None and (hgt_value is not None or sgt_value is not None):
                        total = (hgt_value or 0.0) + (sgt_value or 0.0)
                    return [
                        NorthboundIntradayPoint(
                            time="close",
                            hgt_net_buy=hgt_value,
                            sgt_net_buy=sgt_value,
                            northbound_total=total,
                            source="tushare_moneyflow_hsgt",
                            trade_date=str(row.get("trade_date") or ""),
                        )
                    ]
                except Exception:
                    return []

            async def _from_ths() -> List[NorthboundIntradayPoint]:
                return await asyncio.to_thread(self.northbound.get_intraday)

            if source == "tushare":
                items = await _from_tushare()
                if not items:
                    items = await _from_ths()
            elif source == "ths":
                items = await _from_ths()
                if not items:
                    items = await _from_tushare()
            else:
                key = f"northbound:{time.strftime('%Y%m%d')}"
                bucket = self._bucket_value(key)
                if bucket < ratio:
                    items = await _from_tushare()
                    if not items:
                        items = await _from_ths()
                else:
                    items = await _from_ths()
                    if not items:
                        items = await _from_tushare()
            final_source = items[0].source if items else "none"
            logger.info(
                "[a_stock_enhanced][northbound] source=%s ratio=%s selected=%s count=%s",
                source, ratio, final_source, len(items)
            )
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

    def get_research_reports(
        self,
        code: str,
        limit: int = 10,
    ) -> List[ResearchReportItem]:
        return self.research_reports.get_reports(
            code=code,
            limit=limit,
        )


_a_stock_enhanced_service: Optional[AStockEnhancedService] = None


def get_a_stock_enhanced_service() -> AStockEnhancedService:
    global _a_stock_enhanced_service
    if _a_stock_enhanced_service is None:
        _a_stock_enhanced_service = AStockEnhancedService()
    return _a_stock_enhanced_service
