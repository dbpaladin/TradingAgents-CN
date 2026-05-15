#!/usr/bin/env bash
set -euo pipefail

HOURS="${A_STOCK_GRAY_CHECK_HOURS:-24}"
FINANCE_MIN="${A_STOCK_GRAY_FINANCE_MIN_RATIO:-90}"
NORTHBOUND_MIN="${A_STOCK_GRAY_NORTHBOUND_MIN_RATIO:-90}"

python scripts/a_stock_gray_stats.py \
  --hours "${HOURS}" \
  --min-finance-tushare-ratio "${FINANCE_MIN}" \
  --min-northbound-tushare-ratio "${NORTHBOUND_MIN}"
