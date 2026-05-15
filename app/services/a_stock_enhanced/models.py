from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class EnhancedQuote:
    code: str
    name: Optional[str] = None
    price: Optional[float] = None
    pre_close: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    pct_chg: Optional[float] = None
    change_amt: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None
    pe_ttm: Optional[float] = None
    pe_static: Optional[float] = None
    pb: Optional[float] = None
    total_mv: Optional[float] = None
    circ_mv: Optional[float] = None
    limit_up: Optional[float] = None
    limit_down: Optional[float] = None
    vol_ratio: Optional[float] = None
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnhancedKlineBar:
    code: str
    time: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    period: str = "day"
    adj: Optional[str] = None
    source: str = "unknown"


@dataclass
class FinanceSnapshot:
    code: str
    name: Optional[str] = None
    report_date: Optional[str] = None
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    total_share: Optional[float] = None
    float_share: Optional[float] = None
    bps: Optional[float] = None
    undistributed_profit: Optional[float] = None
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class F10Document:
    code: str
    category: str
    content: str
    title: Optional[str] = None
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NorthboundIntradayPoint:
    time: str
    hgt_net_buy: Optional[float] = None
    sgt_net_buy: Optional[float] = None
    northbound_total: Optional[float] = None
    source: str = "unknown"
    trade_date: Optional[str] = None


@dataclass
class AnnouncementItem:
    code: str
    title: str
    publish_time: Optional[str] = None
    url: Optional[str] = None
    announcement_type: Optional[str] = None
    source: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchReportItem:
    code: str
    title: str
    org: str = ""
    publish_date: str = ""
    rating: str = ""
    last_rating: str = ""
    rating_change: str = ""
    eps_forecast_1y: Optional[float] = None
    eps_forecast_2y: Optional[float] = None
    eps_forecast_3y: Optional[float] = None
    source: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)


def as_dict_list(items: List[Any]) -> List[Dict[str, Any]]:
    return [item.__dict__ for item in items]