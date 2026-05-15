"""
A-share enhanced data services.

This package provides a sidecar PoC for A-share-specific data sources such as
Tencent Finance, mootdx and THS northbound flows. It is intentionally isolated
from the main data source manager so we can validate capabilities without
changing the production default data path.
"""

from .service import AStockEnhancedService, get_a_stock_enhanced_service

__all__ = [
    "AStockEnhancedService",
    "get_a_stock_enhanced_service",
]
