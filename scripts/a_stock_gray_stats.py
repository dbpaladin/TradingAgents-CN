#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional


FINANCE_TAG = "[a_stock_enhanced][finance]"
NORTHBOUND_TAG = "[a_stock_enhanced][northbound]"

FINANCE_SELECTED_RE = re.compile(r"selected=([^\s]+)")
NORTHBOUND_SELECTED_RE = re.compile(r"selected=([^\s]+)")
TS_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _parse_ts(line: str) -> Optional[datetime]:
    m = TS_PREFIX_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _iter_log_files(patterns: Iterable[str]) -> Iterable[Path]:
    seen = set()
    for pattern in patterns:
        for p in glob.glob(pattern):
            path = Path(p)
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _count_selected(
    paths: Iterable[Path],
    tag: str,
    selected_re: re.Pattern[str],
    since: Optional[datetime],
) -> Counter:
    c = Counter()
    for path in paths:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if tag not in line:
                        continue
                    if since is not None:
                        ts = _parse_ts(line)
                        if ts is not None and ts < since:
                            continue
                    m = selected_re.search(line)
                    if not m:
                        c["unknown"] += 1
                    else:
                        c[m.group(1)] += 1
        except OSError:
            continue
    return c


def _print_block(name: str, c: Counter) -> None:
    total = sum(c.values())
    print(f"\n{name}: total={total}")
    if total == 0:
        print("  no records")
        return
    for k, v in sorted(c.items(), key=lambda kv: kv[1], reverse=True):
        ratio = v * 100.0 / total
        print(f"  {k:28s} {v:8d}  {ratio:6.2f}%")


def _ratio(counter: Counter, keyword: str) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    hit = sum(v for k, v in counter.items() if keyword in k)
    return hit * 100.0 / total


def main() -> None:
    parser = argparse.ArgumentParser(description="A-share enhanced gray release stats from logs")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="only count logs in recent N hours; <=0 means all logs",
    )
    parser.add_argument(
        "--log",
        action="append",
        default=[],
        help="log file path or glob; can pass multiple times",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print JSON output for automation",
    )
    parser.add_argument(
        "--min-finance-tushare-ratio",
        type=float,
        default=None,
        help="exit 2 when finance tushare ratio is below this threshold (0-100)",
    )
    parser.add_argument(
        "--min-northbound-tushare-ratio",
        type=float,
        default=None,
        help="exit 3 when northbound tushare ratio is below this threshold (0-100)",
    )
    args = parser.parse_args()

    patterns = args.log or ["logs/**/*.log", "logs/*.log"]
    paths = list(_iter_log_files(patterns))
    since = None
    if args.hours > 0:
        since = datetime.now() - timedelta(hours=args.hours)

    finance = _count_selected(paths, FINANCE_TAG, FINANCE_SELECTED_RE, since)
    northbound = _count_selected(paths, NORTHBOUND_TAG, NORTHBOUND_SELECTED_RE, since)
    finance_tushare_ratio = _ratio(finance, "tushare")
    northbound_tushare_ratio = _ratio(northbound, "tushare")

    summary: Dict[str, int] = {
        "finance_total": sum(finance.values()),
        "northbound_total": sum(northbound.values()),
        "finance_tushare": sum(v for k, v in finance.items() if "tushare" in k),
        "northbound_tushare": sum(v for k, v in northbound.items() if "tushare" in k),
    }
    payload = {
        "log_files": len(paths),
        "window_hours": args.hours if args.hours > 0 else "all",
        "finance": {
            "counts": dict(finance),
            "tushare_ratio": round(finance_tushare_ratio, 4),
        },
        "northbound": {
            "counts": dict(northbound),
            "tushare_ratio": round(northbound_tushare_ratio, 4),
        },
        "summary": summary,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("A-Stock Enhanced Gray Stats")
        print(f"log_files={len(paths)}")
        print(f"window_hours={args.hours if args.hours > 0 else 'all'}")
        _print_block("finance", finance)
        _print_block("northbound", northbound)
        print("\nsummary:")
        for k, v in summary.items():
            print(f"  {k}={v}")
        print(f"  finance_tushare_ratio={finance_tushare_ratio:.2f}%")
        print(f"  northbound_tushare_ratio={northbound_tushare_ratio:.2f}%")

    if args.min_finance_tushare_ratio is not None and finance_tushare_ratio < args.min_finance_tushare_ratio:
        raise SystemExit(2)
    if args.min_northbound_tushare_ratio is not None and northbound_tushare_ratio < args.min_northbound_tushare_ratio:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
