#!/usr/bin/env python3
"""
Smoke validation script for the sidecar A-share enhanced module.

This script is intentionally isolated from production routing and data flows.
By default it runs in offline mode with mocked providers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.services.a_stock_enhanced.models import (  # noqa: E402
    AnnouncementItem,
    EnhancedKlineBar,
    EnhancedQuote,
    NorthboundIntradayPoint,
    ResearchReportItem,
)
from app.services.a_stock_enhanced.service import get_a_stock_enhanced_service  # noqa: E402


def _install_offline_mocks(service) -> None:
    service.tencent.fetch_quotes = lambda codes: {
        "000001": EnhancedQuote(code="000001", name="PingAn", price=10.1, pre_close=9.9, source="mock_tencent")
    }
    service.mootdx.get_realtime_quote = lambda code: EnhancedQuote(
        code="000001",
        price=10.2,
        volume=12000.0,
        amount=1500.0,
        source="mock_mootdx",
    )
    service.mootdx.get_kline = lambda code, period, limit: [
        EnhancedKlineBar(code=code, time="2026-05-14", close=10.0, period=period, source="mock"),
        EnhancedKlineBar(code=code, time="2026-05-15", close=10.2, period=period, source="mock"),
    ]
    service.northbound.get_intraday = lambda: [
        NorthboundIntradayPoint(time="10:00", northbound_total=12.5, source="mock")
    ]
    service.announcements.get_announcements = lambda code, start_date=None, end_date=None, limit=20: [
        AnnouncementItem(code=code, title="Mock announcement", source="mock")
    ]
    service.research_reports.get_reports = lambda code, limit=10: [
        ResearchReportItem(code=code, title="Mock report", org="MockOrg", source="mock")
    ]


async def _run(code: str, offline: bool) -> Dict[str, Any]:
    service = get_a_stock_enhanced_service()
    if offline:
        _install_offline_mocks(service)

    quote = service.get_quote_enhanced(code)
    kline = service.get_kline_enhanced(code, period="day", limit=5)
    northbound = await service.get_northbound_intraday()
    announcements = service.get_announcements(code, limit=3)
    reports = service.get_research_reports(code, limit=3)

    return {
        "code": code,
        "offline": offline,
        "quote": quote.__dict__ if quote else None,
        "kline_count": len(kline),
        "northbound_count": len(northbound),
        "announcement_count": len(announcements),
        "research_report_count": len(reports),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate sidecar a_stock_enhanced module")
    parser.add_argument("--code", default="000001", help="A-share stock code")
    parser.add_argument("--offline", action="store_true", default=True, help="Run with mocked providers")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    result = asyncio.run(_run(args.code, args.offline))
    text = json.dumps(result, ensure_ascii=False, default=str, indent=2)
    print(text)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
