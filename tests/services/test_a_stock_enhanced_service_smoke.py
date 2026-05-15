from __future__ import annotations

import asyncio

from app.services.a_stock_enhanced.models import (
    AnnouncementItem,
    EnhancedKlineBar,
    EnhancedQuote,
    NorthboundIntradayPoint,
    ResearchReportItem,
)
from app.services.a_stock_enhanced.service import AStockEnhancedService


def test_get_quote_enhanced_prefers_mootdx_trade_values() -> None:
    service = AStockEnhancedService()

    service.tencent.fetch_quotes = lambda codes: {
        "000001": EnhancedQuote(
            code="000001",
            name="PingAn",
            price=10.0,
            pre_close=9.8,
            open=9.9,
            high=10.2,
            low=9.7,
            amount=1000.0,
            source="tencent",
            raw={"provider": "tencent"},
        )
    }
    service.mootdx.get_realtime_quote = lambda code: EnhancedQuote(
        code="000001",
        price=10.3,
        pre_close=9.9,
        open=10.0,
        high=10.5,
        low=9.8,
        volume=12345.0,
        amount=2000.0,
        source="mootdx",
        raw={"provider": "mootdx"},
    )

    quote = service.get_quote_enhanced("000001")

    assert quote is not None
    assert quote.code == "000001"
    assert quote.name == "PingAn"
    assert quote.price == 10.3
    assert quote.amount == 2000.0
    assert quote.raw["tencent"]["provider"] == "tencent"
    assert quote.raw["mootdx"]["provider"] == "mootdx"


def test_get_kline_announcements_and_reports_smoke() -> None:
    service = AStockEnhancedService()

    service.mootdx.get_kline = lambda code, period, limit: [
        EnhancedKlineBar(code=code, time="2026-05-14", close=10.2, period=period, source="mootdx"),
        EnhancedKlineBar(code=code, time="2026-05-15", close=10.4, period=period, source="mootdx"),
    ]
    service.announcements.get_announcements = lambda code, start_date=None, end_date=None, limit=20: [
        AnnouncementItem(code=code, title="Mock Announcement", source="mock"),
    ]
    service.research_reports.get_reports = lambda code, limit=10: [
        ResearchReportItem(code=code, title="Mock Report", org="MockOrg", source="mock"),
    ]

    kline = service.get_kline_enhanced("000001", period="day", limit=2)
    anns = service.get_announcements("000001", limit=1)
    reports = service.get_research_reports("000001", limit=1)

    assert len(kline) == 2
    assert anns[0].title == "Mock Announcement"
    assert reports[0].title == "Mock Report"


def test_northbound_cache_ttl_behavior() -> None:
    service = AStockEnhancedService()
    calls = {"count": 0}

    def _mock_get_intraday():
        calls["count"] += 1
        return [NorthboundIntradayPoint(time="10:00", northbound_total=1.0, source="mock")]

    service.northbound.get_intraday = _mock_get_intraday

    first = asyncio.run(service.get_northbound_intraday())
    second = asyncio.run(service.get_northbound_intraday())
    forced = asyncio.run(service.get_northbound_intraday(force_refresh=True))

    assert len(first) == 1
    assert len(second) == 1
    assert len(forced) == 1
    assert calls["count"] == 2
