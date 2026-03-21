"""
A股回测引擎服务
核心逻辑：在历史日期序列上循环执行 AI 分析，模拟 A股交易，计算绩效指标

A股特殊限制：
- T+1 交易制度：当日买入，次日才能卖出
- 涨跌停限制：±10%（ST股±5%）涨停不能买，跌停不能卖
- 交易费用：手续费 + 印花税（卖出方向）
"""

import asyncio
import uuid
import logging
import math
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.models.backtest import (
    BacktestConfig, BacktestTask, BacktestResult, BacktestMetrics,
    TradeRecord, DailyEquity, BacktestStatus, TradeAction
)
from app.models.user import PyObjectId
from bson import ObjectId
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


def _normalize_symbol(symbol: str) -> str:
    """标准化A股代码：去掉市场后缀，保留6位纯数字"""
    symbol = symbol.strip().upper()
    for suffix in [".SZ", ".SH", ".BJ"]:
        if symbol.endswith(suffix):
            symbol = symbol[:-3]
    return symbol


def _get_market_suffix(symbol: str) -> str:
    """根据股票代码推断所属市场"""
    code = _normalize_symbol(symbol)
    if code.startswith("6"):
        return "SH"   # 上海主板
    elif code.startswith(("0", "3")):
        return "SZ"   # 深圳
    elif code.startswith("8") or code.startswith("4"):
        return "BJ"   # 北交所
    return "SH"


class BacktestEngine:
    """A股回测引擎"""

    # A股无风险利率（使用3%年化，参考中国短期国债）
    RISK_FREE_RATE = 0.03
    # 基准指数：上证综指
    BENCHMARK_CODE = "000001"

    def __init__(self, task: BacktestTask, progress_callback=None):
        self.task = task
        self.config = task.config
        self.progress_callback = progress_callback
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"backtest-{task.task_id[:8]}"
        )
        self._analysis_runtime: Optional[Dict[str, Any]] = None
        self._reusable_trading_graph = None
        self._stock_price_cache: Dict[str, float] = {}
        self._benchmark_price_cache: Dict[str, float] = {}

        # 账户状态
        self.cash = self.config.initial_capital
        self.position_shares = 0
        self.buy_date: Optional[str] = None  # T+1：记录买入日期
        self.avg_buy_price = 0.0  # 平均持仓成本

        # 记录
        self.trades: List[TradeRecord] = []
        self.daily_equity: List[DailyEquity] = []
        self.benchmark_prices: List[float] = []

        # 统计
        self.peak_assets = self.config.initial_capital
        self.max_drawdown_pct = 0.0
        self.completed_trades: List[Dict] = []  # 已完成的完整买-卖周期

    async def close(self):
        """释放回测过程中持有的资源"""
        self._executor.shutdown(wait=False, cancel_futures=False)

    async def _update_progress(self, progress: int, current_date: str, message: str):
        """更新进度"""
        db = get_mongo_db()
        await db.backtest_tasks.update_one(
            {"task_id": self.task.task_id},
            {"$set": {
                "progress": progress,
                "current_date": current_date,
                "current_step": message,
                "status": BacktestStatus.RUNNING
            }}
        )
        if self.progress_callback:
            self.progress_callback(progress, current_date, message)

    def _calc_commission(self, amount: float, is_buy: bool) -> Tuple[float, float]:
        """
        计算 A股交易费用
        Returns: (commission, stamp_duty)
        """
        commission = max(
            amount * self.config.commission_rate,
            self.config.min_commission
        )
        stamp_duty = 0.0
        if not is_buy:
            # 印花税仅在卖出时收取
            stamp_duty = amount * self.config.stamp_duty_rate
        return commission, stamp_duty

    def _calculate_buy_shares(self, price: float) -> int:
        """计算可买入股数（按手 100 股计算）"""
        available_cash = self.cash * self.config.position_ratio
        # 考虑佣金后能买的最大股数，直接用总资金除以单股成本（含手续费）
        shares = int(available_cash / (price * (1 + self.config.commission_rate)) / 100) * 100
        return max(0, shares)

    def _parse_ai_decision(self, decision: Dict) -> Tuple[TradeAction, float, str]:
        """
        解析 AI 决策，返回 (action, confidence, reason)
        支持多种 decision 格式
        """
        if not decision:
            return TradeAction.HOLD, 0.0, "无AI决策"

        # 尝试读取 action 字段
        action_str = (
            decision.get("action") or
            decision.get("recommendation") or
            decision.get("signal") or
            ""
        ).upper().strip()

        confidence = float(decision.get("confidence_score") or decision.get("confidence") or 0.0)
        reason = (
            decision.get("summary") or
            decision.get("reason") or
            decision.get("reasoning") or  # signal_processing 返回的是 reasoning
            (decision.get("key_points", [""])[0] if isinstance(decision.get("key_points"), list) and decision.get("key_points") else "")
        )
        reason = str(reason)[:200]  # 截断

        # 解析动作
        if any(kw in action_str for kw in ["BUY", "买入", "强烈买入", "STRONG_BUY"]):
            return TradeAction.BUY, confidence, reason
        elif any(kw in action_str for kw in ["SELL", "卖出", "强烈卖出", "STRONG_SELL"]):
            return TradeAction.SELL, confidence, reason
        else:
            return TradeAction.HOLD, confidence, reason or "无明确AI信号"

    async def _get_trading_calendar(self, start_date: str, end_date: str) -> List[str]:
        """
        获取 A股交易日历（优先使用 Tushare，备选 AkShare）
        """
        # 1. 尝试使用 Tushare (支持第三方代理源)
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            import pandas as pd
            ts_provider = get_tushare_provider()
            if ts_provider and ts_provider.is_available():
                logger.info("🔍 使用 Tushare 获取交易日历...")
                start_str = start_date.replace("-", "")
                end_str = end_date.replace("-", "")
                
                # 调用 Tushare pro.trade_cal
                df = await asyncio.to_thread(
                    ts_provider.api.trade_cal,
                    exchange="SSE",
                    start_date=start_str,
                    end_date=end_str,
                    is_open="1"
                )
                if df is not None and not df.empty:
                    trading_days = pd.to_datetime(df["cal_date"]).dt.strftime("%Y-%m-%d").tolist()
                    logger.info(f"✅ Tushare 获取交易日历成功: {len(trading_days)} 天")
                    return sorted(trading_days)
        except Exception as e:
            logger.warning(f"⚠️ Tushare 获取交易日历失败: {e}，尝试备用方案")

        # 2. 备选方案：使用 AkShare
        try:
            import akshare as ak
            import pandas as pd

            # 获取上证指数历史数据，通过这个获取真实交易日列表
            df = ak.stock_zh_index_daily(symbol="sh000001")
            df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            mask = (df["date_str"] >= start_date) & (df["date_str"] <= end_date)
            trading_days = df.loc[mask, "date_str"].tolist()
            logger.info(f"✅ AkShare 获取交易日历成功: {start_date} ~ {end_date}，共 {len(trading_days)} 个交易日")
            return sorted(trading_days)
        except Exception as e:
            logger.warning(f"⚠️ AkShare 获取交易日历失败: {e}，尝试兜底方案")
            # 备用方案：简单工作日
            result = []
            cur = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            while cur <= end_dt:
                if cur.weekday() < 5:
                    result.append(cur.strftime("%Y-%m-%d"))
                cur += timedelta(days=1)
            return result

    async def _get_stock_price(self, symbol: str, date_str: str) -> Optional[float]:
        """获取股票在指定日期的收盘价 (优先使用 Tushare)"""
        cached_price = self._stock_price_cache.get(date_str)
        if cached_price is not None:
            return cached_price

        # 1. 尝试使用 Tushare
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            ts_provider = get_tushare_provider()
            if ts_provider and ts_provider.is_available():
                df = await ts_provider.get_historical_data(symbol, start_date=date_str, end_date=date_str)
                if df is not None and not df.empty:
                    price = float(df.iloc[0]["close"])
                    self._stock_price_cache[date_str] = price
                    return price
        except Exception as e:
            logger.debug(f"⚠️ Tushare 获取 {symbol} {date_str} 价格失败: {e}")

        # 2. 备选方案：使用 AkShare
        try:
            import akshare as ak
            code = _normalize_symbol(symbol)
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            start = (dt - timedelta(days=5)).strftime("%Y%m%d")
            end = (dt + timedelta(days=1)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
            if df is not None and not df.empty:
                import pandas as pd
                df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
                row = df[df["日期"] == date_str]
                if not row.empty:
                    price = float(row.iloc[0]["收盘"])
                    self._stock_price_cache[date_str] = price
                    return price
        except Exception as e:
            logger.warning(f"⚠️ AkShare 获取 {symbol} {date_str} 收盘价失败: {e}")
        return None

    async def _get_limit_prices(self, symbol: str, date_str: str) -> Tuple[Optional[float], Optional[float]]:
        """
        获取涨跌停价格
        简化版：基于前日收盘价 ±10%/5%
        """
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            ts_provider = get_tushare_provider()
            
            prev_close = None
            if ts_provider and ts_provider.is_available():
                start = (dt - timedelta(days=10)).strftime("%Y-%m-%d")
                end = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
                df = await ts_provider.get_historical_data(symbol, start_date=start, end_date=end)
                if df is not None and not df.empty:
                    prev_close = float(df.iloc[-1]["close"])
            
            if prev_close is None:
                import akshare as ak
                code = _normalize_symbol(symbol)
                start = (dt - timedelta(days=10)).strftime("%Y%m%d")
                end = (dt - timedelta(days=1)).strftime("%Y%m%d")
                df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
                if df is not None and not df.empty:
                    prev_close = float(df.iloc[-1]["收盘"])
            
            if prev_close is None:
                return None, None

            limit_rate = 0.1
            stock_name = self.config.stock_name or ""
            if "ST" in stock_name.upper():
                limit_rate = 0.05
            limit_up = round(prev_close * (1 + limit_rate), 2)
            limit_down = round(prev_close * (1 - limit_rate), 2)
            return limit_up, limit_down
        except Exception as e:
            logger.warning(f"⚠️ 获取 {symbol} {date_str} 涨跌停价失败: {e}")
            return None, None

    async def _get_benchmark_price(self, date_str: str) -> Optional[float]:
        """获取基准指数（上证综指）收盘价"""
        cached_price = self._benchmark_price_cache.get(date_str)
        if cached_price is not None:
            return cached_price

        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            ts_provider = get_tushare_provider()
            if ts_provider and ts_provider.is_available():
                df = await asyncio.to_thread(
                    ts_provider.api.index_daily,
                    ts_code="000001.SH",
                    start_date=date_str.replace("-", ""),
                    end_date=date_str.replace("-", "")
                )
                if df is not None and not df.empty:
                    price = float(df.iloc[0]["close"])
                    self._benchmark_price_cache[date_str] = price
                    return price
        except Exception as e:
            logger.debug(f"⚠️ Tushare 获取基准 {date_str} 价格失败: {e}")

        try:
            import akshare as ak
            import pandas as pd
            df = ak.stock_zh_index_daily(symbol="sh000001")
            df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            row = df[df["date_str"] == date_str]
            if not row.empty:
                price = float(row.iloc[0]["close"])
                self._benchmark_price_cache[date_str] = price
                return price
        except Exception as e:
            logger.warning(f"⚠️ AkShare 获取基准 {date_str} 价格失败: {e}")
        return None

    async def _prefetch_stock_prices(self, symbol: str, start_date: str, end_date: str) -> Dict[str, float]:
        """批量预取个股收盘价，避免逐日远程请求"""
        # 1. 尝试使用 Tushare 一次性获取整段区间
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            ts_provider = get_tushare_provider()
            if ts_provider and ts_provider.is_available():
                df = await ts_provider.get_historical_data(symbol, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    series = {
                        idx.strftime("%Y-%m-%d"): float(row["close"])
                        for idx, row in df.iterrows()
                        if row.get("close") is not None
                    }
                    if series:
                        logger.info(f"✅ 批量预取个股价格成功: {symbol} {len(series)} 天")
                        return series
        except Exception as e:
            logger.warning(f"⚠️ 批量预取个股价格失败(Tushare): {e}")

        # 2. 备选方案：AkShare 整段拉取
        try:
            import akshare as ak
            import pandas as pd

            code = _normalize_symbol(symbol)
            df = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
                series = {
                    str(row["日期"]): float(row["收盘"])
                    for _, row in df.iterrows()
                }
                if series:
                    logger.info(f"✅ 批量预取个股价格成功(AkShare): {symbol} {len(series)} 天")
                    return series
        except Exception as e:
            logger.warning(f"⚠️ 批量预取个股价格失败(AkShare): {e}")

        return {}

    async def _prefetch_benchmark_prices(self, start_date: str, end_date: str) -> Dict[str, float]:
        """批量预取基准指数价格，避免逐日远程请求"""
        # 1. Tushare 区间拉取
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            import pandas as pd

            ts_provider = get_tushare_provider()
            if ts_provider and ts_provider.is_available():
                df = await asyncio.to_thread(
                    ts_provider.api.index_daily,
                    ts_code="000001.SH",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", "")
                )
                if df is not None and not df.empty:
                    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
                    series = {
                        str(row["trade_date"]): float(row["close"])
                        for _, row in df.iterrows()
                    }
                    if series:
                        logger.info(f"✅ 批量预取基准价格成功: {len(series)} 天")
                        return series
        except Exception as e:
            logger.warning(f"⚠️ 批量预取基准价格失败(Tushare): {e}")

        # 2. AkShare 区间裁剪
        try:
            import akshare as ak
            import pandas as pd

            df = await asyncio.to_thread(ak.stock_zh_index_daily, symbol="sh000001")
            if df is not None and not df.empty:
                df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                filtered = df[(df["date_str"] >= start_date) & (df["date_str"] <= end_date)]
                series = {
                    str(row["date_str"]): float(row["close"])
                    for _, row in filtered.iterrows()
                }
                if series:
                    logger.info(f"✅ 批量预取基准价格成功(AkShare): {len(series)} 天")
                    return series
        except Exception as e:
            logger.warning(f"⚠️ 批量预取基准价格失败(AkShare): {e}")

        return {}

    async def _warmup_market_data(self, trading_days: List[str]):
        """提前拉取整段行情，减少回测主循环中的逐日 I/O"""
        if not trading_days:
            return

        stock_prices, benchmark_prices = await asyncio.gather(
            self._prefetch_stock_prices(self.config.symbol, trading_days[0], trading_days[-1]),
            self._prefetch_benchmark_prices(trading_days[0], trading_days[-1]),
        )
        self._stock_price_cache.update(stock_prices)
        self._benchmark_price_cache.update(benchmark_prices)

    def _get_analysis_runtime(self) -> Dict[str, Any]:
        """构建并缓存回测期间复用的分析运行时配置"""
        if self._analysis_runtime is not None:
            return self._analysis_runtime

        from app.core.unified_config import unified_config
        from app.services.simple_analysis_service import (
            create_analysis_config,
            get_provider_and_url_by_model_sync,
        )

        quick_model = self.config.quick_analysis_model or unified_config.get_quick_analysis_model()
        deep_model = self.config.deep_analysis_model or unified_config.get_deep_analysis_model()

        quick_model_config = None
        deep_model_config = None
        for llm_config in unified_config.get_llm_configs():
            if llm_config.model_name == quick_model:
                quick_model_config = {
                    "max_tokens": llm_config.max_tokens,
                    "temperature": llm_config.temperature,
                    "timeout": llm_config.timeout,
                    "retry_times": llm_config.retry_times,
                    "api_base": llm_config.api_base,
                }
            if llm_config.model_name == deep_model:
                deep_model_config = {
                    "max_tokens": llm_config.max_tokens,
                    "temperature": llm_config.temperature,
                    "timeout": llm_config.timeout,
                    "retry_times": llm_config.retry_times,
                    "api_base": llm_config.api_base,
                }

        quick_provider_info = get_provider_and_url_by_model_sync(quick_model)
        deep_provider_info = get_provider_and_url_by_model_sync(deep_model)
        quick_provider = quick_provider_info["provider"]
        deep_provider = deep_provider_info["provider"]

        config = create_analysis_config(
            research_depth=self.config.research_depth,
            selected_analysts=self.config.selected_analysts,
            quick_model=quick_model,
            deep_model=deep_model,
            llm_provider=quick_provider,
            market_type="A股",
            quick_model_config=quick_model_config,
            deep_model_config=deep_model_config,
        )
        config["quick_provider"] = quick_provider
        config["deep_provider"] = deep_provider
        config["quick_backend_url"] = quick_provider_info["backend_url"]
        config["deep_backend_url"] = deep_provider_info["backend_url"]
        config["backend_url"] = quick_provider_info["backend_url"]

        self._analysis_runtime = {
            "quick_model": quick_model,
            "deep_model": deep_model,
            "quick_provider": quick_provider,
            "deep_provider": deep_provider,
            "config": config,
            # 仅在禁用记忆时复用图实例，避免跨日状态污染。
            "reuse_graph": not config.get("memory_enabled", True),
        }

        logger.info(
            "🔍 [回测模型路由] quick=%s(%s), deep=%s(%s), reuse_graph=%s",
            quick_model,
            quick_provider,
            deep_model,
            deep_provider,
            self._analysis_runtime["reuse_graph"],
        )
        return self._analysis_runtime

    def _get_trading_graph(self):
        """获取可复用或按需创建的 TradingAgentsGraph 实例"""
        runtime = self._get_analysis_runtime()
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        if runtime["reuse_graph"]:
            if self._reusable_trading_graph is None:
                self._reusable_trading_graph = TradingAgentsGraph(
                    selected_analysts=self.config.selected_analysts,
                    debug=False,
                    config=runtime["config"]
                )
            return self._reusable_trading_graph

        return TradingAgentsGraph(
            selected_analysts=self.config.selected_analysts,
            debug=False,
            config=runtime["config"]
        )

    async def _run_ai_analysis(self, symbol: str, date_str: str) -> Dict:
        """调用 TradingAgentsGraph 执行 AI 分析"""
        try:
            trading_graph = self._get_trading_graph()

            # 在线程池中执行同步分析，避免每个交易日重复创建线程池。
            loop = asyncio.get_running_loop()
            result_tuple = await loop.run_in_executor(
                self._executor,
                trading_graph.propagate,
                _normalize_symbol(symbol),
                date_str
            )

            # propagate 返回 (final_state, decision) 元组
            if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
                _, decision = result_tuple
            else:
                decision = result_tuple

            if isinstance(decision, dict) and decision:
                logger.info(f"✅ AI分析完成 [{symbol} {date_str}]: action={decision.get('action')}, confidence={decision.get('confidence')}")
                return decision
            else:
                logger.warning(f"⚠️ AI分析返回空决策 [{symbol} {date_str}]: {decision}")
                return {}
        except Exception as e:
            import traceback
            error_msg = f"{type(e).__name__}: {str(e)[:100]}"
            logger.error(f"❌ AI分析失败 [{symbol} {date_str}]:\n{traceback.format_exc()}")
            return {"action": "HOLD", "confidence": 0.0, "reasoning": f"AI引擎内部报错: {error_msg}"}

    async def run(self) -> BacktestResult:
        """
        执行完整回测
        Returns: BacktestResult
        """
        logger.info(f"🚀 开始回测: {self.task.task_id} | {self.config.symbol} | {self.config.start_date} ~ {self.config.end_date}")

        # 1. 获取交易日历
        await self._update_progress(2, self.config.start_date, "📅 获取交易日历...")
        trading_days = await self._get_trading_calendar(self.config.start_date, self.config.end_date)
        if not trading_days:
            raise ValueError(f"没有找到 {self.config.start_date} ~ {self.config.end_date} 的交易日历")

        total_days = len(trading_days)
        logger.info(f"📅 共 {total_days} 个交易日")

        # 1b. 批量预热整段行情，减少逐日 I/O 往返
        await self._update_progress(4, trading_days[0], "📦 预加载历史行情...")
        await self._warmup_market_data(trading_days)

        # 2. 获取基准起始价格（用于计算基准收益率）
        benchmark_start_price: Optional[float] = None
        try:
            benchmark_start_price = await self._get_benchmark_price(trading_days[0])
        except Exception:
            pass

        # 3. 逐日循环
        diagnostic_stats = {
            "days_total": total_days,
            "days_price_none": 0,
            "ai_buy": 0, "ai_sell": 0, "ai_hold": 0,
            "exec_buy": 0, "exec_sell": 0, "exec_abort_buy": 0, "exec_abort_sell": 0,
            "hold_reasons": []
        }
        decision_interval_days = max(1, int(self.config.decision_interval_days or 1))
        last_decision: Dict[str, Any] = {}
        last_decision_action = TradeAction.HOLD
        last_decision_confidence = 0.0
        last_decision_reason = "暂无AI信号"
        last_analysis_idx = -decision_interval_days

        for idx, date_str in enumerate(trading_days):
            progress = int(5 + (idx / total_days) * 90)
            should_run_ai = (
                not last_decision or
                idx == 0 or
                (idx - last_analysis_idx) >= decision_interval_days
            )
            step_prefix = "🔍 分析" if should_run_ai else "♻️ 复用信号"
            await self._update_progress(progress, date_str, f"{step_prefix} {date_str} ({idx+1}/{total_days})...")

            # 3a. 获取当日收盘价
            price = await self._get_stock_price(self.config.symbol, date_str)
            if price is None or price <= 0:
                logger.warning(f"⚠️ {date_str}: 无法获取价格，跳过")
                diagnostic_stats["days_price_none"] += 1
                # 记录持仓不变的净值
                await self._record_daily_equity(date_str, price or 0.0, benchmark_start_price)
                continue

            # 3b. 获取涨跌停价格（简化：不调用API，避免速率限制）
            limit_up, limit_down = None, None

            # 3c. 执行 AI 分析
            if should_run_ai:
                decision = await self._run_ai_analysis(self.config.symbol, date_str)
                action, confidence, reason = self._parse_ai_decision(decision)
                last_decision = decision or {}
                last_decision_action = action
                last_decision_confidence = confidence
                last_decision_reason = reason
                last_analysis_idx = idx
            else:
                decision = last_decision
                action = last_decision_action
                confidence = last_decision_confidence
                reason = f"[复用前次信号] {last_decision_reason}"

            # 3d. T+1 限制检查
            t1_restricted = False
            if action == TradeAction.SELL and self.position_shares > 0:
                if self.buy_date and self.buy_date == date_str:
                    logger.info(f"  ⚠️ {date_str}: T+1限制，当日买入不可卖出")
                    action = TradeAction.HOLD
                    t1_restricted = True

            # 3e. 执行交易
            trade = await self._execute_trade(date_str, price, action, confidence, reason, t1_restricted, limit_up, limit_down)
            
            # 记录诊断统计
            if action == TradeAction.BUY:
                diagnostic_stats["ai_buy"] += 1
                if trade.executed: diagnostic_stats["exec_buy"] += 1
                else: diagnostic_stats["exec_abort_buy"] += 1
            elif action == TradeAction.SELL:
                diagnostic_stats["ai_sell"] += 1
                if trade.executed: diagnostic_stats["exec_sell"] += 1
                else: diagnostic_stats["exec_abort_sell"] += 1
            else:
                diagnostic_stats["ai_hold"] += 1
                if len(diagnostic_stats["hold_reasons"]) < 3:
                    diagnostic_stats["hold_reasons"].append(f"[{date_str}]{reason[:100]}")
                
            self.trades.append(trade)

            # 3f. 记录每日净值
            benchmark_price = await self._get_benchmark_price(date_str)
            benchmark_ratio = 1.0
            if benchmark_start_price and benchmark_price and benchmark_start_price > 0:
                benchmark_ratio = benchmark_price / benchmark_start_price
            await self._record_daily_equity(date_str, price, benchmark_start_price, benchmark_ratio, trade.total_assets)

        # 4. 计算最终绩效指标
        await self._update_progress(97, trading_days[-1] if trading_days else "", "📊 计算绩效指标...")
        
        # 如果没有任何执行的交易，打印诊断报告
        if diagnostic_stats["exec_buy"] == 0 and diagnostic_stats["exec_sell"] == 0:
            reasons_str = " | ".join(diagnostic_stats["hold_reasons"])
            diag_str = f"🛑 回测0交易诊断: 总单={diagnostic_stats['days_total']}, 无价格={diagnostic_stats['days_price_none']}, " \
                       f"AI买入={diagnostic_stats['ai_buy']}(执行失败={diagnostic_stats['exec_abort_buy']}), " \
                       f"AI卖出={diagnostic_stats['ai_sell']}(执行失败={diagnostic_stats['exec_abort_sell']}), " \
                       f"AI持有={diagnostic_stats['ai_hold']}次。持有原因摘录: {reasons_str}"
            logger.error(diag_str)
            # 把诊断信息写到一条 fake trade 记录中，方便前端直接看到
            self.trades.append(TradeRecord(
                date=self.config.end_date,
                action=TradeAction.HOLD,
                price=0.0, shares=0, amount=0.0, commission=0.0, stamp_duty=0.0,
                total_cost=0.0, cash=self.cash, position_shares=self.position_shares,
                position_value=0.0, total_assets=self.cash,
                ai_signal="DIAGNOSTIC", ai_confidence=1.0,
                ai_reason=diag_str,
                t1_restriction=False, limit_up=False, limit_down=False, executed=True
            ))

        metrics = self._calculate_metrics(trading_days)

        result = BacktestResult(
            task_id=self.task.task_id,
            symbol=self.config.symbol,
            stock_name=self.config.stock_name,
            metrics=metrics,
            trades=self.trades,
            daily_equity=self.daily_equity
        )

        logger.info(f"✅ 回测完成: 总收益率 {metrics.total_return:.2f}%, 最大回撤 {metrics.max_drawdown:.2f}%")
        return result

    async def _execute_trade(
        self, date_str: str, price: float, action: TradeAction,
        confidence: float, reason: str, t1_restricted: bool,
        limit_up: Optional[float], limit_down: Optional[float]
    ) -> TradeRecord:
        """执行单笔交易，返回 TradeRecord"""
        shares = 0
        amount = 0.0
        commission = 0.0
        stamp_duty = 0.0
        executed = False
        is_limit_up = False
        is_limit_down = False

        # 检查涨跌停
        if limit_up and price >= limit_up * 0.995:
            is_limit_up = True
        if limit_down and price <= limit_down * 1.005:
            is_limit_down = True

        if action == TradeAction.BUY and self.position_shares == 0:
            # 买入条件：空仓，不在涨停板
            if not is_limit_up:
                shares = self._calculate_buy_shares(price)
                if shares >= 100:
                    amount = shares * price
                    commission, stamp_duty = self._calc_commission(amount, is_buy=True)
                    total_cost = amount + commission + stamp_duty
                    if total_cost <= self.cash:
                        self.cash -= total_cost
                        self.position_shares += shares
                        self.buy_date = date_str
                        self.avg_buy_price = price
                        executed = True
                        logger.info(f"  ✅ 买入: {date_str} {shares}股 @ {price} | 费用:{commission:.2f}+{stamp_duty:.2f}")

        elif action == TradeAction.SELL and self.position_shares > 0:
            # 卖出条件：有持仓，未受T+1限制，不在跌停板
            if not t1_restricted and not is_limit_down:
                shares = self.position_shares
                amount = shares * price
                commission, stamp_duty = self._calc_commission(amount, is_buy=False)
                net_income = amount - commission - stamp_duty
                self.cash += net_income

                # 记录完整交易周期
                buy_amount = shares * self.avg_buy_price
                profit = net_income - buy_amount
                self.completed_trades.append({
                    "profit": profit,
                    "buy_date": self.buy_date,
                    "sell_date": date_str
                })
                if self.buy_date:
                    holding_days = (
                        datetime.strptime(date_str, "%Y-%m-%d") -
                        datetime.strptime(self.buy_date, "%Y-%m-%d")
                    ).days
                else:
                    holding_days = 0

                self.position_shares = 0
                self.buy_date = None
                self.avg_buy_price = 0.0
                executed = True
                logger.info(f"  ✅ 卖出: {date_str} {shares}股 @ {price} | 盈亏:{profit:.2f}")

        total_assets = self.cash + self.position_shares * price

        # 更新最大回撤
        if total_assets > self.peak_assets:
            self.peak_assets = total_assets
        drawdown_pct = (self.peak_assets - total_assets) / self.peak_assets * 100 if self.peak_assets > 0 else 0.0
        if drawdown_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown_pct

        return TradeRecord(
            date=date_str,
            action=action if executed else TradeAction.HOLD,
            price=price,
            shares=shares,
            amount=amount,
            commission=commission,
            stamp_duty=stamp_duty,
            total_cost=amount + commission + stamp_duty if action == TradeAction.BUY else amount - commission - stamp_duty if action == TradeAction.SELL else 0.0,
            cash=self.cash,
            position_shares=self.position_shares,
            position_value=self.position_shares * price,
            total_assets=total_assets,
            ai_signal=str(action.value),
            ai_confidence=confidence,
            ai_reason=reason,
            t1_restriction=t1_restricted,
            limit_up=is_limit_up,
            limit_down=is_limit_down,
            executed=executed
        )

    async def _record_daily_equity(
        self, date_str: str, price: float,
        benchmark_start_price: Optional[float] = None,
        benchmark_ratio: float = 1.0,
        total_assets: Optional[float] = None
    ):
        """记录每日净值"""
        if total_assets is None:
            total_assets = self.cash + self.position_shares * price

        equity_ratio = total_assets / self.config.initial_capital if self.config.initial_capital > 0 else 1.0
        drawdown = (self.peak_assets - total_assets) / self.peak_assets * 100 if self.peak_assets > 0 else 0.0

        self.daily_equity.append(DailyEquity(
            date=date_str,
            total_assets=total_assets,
            cash=self.cash,
            position_value=self.position_shares * price,
            equity_ratio=round(equity_ratio, 6),
            benchmark_ratio=round(benchmark_ratio, 6),
            drawdown=round(drawdown, 4)
        ))

    def _calculate_metrics(self, trading_days: List[str]) -> BacktestMetrics:
        """计算最终绩效指标"""
        if not self.daily_equity:
            # 无数据时返回空指标
            return BacktestMetrics(
                total_return=0.0, annual_return=0.0,
                max_drawdown=0.0, sharpe_ratio=0.0, volatility=0.0,
                total_trades=0, final_assets=self.config.initial_capital,
                initial_capital=self.config.initial_capital,
                profit_loss=0.0, start_date=self.config.start_date, end_date=self.config.end_date
            )

        initial = self.config.initial_capital
        final = self.daily_equity[-1].total_assets

        # 收益指标
        total_return = (final - initial) / initial * 100

        # 计算实际交易天数（日历天数，而非交易日）
        start_dt = datetime.strptime(self.config.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(self.config.end_date, "%Y-%m-%d")
        calendar_days = (end_dt - start_dt).days or 1
        annual_return = ((final / initial) ** (365.0 / calendar_days) - 1) * 100 if final > 0 else 0.0

        # 基准收益率（最后一日净值比）
        benchmark_final_ratio = self.daily_equity[-1].benchmark_ratio if self.daily_equity else 1.0
        benchmark_return = (benchmark_final_ratio - 1) * 100
        excess_return = total_return - benchmark_return

        # 波动率（年化日收益标准差）
        daily_returns = []
        for i in range(1, len(self.daily_equity)):
            prev = self.daily_equity[i - 1].total_assets
            curr = self.daily_equity[i].total_assets
            if prev > 0:
                daily_returns.append((curr - prev) / prev)

        if len(daily_returns) > 1:
            mean_r = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            volatility = math.sqrt(variance) * math.sqrt(252) * 100  # 年化
        else:
            volatility = 0.0

        # 夏普比率
        if volatility > 0:
            sharpe_ratio = (annual_return - self.RISK_FREE_RATE * 100) / volatility
        else:
            sharpe_ratio = 0.0

        # 交易统计
        buy_trades = sum(1 for t in self.trades if t.executed and t.action == TradeAction.BUY)
        sell_trades = sum(1 for t in self.trades if t.executed and t.action == TradeAction.SELL)
        win_trades = sum(1 for t in self.completed_trades if t["profit"] > 0)
        lose_trades = sum(1 for t in self.completed_trades if t["profit"] <= 0)
        total_closed_trades = len(self.completed_trades)
        win_rate = (win_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0.0

        # 平均持仓天数
        holding_days_list = []
        for t in self.completed_trades:
            if t.get("buy_date") and t.get("sell_date"):
                days = (
                    datetime.strptime(t["sell_date"], "%Y-%m-%d") -
                    datetime.strptime(t["buy_date"], "%Y-%m-%d")
                ).days
                holding_days_list.append(days)
        avg_holding_days = sum(holding_days_list) / len(holding_days_list) if holding_days_list else 0.0

        # 费用统计
        total_commission = sum(t.commission for t in self.trades)
        total_stamp_duty = sum(t.stamp_duty for t in self.trades)

        return BacktestMetrics(
            total_return=round(total_return, 4),
            annual_return=round(annual_return, 4),
            benchmark_return=round(benchmark_return, 4),
            excess_return=round(excess_return, 4),
            max_drawdown=round(self.max_drawdown_pct, 4),
            sharpe_ratio=round(sharpe_ratio, 4),
            volatility=round(volatility, 4),
            total_trades=buy_trades + sell_trades,
            buy_trades=buy_trades,
            sell_trades=sell_trades,
            win_trades=win_trades,
            lose_trades=lose_trades,
            win_rate=round(win_rate, 4),
            avg_holding_days=round(avg_holding_days, 2),
            total_commission=round(total_commission, 2),
            total_stamp_duty=round(total_stamp_duty, 2),
            total_fees=round(total_commission + total_stamp_duty, 2),
            final_assets=round(final, 2),
            initial_capital=round(initial, 2),
            profit_loss=round(final - initial, 2),
            trading_days=len(trading_days),
            start_date=self.config.start_date,
            end_date=self.config.end_date
        )


class BacktestService:
    """回测服务：管理回测任务的创建、执行、查询"""

    def _estimate_trading_days_fast(self, start_date: str, end_date: str) -> int:
        """粗略估算交易日数量，用于创建任务时的自动降载决策"""
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        trading_days = 0
        cur = start_dt
        while cur <= end_dt:
            if cur.weekday() < 5:
                trading_days += 1
            cur += timedelta(days=1)
        return trading_days

    def _estimate_analyst_weight(self, analysts: List[str]) -> int:
        """估算分析师负载权重，覆盖 sentiment 在图中的额外展开成本"""
        unique_analysts = set(analysts or [])
        weight = len(unique_analysts)
        if "sentiment" in unique_analysts:
            # sentiment 会在图中额外扩展为 social + emotion
            weight += 2
        return max(1, weight)

    def _auto_optimize_backtest_config(self, config: BacktestConfig) -> Optional[str]:
        """
        对明显过重的回测自动开启加速/极速模式。
        仅在用户仍使用逐日重算时介入，避免覆盖用户已经做出的明确选择。
        """
        if (config.decision_interval_days or 1) > 1:
            return None

        estimated_days = self._estimate_trading_days_fast(config.start_date, config.end_date)
        analyst_weight = self._estimate_analyst_weight(config.selected_analysts)
        workload_score = estimated_days * analyst_weight

        optimized_interval = 1
        if workload_score >= 180 or (estimated_days >= 35 and analyst_weight >= 5):
            optimized_interval = 5
        elif workload_score >= 90 or (estimated_days >= 20 and analyst_weight >= 4):
            optimized_interval = 3

        if optimized_interval == 1:
            return None

        config.decision_interval_days = optimized_interval
        note = (
            f"检测到本次回测负载较高，已自动切换为每 {optimized_interval} 个交易日重算一次 AI"
            f"（估算交易日 {estimated_days}，分析师权重 {analyst_weight}）"
        )
        logger.warning("⚡ [回测自动降载] %s | symbol=%s", note, config.symbol)
        return note

    async def create_task(self, user_id: str, config: BacktestConfig) -> Dict[str, Any]:
        """创建并提交回测任务（异步执行）"""
        task_id = str(uuid.uuid4())
        optimization_note = self._auto_optimize_backtest_config(config)

        # 标准化股票名称（尝试从 AkShare 获取）
        if not config.stock_name:
            config.stock_name = await self._get_stock_name(config.symbol)

        # 将 user_id 转为 PyObjectId
        try:
            uid = PyObjectId(ObjectId(user_id)) if user_id != "admin" else PyObjectId(ObjectId("507f1f77bcf86cd799439011"))
        except Exception:
            uid = PyObjectId(ObjectId())

        task = BacktestTask(
            task_id=task_id,
            user_id=uid,
            config=config,
            status=BacktestStatus.PENDING
        )

        # 保存到 MongoDB
        db = get_mongo_db()
        await db.backtest_tasks.insert_one(task.model_dump(by_alias=True))
        logger.info(f"✅ 回测任务已创建: {task_id}")

        # 在后台异步启动
        asyncio.create_task(self._run_task_background(task))

        return {
            "task_id": task_id,
            "status": BacktestStatus.PENDING,
            "symbol": config.symbol,
            "start_date": config.start_date,
            "end_date": config.end_date,
            "decision_interval_days": config.decision_interval_days,
            "optimization_note": optimization_note,
            "message": optimization_note or "回测任务已提交，正在后台运行"
        }

    async def _run_task_background(self, task: BacktestTask):
        """后台运行回测任务"""
        db = get_mongo_db()
        engine: Optional[BacktestEngine] = None
        try:
            # 更新状态为 running
            started_at = now_tz()
            await db.backtest_tasks.update_one(
                {"task_id": task.task_id},
                {"$set": {"status": BacktestStatus.RUNNING, "started_at": started_at}}
            )

            engine = BacktestEngine(task)
            result = await engine.run()

            # 保存结果
            completed_at = now_tz()
            await db.backtest_tasks.update_one(
                {"task_id": task.task_id},
                {"$set": {
                    "status": BacktestStatus.COMPLETED,
                    "progress": 100,
                    "result": result.model_dump(),
                    "completed_at": completed_at,
                    "current_step": "✅ 回测完成"
                }}
            )
            logger.info(f"✅ 回测任务完成: {task.task_id}")

        except Exception as e:
            logger.error(f"❌ 回测任务失败: {task.task_id} - {e}", exc_info=True)
            await db.backtest_tasks.update_one(
                {"task_id": task.task_id},
                {"$set": {
                    "status": BacktestStatus.FAILED,
                    "error_message": str(e),
                    "completed_at": now_tz(),
                    "current_step": f"❌ 失败: {str(e)[:200]}"
                }}
            )
        finally:
            if engine is not None:
                await engine.close()

    async def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        db = get_mongo_db()
        doc = await db.backtest_tasks.find_one(
            {"task_id": task_id},
            {"result": 0}  # 不返回完整结果（可能很大）
        )
        if not doc:
            return None

        doc.pop("_id", None)
        return {
            "task_id": doc.get("task_id"),
            "status": doc.get("status"),
            "progress": doc.get("progress", 0),
            "current_date": doc.get("current_date"),
            "current_step": doc.get("current_step"),
            "symbol": doc.get("config", {}).get("symbol"),
            "start_date": doc.get("config", {}).get("start_date"),
            "end_date": doc.get("config", {}).get("end_date"),
            "created_at": doc.get("created_at"),
            "started_at": doc.get("started_at"),
            "completed_at": doc.get("completed_at"),
            "error_message": doc.get("error_message")
        }

    async def get_task_result(self, task_id: str) -> Optional[Dict]:
        """获取完整回测结果"""
        db = get_mongo_db()
        doc = await db.backtest_tasks.find_one({"task_id": task_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return doc

    async def list_user_tasks(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict]:
        """获取用户的回测任务列表"""
        db = get_mongo_db()
        try:
            uid_str = user_id if user_id != "admin" else "507f1f77bcf86cd799439011"
            uid_obj = ObjectId(uid_str)
        except Exception:
            uid_str = user_id
            uid_obj = None

        if uid_obj:
            query = {"user_id": {"$in": [uid_str, uid_obj]}}
        else:
            query = {"user_id": uid_str}
            
        cursor = db.backtest_tasks.find(query, {"result": 0}).sort("created_at", -1).skip(offset).limit(limit)
        tasks = []
        async for doc in cursor:
            doc.pop("_id", None)
            tasks.append({
                "task_id": doc.get("task_id"),
                "status": doc.get("status"),
                "progress": doc.get("progress", 0),
                "symbol": doc.get("config", {}).get("symbol"),
                "stock_name": doc.get("config", {}).get("stock_name"),
                "start_date": doc.get("config", {}).get("start_date"),
                "end_date": doc.get("config", {}).get("end_date"),
                "name": doc.get("config", {}).get("name", ""),
                "created_at": doc.get("created_at"),
                "completed_at": doc.get("completed_at"),
                "error_message": doc.get("error_message"),
                # 如果已完成，包含核心指标
                "total_return": (doc.get("result") or {}).get("metrics", {}).get("total_return") if doc.get("result") else None,
                "max_drawdown": (doc.get("result") or {}).get("metrics", {}).get("max_drawdown") if doc.get("result") else None,
            })
        return tasks

    async def delete_task(self, task_id: str, user_id: str) -> bool:
        """删除回测任务"""
        db = get_mongo_db()
        result = await db.backtest_tasks.delete_one({"task_id": task_id})
        return result.deleted_count > 0

    async def _get_stock_name(self, symbol: str) -> Optional[str]:
        """通过 AkShare 获取股票名称"""
        try:
            import akshare as ak
            code = _normalize_symbol(symbol)
            df = ak.stock_individual_info_em(symbol=code)
            if df is not None and not df.empty:
                name_row = df[df.iloc[:, 0] == "股票简称"]
                if not name_row.empty:
                    return str(name_row.iloc[0, 1])
        except Exception as e:
            logger.debug(f"⚠️ 获取股票名称失败: {e}")
        return None


# 单例服务 
_backtest_service: Optional[BacktestService] = None


def get_backtest_service() -> BacktestService:
    """获取回测服务单例"""
    global _backtest_service
    if _backtest_service is None:
        _backtest_service = BacktestService()
    return _backtest_service
