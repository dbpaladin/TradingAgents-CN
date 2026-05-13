from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class AStockEnhancedConfig:
    enabled: bool
    tencent_quotes_enabled: bool
    mootdx_enabled: bool
    northbound_enabled: bool
    announcements_enabled: bool
    research_reports_enabled: bool
    quote_ttl_seconds: int
    northbound_ttl_seconds: int
    request_timeout_seconds: int


def get_a_stock_enhanced_config() -> AStockEnhancedConfig:
    settings = get_settings()
    return AStockEnhancedConfig(
        enabled=settings.A_STOCK_DATA_ENABLED,
        tencent_quotes_enabled=settings.A_STOCK_TENCENT_QUOTES_ENABLED,
        mootdx_enabled=settings.A_STOCK_MOOTDX_ENABLED,
        northbound_enabled=settings.A_STOCK_NORTHBOUND_ENABLED,
        announcements_enabled=settings.A_STOCK_ANNOUNCEMENTS_ENABLED,
        research_reports_enabled=getattr(settings, "A_STOCK_RESEARCH_REPORTS_ENABLED", True),
        quote_ttl_seconds=settings.A_STOCK_QUOTE_TTL_SECONDS,
        northbound_ttl_seconds=settings.A_STOCK_NORTHBOUND_TTL_SECONDS,
        request_timeout_seconds=settings.A_STOCK_REQUEST_TIMEOUT_SECONDS,
    )