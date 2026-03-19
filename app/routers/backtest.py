"""
回测 API 路由
提供 A股回测任务的创建、查询、结果获取等接口
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, List, Optional
import logging

from app.routers.auth_db import get_current_user
from app.services.backtest_service import get_backtest_service
from app.models.backtest import BacktestCreateRequest, BacktestStatus

router = APIRouter()
logger = logging.getLogger("webapi")


@router.post("/tasks", response_model=Dict[str, Any])
async def create_backtest_task(
    request: BacktestCreateRequest,
    user: dict = Depends(get_current_user)
):
    """
    提交回测任务
    
    创建一个新的 A股回测任务并在后台异步执行。
    回测将在历史日期上循环调用 AI 分析，模拟 A股交易（含T+1、涨跌停、手续费）。
    
    返回 task_id，可通过 GET /tasks/{task_id} 查询进度。
    """
    try:
        config = request.config
        logger.info(f"🚀 [回测] 收到回测请求: {config.symbol} | {config.start_date} ~ {config.end_date}")
        logger.info(f"👤 [回测] 用户: {user.get('id')}")

        # 基本参数验证
        if not config.symbol or not config.symbol.strip():
            raise HTTPException(status_code=400, detail="股票代码不能为空")
        if not config.start_date or not config.end_date:
            raise HTTPException(status_code=400, detail="开始日期和结束日期不能为空")
        if config.start_date >= config.end_date:
            raise HTTPException(status_code=400, detail="开始日期必须早于结束日期")

        service = get_backtest_service()
        result = await service.create_task(user_id=user["id"], config=config)

        return {
            "success": True,
            "data": result,
            "message": "回测任务已提交，请通过 task_id 查询进度"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 提交回测任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=Dict[str, Any])
async def get_backtest_task_status(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    查询回测任务状态与进度
    
    返回任务当前状态、进度百分比、当前正在分析的日期。
    状态值: pending | running | completed | failed | cancelled
    """
    try:
        service = get_backtest_service()
        status = await service.get_task_status(task_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"回测任务不存在: {task_id}")

        return {
            "success": True,
            "data": status,
            "message": "任务状态获取成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取回测任务状态失败: {task_id} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/result", response_model=Dict[str, Any])
async def get_backtest_task_result(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    获取完整回测结果（仅在任务完成后可用）
    
    返回：
    - metrics: 绩效指标（总收益率、最大回撤、夏普比率、胜率等）
    - trades: 完整交易记录列表
    - daily_equity: 每日净值序列（用于绘制净值曲线）
    """
    try:
        service = get_backtest_service()
        doc = await service.get_task_result(task_id)

        if not doc:
            raise HTTPException(status_code=404, detail=f"回测任务不存在: {task_id}")

        status = doc.get("status")
        if status == BacktestStatus.RUNNING or status == BacktestStatus.PENDING:
            return {
                "success": False,
                "data": {"status": status, "progress": doc.get("progress", 0)},
                "message": f"任务尚未完成，当前状态: {status}"
            }
        if status == BacktestStatus.FAILED:
            return {
                "success": False,
                "data": {"status": status, "error": doc.get("error_message")},
                "message": f"任务执行失败: {doc.get('error_message', '未知错误')}"
            }

        result = doc.get("result")
        if not result:
            raise HTTPException(status_code=404, detail="回测结果数据为空")

        return {
            "success": True,
            "data": result,
            "message": "回测结果获取成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取回测结果失败: {task_id} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", response_model=Dict[str, Any])
async def list_backtest_tasks(
    user: dict = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量"),
    offset: int = Query(default=0, ge=0, description="偏移量")
):
    """
    获取当前用户的回测任务列表
    
    返回按创建时间降序排列的回测任务列表，包含任务状态和核心指标（如已完成）。
    """
    try:
        service = get_backtest_service()
        tasks = await service.list_user_tasks(
            user_id=user["id"],
            limit=limit,
            offset=offset
        )
        return {
            "success": True,
            "data": {
                "tasks": tasks,
                "total": len(tasks),
                "limit": limit,
                "offset": offset
            },
            "message": "任务列表获取成功"
        }
    except Exception as e:
        logger.error(f"❌ 获取回测任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}", response_model=Dict[str, Any])
async def delete_backtest_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """删除回测任务"""
    try:
        service = get_backtest_service()
        deleted = await service.delete_task(task_id=task_id, user_id=user["id"])
        if not deleted:
            raise HTTPException(status_code=404, detail="任务不存在或无权删除")
        return {"success": True, "message": "任务已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 删除回测任务失败: {task_id} - {e}")
        raise HTTPException(status_code=500, detail=str(e))
