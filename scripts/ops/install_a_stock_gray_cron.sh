#!/usr/bin/env bash
set -euo pipefail

# Install/update cron job for a_stock gray check.
#
# Usage:
#   bash scripts/ops/install_a_stock_gray_cron.sh /abs/path/to/repo
#
# Optional env overrides:
#   CRON_SCHEDULE="*/30 * * * *"
#   CHECK_HOURS=24
#   FINANCE_MIN=90
#   NORTHBOUND_MIN=90

REPO_ROOT="${1:-$(pwd)}"
CRON_SCHEDULE="${CRON_SCHEDULE:-*/30 * * * *}"
CHECK_HOURS="${CHECK_HOURS:-24}"
FINANCE_MIN="${FINANCE_MIN:-90}"
NORTHBOUND_MIN="${NORTHBOUND_MIN:-90}"

if [[ ! -f "${REPO_ROOT}/scripts/check_a_stock_gray.sh" ]]; then
  echo "ERROR: cannot find scripts/check_a_stock_gray.sh under ${REPO_ROOT}" >&2
  exit 1
fi

mkdir -p "${REPO_ROOT}/logs"

JOB="A_STOCK_GRAY_CHECK_HOURS=${CHECK_HOURS} A_STOCK_GRAY_FINANCE_MIN_RATIO=${FINANCE_MIN} A_STOCK_GRAY_NORTHBOUND_MIN_RATIO=${NORTHBOUND_MIN} bash ${REPO_ROOT}/scripts/check_a_stock_gray.sh >> ${REPO_ROOT}/logs/a_stock_gray_cron.log 2>&1"
ENTRY="${CRON_SCHEDULE} ${JOB}"

TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

crontab -l 2>/dev/null | grep -v "scripts/check_a_stock_gray.sh" > "${TMP_FILE}" || true
echo "${ENTRY}" >> "${TMP_FILE}"
crontab "${TMP_FILE}"

echo "Installed cron entry:"
echo "${ENTRY}"
