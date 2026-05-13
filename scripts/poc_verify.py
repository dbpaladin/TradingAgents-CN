#!/usr/bin/env python3
"""
PoC Verification Script for A-Stock Enhanced Data Source.

This script validates all enhanced data endpoints and records results
for the 3-5 trading day observation period.

Usage:
    python scripts/poc_verify.py --code 000938 --output eval_results/poc_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def run_test(name: str, test_fn, results: Dict[str, Any], test_results: Dict[str, Any]) -> None:
    """Run a single test and record results."""
    print(f"\n[{name}]")
    t0 = time.time()
    try:
        result = test_fn()
        elapsed = time.time() - t0
        test_results[name] = {"status": "pass", "elapsed_s": round(elapsed, 3), "result": result}
        print(f"  PASS - {result}")
    except Exception as exc:
        elapsed = time.time() - t0
        test_results[name] = {"status": "fail", "elapsed_s": round(elapsed, 3), "error": str(exc)}
        print(f"  FAIL - {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC Verification for A-Stock Enhanced Data Source")
    parser.add_argument("--code", default="000938", help="Stock code to test (default: 000938)")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--period", default="day", help="Kline period (default: day)")
    parser.add_argument("--kline-limit", type=int, default=30, help="Kline limit (default: 30)")
    parser.add_argument("--ann-limit", type=int, default=10, help="Announcements limit (default: 10)")
    parser.add_argument("--report-limit", type=int, default=10, help="Research reports limit (default: 10)")
    args = parser.parse_args()

    if args.output is None:
        args.output = f"eval_results/poc_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{args.code}.json"

    results: Dict[str, Any] = {
        "code": args.code,
        "timestamp": datetime.now().isoformat(),
        "tests": {},
    }

    print(f"PoC Verification for {args.code}")
    print("=" * 60)

    # Import service
    from app.services.a_stock_enhanced import get_a_stock_enhanced_service
    service = get_a_stock_enhanced_service()

    # Test 1: Enhanced Quote
    def test_quote():
        quote = service.get_quote_enhanced(args.code)
        if not quote:
            raise ValueError("Quote returned None")
        return f"{quote.name} @ {quote.price} (PE: {quote.pe_ttm}, PB: {quote.pb})"

    run_test("Testing Enhanced Quote...", test_quote, results, results["tests"])

    # Test 2: Kline
    def test_kline():
        klines = service.get_kline_enhanced(code=args.code, period=args.period, limit=args.kline_limit)
        if not klines:
            raise ValueError("Kline returned empty list")
        return f"{len(klines)} bars ({klines[0].time} to {klines[-1].time})"

    run_test("Testing Enhanced Kline...", test_kline, results, results["tests"])

    # Test 3: Finance Snapshot
    def test_finance():
        snap = service.get_finance_snapshot(args.code)
        if not snap:
            raise ValueError("Finance snapshot returned None")
        return f"Report date: {snap.report_date}, Revenue: {snap.revenue}"

    run_test("Testing Finance Snapshot...", test_finance, results, results["tests"])

    # Test 4: Announcements
    def test_announcements():
        anns = service.get_announcements(code=args.code, limit=args.ann_limit)
        if not anns:
            raise ValueError("Announcements returned empty list")
        return f"{len(anns)} announcements"

    run_test("Testing Announcements...", test_announcements, results, results["tests"])

    # Test 5: Research Reports
    def test_reports():
        reports = service.get_research_reports(code=args.code, limit=args.report_limit)
        if not reports:
            raise ValueError("Research reports returned empty list")
        return f"{len(reports)} reports"

    run_test("Testing Research Reports...", test_reports, results, results["tests"])

    # Summary
    passed = sum(1 for t in results["tests"].values() if t["status"] == "pass")
    total = len(results["tests"])
    print("\n" + "=" * 60)
    print(f"Summary: {passed}/{total} tests passed")

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()