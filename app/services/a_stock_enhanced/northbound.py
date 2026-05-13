from __future__ import annotations

import logging
from typing import List

import requests

from .config import get_a_stock_enhanced_config
from .models import NorthboundIntradayPoint
from .utils import now_trade_date, safe_float

logger = logging.getLogger(__name__)


class NorthboundProvider:
    source_name = "ths_hsgt"
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"

    def __init__(self) -> None:
        self.config = get_a_stock_enhanced_config()

    def get_intraday(self) -> List[NorthboundIntradayPoint]:
        if not self.config.enabled or not self.config.northbound_enabled:
            return []
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.10jqka.com.cn/",
        }
        try:
            response = requests.get(
                self.url,
                headers=headers,
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("northbound fetch failed: %s", exc)
            return []

        times = payload.get("time") or []
        hgt = payload.get("hgt") or []
        sgt = payload.get("sgt") or []
        size = min(len(times), len(hgt), len(sgt))
        trade_date = now_trade_date()
        items: List[NorthboundIntradayPoint] = []
        for idx in range(size):
            hgt_value = safe_float(hgt[idx])
            sgt_value = safe_float(sgt[idx])
            total = None
            if hgt_value is not None or sgt_value is not None:
                total = (hgt_value or 0.0) + (sgt_value or 0.0)
            items.append(
                NorthboundIntradayPoint(
                    time=str(times[idx]),
                    hgt_net_buy=hgt_value,
                    sgt_net_buy=sgt_value,
                    northbound_total=total,
                    source=self.source_name,
                    trade_date=trade_date,
                )
            )
        return items
