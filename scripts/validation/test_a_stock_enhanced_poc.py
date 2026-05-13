#!/usr/bin/env python3
"""
Smoke test for the sidecar A-share enhanced PoC.

This script is intentionally read-only and does not write to application
collections. It helps us validate endpoint availability before integrating the
service into any product flow.
"""

from __future__ import annotations

import asyncio
import json

from app.services.a_stock_enhanced import get_a_stock_enhanced_service


async def main() -> None:
    svc = get_a_stock_enhanced_service()
    code = "000001"

    quote = svc.get_quote_enhanced(code)
    kline = svc.get_kline_enhanced(code, period="day", limit=5)
    northbound = await svc.get_northbound_intraday()
    announcements = svc.get_announcements(code, limit=3)

    result = {
        "quote": quote.__dict__ if quote else None,
        "kline_count": len(kline),
        "northbound_count": len(northbound),
        "announcement_count": len(announcements),
    }
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
