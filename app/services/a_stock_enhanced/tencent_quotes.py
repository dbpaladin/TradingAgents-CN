from __future__ import annotations

import logging
import urllib.request
from typing import Dict, List

from .config import get_a_stock_enhanced_config
from .models import EnhancedQuote
from .utils import market_prefix, normalize_code, safe_float

logger = logging.getLogger(__name__)


class TencentQuotesProvider:
    source_name = "tencent_finance"

    def __init__(self) -> None:
        self.config = get_a_stock_enhanced_config()

    def fetch_quotes(self, codes: List[str]) -> Dict[str, EnhancedQuote]:
        if not self.config.enabled or not self.config.tencent_quotes_enabled:
            return {}

        normalized = [normalize_code(code) for code in codes if code]
        if not normalized:
            return {}

        prefixed = [f"{market_prefix(code)}{code}" for code in normalized]
        url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            raw_text = urllib.request.urlopen(
                req,
                timeout=self.config.request_timeout_seconds,
            ).read().decode("gbk", errors="ignore")
        except Exception as exc:
            logger.warning("Tencent quotes fetch failed: %s", exc)
            return {}

        results: Dict[str, EnhancedQuote] = {}
        for line in raw_text.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            values = line.split('"')[1].split("~")
            if len(values) < 53:
                continue
            code = normalize_code(key)
            amount_wan = safe_float(values[37])
            results[code] = EnhancedQuote(
                code=code,
                name=values[1] or None,
                price=safe_float(values[3]),
                pre_close=safe_float(values[4]),
                open=safe_float(values[5]),
                change_amt=safe_float(values[31]),
                pct_chg=safe_float(values[32]),
                high=safe_float(values[33]),
                low=safe_float(values[34]),
                amount=(amount_wan * 10000) if amount_wan is not None else None,
                turnover_rate=safe_float(values[38]),
                pe_ttm=safe_float(values[39]),
                total_mv=safe_float(values[44]),
                circ_mv=safe_float(values[45]),
                pb=safe_float(values[46]),
                limit_up=safe_float(values[47]),
                limit_down=safe_float(values[48]),
                vol_ratio=safe_float(values[49]),
                pe_static=safe_float(values[52]),
                source=self.source_name,
                raw={
                    "line": line,
                    "amount_wan": amount_wan,
                },
            )
        return results
