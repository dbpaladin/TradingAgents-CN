from __future__ import annotations

from datetime import datetime
from typing import Optional


def normalize_code(code: str) -> str:
    digits = "".join(ch for ch in str(code).strip() if ch.isdigit())
    return digits.zfill(6) if digits else str(code).strip()


def market_prefix(code: str) -> str:
    code6 = normalize_code(code)
    if code6.startswith(("6", "9")):
        return "sh"
    if code6.startswith("8"):
        return "bj"
    return "sz"


def safe_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip().replace(",", "").replace("%", "")
            if text in {"", "-", "None", "nan"}:
                return None
            return float(text)
        return float(value)
    except Exception:
        return None


def coalesce(*values):
    for value in values:
        if value is not None:
            return value
    return None


def now_trade_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")
