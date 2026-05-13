"""
A-share enhanced data source debug routes (read-only).

These endpoints are intentionally isolated for PoC validation and should not be
treated as production primary data APIs.
"""

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.a_stock_enhanced import get_a_stock_enhanced_service
from app.services.a_stock_enhanced.models import as_dict_list, ResearchReportItem

router = APIRouter(prefix="/api/debug/a-stock-enhanced", tags=["a-stock-enhanced-debug"])


@router.get("/quote/{code}")
async def get_enhanced_quote(
    code: str,
    current_user: dict = Depends(get_current_user),
):
    service = get_a_stock_enhanced_service()
    quote = service.get_quote_enhanced(code)
    return ok(data=asdict(quote) if quote else None)


@router.get("/kline/{code}")
async def get_enhanced_kline(
    code: str,
    period: str = Query(default="day", description="day/week/month/1m/5m/15m/30m/60m"),
    limit: int = Query(default=120, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    service = get_a_stock_enhanced_service()
    items = service.get_kline_enhanced(code=code, period=period, limit=limit)
    return ok(data=as_dict_list(items))


@router.get("/research-reports/{code}")
async def get_research_reports(
    code: str,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    service = get_a_stock_enhanced_service()
    items = service.get_research_reports(code=code, limit=limit)
    return ok(data=as_dict_list(items))


@router.get("/northbound-intraday")
async def get_northbound_intraday(
    force_refresh: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    service = get_a_stock_enhanced_service()
    items = await service.get_northbound_intraday(force_refresh=force_refresh)
    return ok(data=as_dict_list(items))


@router.get("/announcements/{code}")
async def get_announcements(
    code: str,
    start_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    service = get_a_stock_enhanced_service()
    items = service.get_announcements(
        code=code,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return ok(data=as_dict_list(items))
