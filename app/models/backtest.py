"""
回测相关数据模型
A股回测功能的 Pydantic 数据模型定义
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from bson import ObjectId
from app.models.user import PyObjectId
from app.utils.timezone import now_tz


class BacktestStatus(str, Enum):
    """回测任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TradeAction(str, Enum):
    """交易动作枚举"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PositionStrategy(str, Enum):
    """仓位策略枚举"""
    FULL = "full"           # 全仓操作
    HALF = "half"           # 半仓操作
    FIXED_RATIO = "fixed"   # 固定比例


class BacktestConfig(BaseModel):
    """回测配置模型"""
    # 标的信息
    symbol: str = Field(..., description="A股股票代码, 如 000001 或 000001.SZ")
    stock_name: Optional[str] = Field(None, description="股票名称（可选，系统自动填充）")

    # 时间范围
    start_date: str = Field(..., description="回测开始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., description="回测结束日期 (YYYY-MM-DD)")

    # 资金配置
    initial_capital: float = Field(default=100000.0, ge=10000.0, description="初始资金（元），最低1万元")
    position_ratio: float = Field(default=1.0, ge=0.1, le=1.0, description="每次买入使用的资金比例(0.1-1.0)")
    position_strategy: PositionStrategy = Field(default=PositionStrategy.FULL, description="仓位策略")

    # A股交易费用配置
    commission_rate: float = Field(default=0.0003, ge=0.0, le=0.01, description="佣金费率，默认0.03%")
    stamp_duty_rate: float = Field(default=0.001, ge=0.0, le=0.01, description="印花税（卖出时）, 默认0.1%")
    min_commission: float = Field(default=5.0, ge=0.0, description="最低佣金（元），默认5元")

    # AI 分析配置
    selected_analysts: List[str] = Field(
        default_factory=lambda: ["market", "fundamentals"],
        description="使用的分析师列表，建议为加速回测只用 market+fundamentals"
    )
    research_depth: str = Field(default="快速", description="分析深度，建议用'快速'以控制成本")
    quick_analysis_model: Optional[str] = Field(None, description="快速分析模型")
    deep_analysis_model: Optional[str] = Field(None, description="深度分析模型")
    decision_interval_days: int = Field(
        default=1,
        ge=1,
        le=20,
        description="每隔多少个交易日重新运行一次 AI；1 表示逐日分析，>1 表示中间交易日复用上次信号"
    )

    # 描述
    name: str = Field(default="", description="回测名称")
    description: Optional[str] = Field(None, description="回测描述")


class TradeRecord(BaseModel):
    """单笔交易记录"""
    date: str = Field(..., description="交易日期 (YYYY-MM-DD)")
    action: TradeAction = Field(..., description="买入/卖出/持有")
    price: float = Field(..., description="成交价格（收盘价）")
    shares: int = Field(default=0, description="交易股数(手数×100)")
    amount: float = Field(default=0.0, description="交易金额（元）")
    commission: float = Field(default=0.0, description="手续费（元）")
    stamp_duty: float = Field(default=0.0, description="印花税（元）")
    total_cost: float = Field(default=0.0, description="总费用（元）")

    # 交易后账户状态
    cash: float = Field(..., description="交易后现金余额（元）")
    position_shares: int = Field(..., description="交易后持仓股数")
    position_value: float = Field(..., description="交易后持仓市值（元）")
    total_assets: float = Field(..., description="交易后总资产（元）")

    # AI 决策信息
    ai_signal: str = Field(default="", description="AI原始信号")
    ai_confidence: float = Field(default=0.0, description="AI置信度")
    ai_reason: str = Field(default="", description="AI决策原因摘要")
    ai_provider: Optional[str] = Field(default=None, description="本次决策使用的模型供应商")
    ai_model: Optional[str] = Field(default=None, description="本次决策使用的模型名称（可能为quick/deep组合）")
    ai_runtime_mode: Optional[str] = Field(default=None, description="决策运行模式：primary/degraded/rule/reuse等")
    analysis_elapsed_ms: Optional[float] = Field(default=None, description="AI推理耗时（毫秒）")
    decision_elapsed_ms: Optional[float] = Field(default=None, description="信号解析与纠偏耗时（毫秒）")
    execution_elapsed_ms: Optional[float] = Field(default=None, description="交易执行耗时（毫秒）")
    day_elapsed_ms: Optional[float] = Field(default=None, description="当日完整处理耗时（毫秒）")

    # A股特殊情况标记
    t1_restriction: bool = Field(default=False, description="是否受T+1限制影响")
    limit_up: bool = Field(default=False, description="是否处于涨停板（无法买入）")
    limit_down: bool = Field(default=False, description="是否处于跌停板（无法卖出）")
    executed: bool = Field(default=True, description="是否实际执行（因涨跌停等可能未执行）")


class DailyEquity(BaseModel):
    """每日净值记录"""
    date: str = Field(..., description="日期 (YYYY-MM-DD)")
    total_assets: float = Field(..., description="总资产")
    cash: float = Field(..., description="现金")
    position_value: float = Field(..., description="持仓市值")
    equity_ratio: float = Field(..., description="净值比（相对初始资金）")
    benchmark_ratio: float = Field(default=1.0, description="基准指数净值比（上证指数）")
    drawdown: float = Field(default=0.0, description="当日回撤")


class BacktestMetrics(BaseModel):
    """回测绩效指标"""
    # 收益指标
    total_return: float = Field(..., description="总收益率 (%)")
    annual_return: float = Field(..., description="年化收益率 (%)")
    benchmark_return: float = Field(default=0.0, description="基准（上证指数）收益率 (%)")
    excess_return: float = Field(default=0.0, description="超额收益率 (%)")

    # 风险指标
    max_drawdown: float = Field(..., description="最大回撤 (%)")
    sharpe_ratio: float = Field(..., description="夏普比率（无风险利率3%）")
    volatility: float = Field(..., description="年化波动率 (%)")

    # 交易统计
    total_trades: int = Field(..., description="总交易次数（买+卖）")
    buy_trades: int = Field(default=0, description="买入次数")
    sell_trades: int = Field(default=0, description="卖出次数")
    win_trades: int = Field(default=0, description="盈利交易次数")
    lose_trades: int = Field(default=0, description="亏损交易次数")
    win_rate: float = Field(default=0.0, description="胜率 (%)")
    avg_holding_days: float = Field(default=0.0, description="平均持仓天数")

    # 费用统计
    total_commission: float = Field(default=0.0, description="总手续费（元）")
    total_stamp_duty: float = Field(default=0.0, description="总印花税（元）")
    total_fees: float = Field(default=0.0, description="总费用（元）")

    # 最终账户状态
    final_assets: float = Field(..., description="最终总资产（元）")
    initial_capital: float = Field(..., description="初始资金（元）")
    profit_loss: float = Field(..., description="盈亏金额（元）")

    # 回测元数据
    trading_days: int = Field(default=0, description="实际回测交易日数量")
    start_date: str = Field(default="", description="开始日期")
    end_date: str = Field(default="", description="结束日期")


class BacktestResult(BaseModel):
    """完整回测结果"""
    task_id: str = Field(..., description="回测任务ID")
    symbol: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")

    metrics: BacktestMetrics = Field(..., description="绩效指标")
    trades: List[TradeRecord] = Field(default_factory=list, description="交易记录列表")
    daily_equity: List[DailyEquity] = Field(default_factory=list, description="每日净值序列")

    created_at: datetime = Field(default_factory=now_tz, description="创建时间")


class BacktestTask(BaseModel):
    """回测任务模型（存储到 MongoDB）"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    task_id: str = Field(..., description="任务唯一标识")
    user_id: PyObjectId = Field(..., description="所属用户ID")

    status: BacktestStatus = Field(default=BacktestStatus.PENDING, description="任务状态")
    progress: int = Field(default=0, ge=0, le=100, description="进度 0-100")
    current_date: Optional[str] = Field(None, description="当前正在分析的日期")
    current_step: Optional[str] = Field(None, description="当前步骤说明")

    config: BacktestConfig = Field(..., description="回测配置")
    result: Optional[BacktestResult] = Field(None, description="回测结果")

    error_message: Optional[str] = Field(None, description="错误信息")

    created_at: datetime = Field(default_factory=now_tz)
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )


# ======= API 请求/响应模型 =======

class BacktestCreateRequest(BaseModel):
    """创建回测任务请求"""
    config: BacktestConfig


class BacktestTaskResponse(BaseModel):
    """回测任务响应（简化）"""
    task_id: str
    status: BacktestStatus
    progress: int
    current_date: Optional[str] = None
    current_step: Optional[str] = None
    symbol: str
    start_date: str
    end_date: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
