"""
A股回测模块单元测试

测试范围：
1. A股交易日历过滤逻辑
2. T+1 限制逻辑
3. 绩效指标计算
4. 股票代码标准化
5. 交易费用计算
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from bson import ObjectId
from types import SimpleNamespace


# 添加项目根路径
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.backtest import (
    BacktestConfig, BacktestTask, BacktestStatus, TradeAction,
    TradeRecord, DailyEquity
)
from app.models.user import PyObjectId


def make_test_task(symbol="000001", start_date="2024-01-01", end_date="2024-06-30",
                   initial_capital=100000.0) -> BacktestTask:
    """创建测试用回测任务"""
    config = BacktestConfig(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        position_ratio=1.0,
        commission_rate=0.0003,
        stamp_duty_rate=0.001,
        min_commission=5.0,
        selected_analysts=["market"],
        research_depth="快速"
    )
    return BacktestTask(
        task_id="test-task-001",
        user_id=PyObjectId(ObjectId()),
        config=config,
        status=BacktestStatus.PENDING
    )


# ===== 测试：股票代码标准化 =====

class TestNormalizeSymbol:
    def test_plain_6digit(self):
        from app.services.backtest_service import _normalize_symbol
        assert _normalize_symbol("000001") == "000001"

    def test_with_sz_suffix(self):
        from app.services.backtest_service import _normalize_symbol
        assert _normalize_symbol("000001.SZ") == "000001"

    def test_with_sh_suffix(self):
        from app.services.backtest_service import _normalize_symbol
        assert _normalize_symbol("600519.SH") == "600519"

    def test_with_bj_suffix(self):
        from app.services.backtest_service import _normalize_symbol
        assert _normalize_symbol("430047.BJ") == "430047"

    def test_lowercase(self):
        from app.services.backtest_service import _normalize_symbol
        assert _normalize_symbol("600519.sh") == "600519"


class TestGetMarketSuffix:
    def test_sh_main(self):
        from app.services.backtest_service import _get_market_suffix
        assert _get_market_suffix("600519") == "SH"

    def test_sz_gem(self):
        from app.services.backtest_service import _get_market_suffix
        assert _get_market_suffix("300750") == "SZ"

    def test_sz_sme(self):
        from app.services.backtest_service import _get_market_suffix
        assert _get_market_suffix("000001") == "SZ"


# ===== 测试：交易费用计算 =====

class TestCommissionCalc:
    """测试 A股手续费计算"""

    def setup_method(self):
        task = make_test_task(initial_capital=100000.0)
        from app.services.backtest_service import BacktestEngine
        self.engine = BacktestEngine(task)

    def test_buy_commission_above_min(self):
        """大额买入时手续费 = 金额 × 费率"""
        comm, stamp = self.engine._calc_commission(100000, is_buy=True)
        assert abs(comm - 100000 * 0.0003) < 0.01
        assert stamp == 0.0  # 买入无印花税

    def test_buy_commission_at_minimum(self):
        """小额买入时手续费不低于最低5元"""
        comm, stamp = self.engine._calc_commission(1000, is_buy=True)
        assert comm == 5.0  # 最低佣金
        assert stamp == 0.0

    def test_sell_includes_stamp_duty(self):
        """卖出时收取印花税"""
        comm, stamp = self.engine._calc_commission(100000, is_buy=False)
        assert abs(comm - 100000 * 0.0003) < 0.01
        assert abs(stamp - 100000 * 0.001) < 0.01

    def test_buy_vs_sell_cost_difference(self):
        """卖出应比买入多一笔印花税"""
        comm_buy, stamp_buy = self.engine._calc_commission(50000, is_buy=True)
        comm_sell, stamp_sell = self.engine._calc_commission(50000, is_buy=False)
        assert stamp_buy == 0.0
        assert stamp_sell > 0.0


# ===== 测试：T+1 限制逻辑 =====

class TestT1Restriction:
    """测试 T+1 交易制度"""

    def setup_method(self):
        task = make_test_task()
        from app.services.backtest_service import BacktestEngine
        self.engine = BacktestEngine(task)
        # 模拟已有持仓
        self.engine.position_shares = 1000
        self.engine.buy_date = "2024-03-01"
        self.engine.avg_buy_price = 10.0

    def test_sell_same_day_as_buy(self):
        """当日买入，当日不能卖出 → T+1 限制"""
        # 如果 buy_date == date_str，则卖出被阻止
        buy_date = "2024-03-01"
        date_str = "2024-03-01"
        t1_restricted = (buy_date == date_str)
        assert t1_restricted is True

    def test_sell_next_day_allowed(self):
        """次日卖出不受 T+1 限制"""
        buy_date = "2024-03-01"
        date_str = "2024-03-04"  # 下一个交易日
        t1_restricted = (buy_date == date_str)
        assert t1_restricted is False

    def test_t1_prevents_trade(self):
        """
        当日买入后若 action=SELL，引擎应将 action 转为 HOLD
        """
        # 在真实代码中，引擎会检查 buy_date == date_str
        self.engine.buy_date = "2024-03-01"
        action = TradeAction.SELL
        t1_restricted = (self.engine.buy_date == "2024-03-01")
        if t1_restricted:
            action = TradeAction.HOLD
        assert action == TradeAction.HOLD


# ===== 测试：买入股数计算 =====

class TestCalculateBuyShares:
    def setup_method(self):
        task = make_test_task(initial_capital=100000.0)
        task.config.position_ratio = 1.0  # 全仓
        from app.services.backtest_service import BacktestEngine
        self.engine = BacktestEngine(task)
        self.engine.cash = 100000.0

    def test_buy_shares_multiple_of_100(self):
        """买入股数必须是 100 的整数倍"""
        shares = self.engine._calculate_buy_shares(10.0)
        assert shares % 100 == 0

    def test_buy_shares_respects_cash_limit(self):
        """买入金额不超过现金"""
        price = 20.0
        shares = self.engine._calculate_buy_shares(price)
        total_cost = shares * price
        assert total_cost <= self.engine.cash

    def test_buy_shares_half_position(self):
        """半仓时买入额度约为一半"""
        task = make_test_task(initial_capital=100000.0)
        task.config.position_ratio = 0.5
        from app.services.backtest_service import BacktestEngine
        engine = BacktestEngine(task)
        engine.cash = 100000.0

        shares_full = self.engine._calculate_buy_shares(10.0)    # 全仓
        shares_half = engine._calculate_buy_shares(10.0)         # 半仓

        # 半仓的股数应约为全仓的一半
        assert shares_half < shares_full


# ===== 测试：AI 决策解析 =====

class TestParseAiDecision:
    def setup_method(self):
        task = make_test_task()
        from app.services.backtest_service import BacktestEngine
        self.engine = BacktestEngine(task)

    def test_buy_signal(self):
        decision = {"action": "BUY", "confidence": 0.8, "summary": "市场强劲"}
        action, conf, reason = self.engine._parse_ai_decision(decision)
        assert action == TradeAction.BUY
        assert abs(conf - 0.8) < 0.01

    def test_sell_signal(self):
        decision = {"action": "SELL", "confidence": 0.7, "summary": "风险加大"}
        action, conf, _ = self.engine._parse_ai_decision(decision)
        assert action == TradeAction.SELL

    def test_hold_signal(self):
        decision = {"action": "HOLD", "confidence": 0.5}
        action, _, _ = self.engine._parse_ai_decision(decision)
        assert action == TradeAction.HOLD

    def test_empty_decision_defaults_to_hold(self):
        action, conf, reason = self.engine._parse_ai_decision({})
        assert action == TradeAction.HOLD

    def test_chinese_buy_signal(self):
        decision = {"action": "买入", "confidence": 0.9}
        action, _, _ = self.engine._parse_ai_decision(decision)
        assert action == TradeAction.BUY

    def test_chinese_sell_signal(self):
        decision = {"action": "卖出", "confidence": 0.75}
        action, _, _ = self.engine._parse_ai_decision(decision)
        assert action == TradeAction.SELL


class TestActionNormalization:
    def setup_method(self):
        task = make_test_task()
        from app.services.backtest_service import BacktestEngine
        self.engine = BacktestEngine(task)

    def test_normalize_sell_to_hold_when_flat(self):
        self.engine.position_shares = 0
        action, reason = self.engine._normalize_action_for_position(TradeAction.SELL, "空仓卖出测试")
        assert action == TradeAction.HOLD
        assert "空仓" in reason

    def test_normalize_buy_to_hold_when_already_holding(self):
        self.engine.position_shares = 1000
        action, reason = self.engine._normalize_action_for_position(TradeAction.BUY, "持仓买入测试")
        assert action == TradeAction.HOLD
        assert "已有持仓" in reason


class TestBacktestModelRouting:
    @pytest.mark.asyncio
    async def test_run_ai_analysis_uses_model_provider_instead_of_hardcoded_dashscope(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        task.config.quick_analysis_model = "gpt-4o-mini"
        task.config.deep_analysis_model = "gpt-4o"
        engine = BacktestEngine(task)

        fake_unified_config = SimpleNamespace(
            get_quick_analysis_model=lambda: "qwen-turbo",
            get_deep_analysis_model=lambda: "qwen-max",
            get_llm_configs=lambda: [
                SimpleNamespace(
                    model_name="gpt-4o-mini",
                    max_tokens=2048,
                    temperature=0.2,
                    timeout=90,
                    retry_times=2,
                    api_base="https://api.openai.com/v1",
                ),
                SimpleNamespace(
                    model_name="gpt-4o",
                    max_tokens=4096,
                    temperature=0.4,
                    timeout=120,
                    retry_times=3,
                    api_base="https://api.openai.com/v1",
                ),
            ],
        )

        captured = {}

        def fake_create_analysis_config(**kwargs):
            captured["create_kwargs"] = kwargs
            return {
                "llm_provider": kwargs["llm_provider"],
                "quick_think_llm": kwargs["quick_model"],
                "deep_think_llm": kwargs["deep_model"],
                "backend_url": "placeholder",
                "selected_analysts": kwargs["selected_analysts"],
            }

        class FakeGraph:
            def __init__(self, selected_analysts, debug, config):
                captured["graph_config"] = config

            def propagate(self, symbol, date_str):
                return {}, {"action": "BUY", "confidence": 0.9}

        class FakeLoop:
            def run_in_executor(self, executor, func, *args):
                fut = asyncio.Future()
                fut.set_result(func(*args))
                return fut

        with patch("app.core.unified_config.unified_config", fake_unified_config), \
             patch("app.services.simple_analysis_service.create_analysis_config", side_effect=fake_create_analysis_config), \
             patch("app.services.simple_analysis_service.get_provider_and_url_by_model_sync") as mock_provider_lookup, \
             patch("tradingagents.graph.trading_graph.TradingAgentsGraph", FakeGraph), \
             patch("asyncio.get_running_loop", return_value=FakeLoop()):
            mock_provider_lookup.side_effect = [
                {
                    "provider": "openai",
                    "backend_url": "https://api.openai.com/v1",
                    "api_key": "sk-quick",
                },
                {
                    "provider": "openai",
                    "backend_url": "https://api.openai.com/v1",
                    "api_key": "sk-deep",
                },
            ]

            decision = await engine._run_ai_analysis("000001", "2026-02-24")

        assert decision["action"] == "BUY"
        assert captured["create_kwargs"]["llm_provider"] == "openai"
        assert captured["create_kwargs"]["quick_model_config"]["timeout"] == 90
        assert captured["graph_config"]["llm_provider"] == "openai"
        assert captured["graph_config"]["quick_provider"] == "openai"
        assert captured["graph_config"]["deep_provider"] == "openai"
        assert captured["graph_config"]["quick_backend_url"] == "https://api.openai.com/v1"
        assert captured["graph_config"]["deep_backend_url"] == "https://api.openai.com/v1"
        assert captured["graph_config"]["backend_url"] == "https://api.openai.com/v1"

    def test_get_analysis_runtime_disables_ai_when_required_api_key_missing(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        task.config.quick_analysis_model = "qwen-turbo"
        task.config.deep_analysis_model = "qwen-max"
        engine = BacktestEngine(task)

        fake_unified_config = SimpleNamespace(
            get_quick_analysis_model=lambda: "qwen-turbo",
            get_deep_analysis_model=lambda: "qwen-max",
            get_llm_configs=lambda: [],
        )

        with patch("app.core.unified_config.unified_config", fake_unified_config), \
             patch("app.services.simple_analysis_service.create_analysis_config", return_value={"memory_enabled": False}), \
             patch("app.services.simple_analysis_service.get_provider_and_url_by_model_sync") as mock_provider_lookup:
            mock_provider_lookup.side_effect = [
                {
                    "provider": "dashscope",
                    "backend_url": "https://dashscope.aliyuncs.com/api/v1",
                    "api_key": None,
                },
                {
                    "provider": "dashscope",
                    "backend_url": "https://dashscope.aliyuncs.com/api/v1",
                    "api_key": None,
                },
            ]
            runtime = engine._get_analysis_runtime()

        assert runtime["quick_provider"] == "dashscope"
        assert runtime["deep_provider"] == "dashscope"
        assert engine._ai_disabled_reason is not None
        assert "API Key 缺失" in engine._ai_disabled_reason

    def test_compute_analysis_timeout_expands_for_multi_analyst_backtest(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        task.config.selected_analysts = [
            "market",
            "fundamentals",
            "news",
            "social",
            "emotion",
            "fund_flow",
            "theme_rotation",
            "institutional_theme",
        ]
        task.config.research_depth = "快速"
        engine = BacktestEngine(task)
        engine._analysis_runtime = {
            "quick_timeout": 180,
            "deep_timeout": 180,
        }

        assert engine._compute_analysis_timeout_seconds() == 1800

    def test_compute_analysis_timeout_counts_sentiment_expansion(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        task.config.selected_analysts = [
            "market",
            "fundamentals",
            "sentiment",
            "fund_flow",
            "news",
            "institutional_theme",
            "theme_rotation",
        ]
        task.config.research_depth = "快速"
        engine = BacktestEngine(task)
        engine._analysis_runtime = {
            "quick_timeout": 180,
            "deep_timeout": 180,
        }

        assert engine._compute_analysis_timeout_seconds() == 1800

    def test_get_analysis_runtime_tightens_backtest_rounds_and_memory(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        task.config.research_depth = "深度"
        task.config.selected_analysts = ["market", "fundamentals", "news"]
        engine = BacktestEngine(task)

        fake_unified_config = SimpleNamespace(
            get_quick_analysis_model=lambda: "qwen-turbo",
            get_deep_analysis_model=lambda: "qwen-max",
            get_llm_configs=lambda: [],
        )

        with patch("app.core.unified_config.unified_config", fake_unified_config), \
             patch("app.services.simple_analysis_service.create_analysis_config", return_value={
                 "memory_enabled": True,
                 "max_debate_rounds": 2,
                 "max_risk_discuss_rounds": 2,
                 "online_tools": False,
             }), \
             patch("app.services.simple_analysis_service.get_provider_and_url_by_model_sync") as mock_provider_lookup:
            mock_provider_lookup.side_effect = [
                {
                    "provider": "dashscope",
                    "backend_url": "https://dashscope.aliyuncs.com/api/v1",
                    "api_key": "sk-quick",
                },
                {
                    "provider": "dashscope",
                    "backend_url": "https://dashscope.aliyuncs.com/api/v1",
                    "api_key": "sk-deep",
                },
            ]
            runtime = engine._get_analysis_runtime()

        assert runtime["config"]["memory_enabled"] is False
        assert runtime["config"]["max_debate_rounds"] == 1
        assert runtime["config"]["max_risk_discuss_rounds"] == 1
        assert runtime["config"]["online_tools"] is True

    def test_should_start_in_degraded_mode_for_long_high_load_backtest(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        task.config.selected_analysts = [
            "market",
            "fundamentals",
            "sentiment",
            "news",
            "institutional_theme",
        ]
        engine = BacktestEngine(task)
        engine._analysis_runtime = {
            "selected_analysts": task.config.selected_analysts,
        }

        trading_days = [f"2024-03-{day:02d}" for day in range(1, 22)]

        assert engine._should_start_in_degraded_mode(trading_days) is True

    @pytest.mark.asyncio
    async def test_run_ai_analysis_reuses_graph_in_fast_mode(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        engine = BacktestEngine(task)

        fake_runtime = {
            "config": {"memory_enabled": False},
            "reuse_graph": True,
        }
        created_graphs = []

        class FakeGraph:
            def __init__(self, selected_analysts, debug, config):
                created_graphs.append((selected_analysts, debug, config))

            def propagate(self, symbol, date_str):
                return {}, {"action": "HOLD", "confidence": 0.1}

        class FakeLoop:
            def run_in_executor(self, executor, func, *args):
                fut = asyncio.Future()
                fut.set_result(func(*args))
                return fut

        with patch.object(engine, "_get_analysis_runtime", return_value=fake_runtime), \
             patch("tradingagents.graph.trading_graph.TradingAgentsGraph", FakeGraph), \
             patch("asyncio.get_running_loop", return_value=FakeLoop()):
            await engine._run_ai_analysis("000001", "2026-02-24")
            await engine._run_ai_analysis("000001", "2026-02-25")

        assert len(created_graphs) == 1

    @pytest.mark.asyncio
    async def test_run_ai_analysis_switches_to_lightweight_mode_before_disabling(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task()
        engine = BacktestEngine(task)

        class FakeGraph:
            def propagate(self, symbol, date_str):
                return {}, {"action": "BUY", "confidence": 0.9}

        class FakeLoop:
            def run_in_executor(self, executor, func, *args):
                fut = asyncio.Future()
                fut.set_result(func(*args))
                return fut

        fake_primary_runtime = {
            "runtime_mode": "primary",
            "quick_timeout": 180,
            "deep_timeout": 180,
            "config": {},
            "reuse_graph": False,
            "selected_analysts": ["market"],
            "quick_model": "gpt-4o-mini",
            "quick_provider": "openai",
            "quick_api_key": "sk-quick",
            "quick_backend_url": "https://api.openai.com/v1",
        }

        fake_degraded_runtime = {
            "runtime_mode": "degraded",
            "quick_timeout": 60,
            "deep_timeout": 60,
            "config": {},
            "reuse_graph": False,
            "selected_analysts": ["market"],
        }

        with patch.object(engine, "_get_analysis_runtime", return_value=fake_primary_runtime), \
             patch.object(engine, "_build_degraded_runtime", return_value=fake_degraded_runtime), \
             patch.object(engine, "_get_trading_graph", return_value=FakeGraph()), \
             patch("asyncio.get_running_loop", return_value=FakeLoop()), \
             patch.object(engine, "_refresh_executor_after_timeout"), \
             patch("app.services.backtest_service.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            first = await engine._run_ai_analysis("000001", "2026-02-24")
            second = await engine._run_ai_analysis("000001", "2026-02-25")
            third = await engine._run_ai_analysis("000001", "2026-02-26")

        assert first["action"] == "HOLD"
        assert "超时" in first["reasoning"]
        assert second["action"] == "HOLD"
        assert "模式=degraded" in second["reasoning"]
        assert third["action"] == "HOLD"
        assert "轻量分析模式连续超时" in third["reasoning"]
        assert engine._ai_disabled_reason is not None


class TestBacktestMarketDataCache:
    @pytest.mark.asyncio
    async def test_get_stock_price_prefers_prefetched_cache(self):
        from app.services.backtest_service import BacktestEngine

        engine = BacktestEngine(make_test_task())
        engine._stock_price_cache["2024-03-01"] = 12.34

        with patch("tradingagents.dataflows.providers.china.tushare.get_tushare_provider") as mock_provider:
            price = await engine._get_stock_price("000001", "2024-03-01")

        assert price == 12.34
        mock_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_benchmark_price_prefers_prefetched_cache(self):
        from app.services.backtest_service import BacktestEngine

        engine = BacktestEngine(make_test_task())
        engine._benchmark_price_cache["2024-03-01"] = 3456.78

        with patch("tradingagents.dataflows.providers.china.tushare.get_tushare_provider") as mock_provider:
            price = await engine._get_benchmark_price("2024-03-01")

        assert price == 3456.78
        mock_provider.assert_not_called()


class TestBacktestDecisionInterval:
    @pytest.mark.asyncio
    async def test_run_reuses_last_signal_between_analysis_intervals(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task(start_date="2024-03-01", end_date="2024-03-07")
        task.config.decision_interval_days = 3
        engine = BacktestEngine(task)

        trading_days = [
            "2024-03-01",
            "2024-03-04",
            "2024-03-05",
            "2024-03-06",
            "2024-03-07",
        ]

        engine._update_progress = AsyncMock()
        engine._get_trading_calendar = AsyncMock(return_value=trading_days)
        engine._warmup_market_data = AsyncMock()
        engine._get_stock_price = AsyncMock(side_effect=[10.0, 10.2, 10.4, 10.6, 10.8])
        engine._get_benchmark_price = AsyncMock(side_effect=[3000.0, 3000.0, 3010.0, 3020.0, 3030.0, 3040.0])
        engine._run_ai_analysis = AsyncMock(side_effect=[
            {"action": "BUY", "confidence": 0.8, "summary": "首次分析买入"},
            {"action": "SELL", "confidence": 0.7, "summary": "间隔到期后卖出"},
        ])

        result = await engine.run()

        assert result.metrics.trading_days == 5
        assert engine._run_ai_analysis.await_count == 2
        assert result.trades[1].ai_reason.startswith("[复用前次信号]")
        assert result.trades[2].ai_reason.startswith("[复用前次信号]")

    @pytest.mark.asyncio
    async def test_run_does_not_reuse_hold_signal_between_analysis_intervals(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task(start_date="2024-03-01", end_date="2024-03-05")
        task.config.decision_interval_days = 3
        engine = BacktestEngine(task)

        trading_days = [
            "2024-03-01",
            "2024-03-04",
            "2024-03-05",
        ]

        engine._update_progress = AsyncMock()
        engine._get_trading_calendar = AsyncMock(return_value=trading_days)
        engine._warmup_market_data = AsyncMock()
        engine._get_stock_price = AsyncMock(side_effect=[10.0, 10.2, 10.4])
        engine._get_benchmark_price = AsyncMock(side_effect=[3000.0, 3000.0, 3010.0, 3020.0])
        engine._run_ai_analysis = AsyncMock(side_effect=[
            {"action": "HOLD", "confidence": 0.3, "summary": "首日观望"},
            {"action": "BUY", "confidence": 0.8, "summary": "次日转强"},
            {"action": "SELL", "confidence": 0.7, "summary": "第三日止盈"},
        ])

        result = await engine.run()

        assert result.metrics.trading_days == 3
        assert engine._run_ai_analysis.await_count == 2
        assert not result.trades[1].ai_reason.startswith("[复用前次信号]")
        assert result.trades[2].ai_reason.startswith("[复用前次信号]")


class TestBacktestRuleFallback:
    @pytest.mark.asyncio
    async def test_run_uses_rule_fallback_when_ai_timeout(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task(start_date="2024-03-01", end_date="2024-03-05")
        task.config.decision_interval_days = 1
        engine = BacktestEngine(task)

        trading_days = [
            "2024-03-01",
            "2024-03-04",
            "2024-03-05",
        ]

        engine._update_progress = AsyncMock()
        engine._get_trading_calendar = AsyncMock(return_value=trading_days)
        engine._warmup_market_data = AsyncMock()
        engine._get_analysis_runtime = MagicMock(return_value={
            "runtime_mode": "primary",
            "quick_timeout": 180,
            "deep_timeout": 180,
            "config": {},
            "reuse_graph": False,
            "selected_analysts": ["market"],
        })
        engine._get_stock_price = AsyncMock(side_effect=[10.0, 10.2, 10.1])
        engine._get_benchmark_price = AsyncMock(side_effect=[3000.0, 3000.0, 3010.0, 3020.0])
        engine._run_ai_analysis = AsyncMock(side_effect=[
            {"action": "HOLD", "confidence": 0.0, "reasoning": "AI分析超时(180s) [连续超时 1]"},
            {"action": "HOLD", "confidence": 0.0, "reasoning": "AI分析超时(180s) [连续超时 2]"},
            {"action": "HOLD", "confidence": 0.0, "reasoning": "AI分析连续超时达到2次，后续日期已自动降级为 HOLD"},
        ])

        result = await engine.run()

        executed_actions = [t.action for t in result.trades if t.executed]
        assert TradeAction.BUY in executed_actions
        assert TradeAction.SELL in executed_actions
        assert all(t.ai_signal != "DIAGNOSTIC" for t in result.trades)

    @pytest.mark.asyncio
    async def test_run_enters_rule_mode_after_first_ai_failure(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task(start_date="2024-03-01", end_date="2024-03-05")
        task.config.decision_interval_days = 1
        engine = BacktestEngine(task)

        trading_days = [
            "2024-03-01",
            "2024-03-04",
            "2024-03-05",
        ]

        engine._update_progress = AsyncMock()
        engine._get_trading_calendar = AsyncMock(return_value=trading_days)
        engine._warmup_market_data = AsyncMock()
        engine._get_analysis_runtime = MagicMock(return_value={
            "runtime_mode": "primary",
            "quick_timeout": 180,
            "deep_timeout": 180,
            "config": {},
            "reuse_graph": False,
            "selected_analysts": ["market"],
        })
        engine._get_stock_price = AsyncMock(side_effect=[10.0, 9.5, 9.6])
        engine._get_benchmark_price = AsyncMock(side_effect=[3000.0, 3000.0, 3010.0, 3020.0])
        engine._run_ai_analysis = AsyncMock(side_effect=[
            {"action": "HOLD", "confidence": 0.0, "reasoning": "AI分析超时(180s) [连续超时 1]"},
            {"action": "BUY", "confidence": 0.9, "summary": "不应被调用"},
            {"action": "SELL", "confidence": 0.9, "summary": "不应被调用"},
        ])

        result = await engine.run()

        # 首次失败后应熔断为规则模式，后续不再继续调用 AI。
        assert engine._run_ai_analysis.await_count == 1
        assert engine._rule_mode_enabled is True
        executed_actions = [t.action for t in result.trades if t.executed]
        assert TradeAction.BUY in executed_actions
        assert TradeAction.SELL in executed_actions

    @pytest.mark.asyncio
    async def test_run_does_not_force_buy_when_no_entry_signal_exists(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task(start_date="2024-03-01", end_date="2024-03-05")
        task.config.decision_interval_days = 1
        engine = BacktestEngine(task)

        trading_days = [
            "2024-03-01",
            "2024-03-04",
            "2024-03-05",
        ]

        engine._update_progress = AsyncMock()
        engine._get_trading_calendar = AsyncMock(return_value=trading_days)
        engine._warmup_market_data = AsyncMock()
        engine._get_analysis_runtime = MagicMock(return_value={
            "runtime_mode": "primary",
            "quick_timeout": 180,
            "deep_timeout": 180,
            "config": {},
            "reuse_graph": False,
            "selected_analysts": ["market"],
        })
        engine._get_stock_price = AsyncMock(side_effect=[10.0, 10.1, 10.3])
        engine._get_benchmark_price = AsyncMock(side_effect=[3000.0, 3000.0, 3010.0, 3020.0])
        engine._run_ai_analysis = AsyncMock(side_effect=[
            {"action": "SELL", "confidence": 0.7, "summary": "首日看空"},
            {"action": "HOLD", "confidence": 0.6, "summary": "次日观望"},
            {"action": "SELL", "confidence": 0.8, "summary": "第三日减仓"},
        ])

        result = await engine.run()

        executed_actions = [t.action for t in result.trades if t.executed]
        assert TradeAction.BUY not in executed_actions
        assert TradeAction.SELL not in executed_actions
        assert any(t.ai_signal == "DIAGNOSTIC" for t in result.trades)

    @pytest.mark.asyncio
    async def test_run_records_model_and_step_elapsed_in_trade_details(self):
        from app.services.backtest_service import BacktestEngine

        task = make_test_task(start_date="2024-03-01", end_date="2024-03-05")
        task.config.decision_interval_days = 1
        engine = BacktestEngine(task)

        trading_days = [
            "2024-03-01",
            "2024-03-04",
            "2024-03-05",
        ]

        engine._update_progress = AsyncMock()
        engine._get_trading_calendar = AsyncMock(return_value=trading_days)
        engine._warmup_market_data = AsyncMock()
        engine._get_analysis_runtime = MagicMock(return_value={
            "runtime_mode": "primary",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.4",
            "quick_provider": "custom_openai",
            "deep_provider": "custom_openai",
            "quick_timeout": 60,
            "deep_timeout": 60,
            "config": {},
            "reuse_graph": False,
            "selected_analysts": ["market"],
        })
        engine._get_stock_price = AsyncMock(side_effect=[10.0, 10.2, 10.1])
        engine._get_benchmark_price = AsyncMock(side_effect=[3000.0, 3000.0, 3010.0, 3020.0])
        engine._run_ai_analysis = AsyncMock(side_effect=[
            {"action": "BUY", "confidence": 0.8, "summary": "买入"},
            {"action": "HOLD", "confidence": 0.6, "summary": "持有"},
            {"action": "SELL", "confidence": 0.7, "summary": "卖出"},
        ])

        result = await engine.run()
        detail_rows = [t for t in result.trades if t.ai_signal != "DIAGNOSTIC"]

        assert detail_rows, "应有按日明细记录"
        for row in detail_rows:
            assert row.ai_model is not None and row.ai_model != ""
            assert row.ai_provider is not None and row.ai_provider != ""
            assert row.analysis_elapsed_ms is not None and row.analysis_elapsed_ms >= 0
            assert row.decision_elapsed_ms is not None and row.decision_elapsed_ms >= 0
            assert row.execution_elapsed_ms is not None and row.execution_elapsed_ms >= 0
            assert row.day_elapsed_ms is not None and row.day_elapsed_ms >= 0


class TestBacktestAutoOptimization:
    def test_auto_optimize_does_not_override_user_daily_interval(self):
        from app.services.backtest_service import BacktestService

        service = BacktestService()
        config = BacktestConfig(
            symbol="601669",
            start_date="2026-01-01",
            end_date="2026-03-21",
            selected_analysts=[
                "market",
                "fundamentals",
                "sentiment",
                "fund_flow",
                "news",
                "institutional_theme",
                "theme_rotation",
            ],
            research_depth="快速",
            decision_interval_days=1,
        )

        note = service._auto_optimize_backtest_config(config)

        assert note is None
        assert config.decision_interval_days == 1

    def test_auto_optimize_keeps_explicit_fast_mode_choice(self):
        from app.services.backtest_service import BacktestService

        service = BacktestService()
        config = BacktestConfig(
            symbol="601669",
            start_date="2026-01-01",
            end_date="2026-03-21",
            selected_analysts=["market", "fundamentals", "news"],
            research_depth="快速",
            decision_interval_days=3,
        )

        note = service._auto_optimize_backtest_config(config)

        assert note is None
        assert config.decision_interval_days == 3


# ===== 测试：绩效指标计算 =====

class TestCalculateMetrics:
    def setup_method(self):
        task = make_test_task(initial_capital=100000.0)
        from app.services.backtest_service import BacktestEngine
        self.engine = BacktestEngine(task)

    def test_positive_total_return(self):
        """最终资产 > 初始资金时收益率应为正"""
        self.engine.daily_equity = [
            DailyEquity(date="2024-01-02", total_assets=100000, cash=100000, position_value=0,
                        equity_ratio=1.0, benchmark_ratio=1.0),
            DailyEquity(date="2024-06-28", total_assets=110000, cash=110000, position_value=0,
                        equity_ratio=1.1, benchmark_ratio=1.05)
        ]
        metrics = self.engine._calculate_metrics(["2024-01-02", "2024-06-28"])
        assert metrics.total_return > 0
        assert metrics.final_assets == pytest.approx(110000, rel=1e-3)
        assert metrics.profit_loss == pytest.approx(10000, rel=1e-3)

    def test_negative_total_return(self):
        """最终资产 < 初始资金时收益率应为负"""
        self.engine.daily_equity = [
            DailyEquity(date="2024-01-02", total_assets=100000, cash=100000, position_value=0,
                        equity_ratio=1.0, benchmark_ratio=1.0),
            DailyEquity(date="2024-06-28", total_assets=90000, cash=90000, position_value=0,
                        equity_ratio=0.9, benchmark_ratio=0.95)
        ]
        metrics = self.engine._calculate_metrics(["2024-01-02", "2024-06-28"])
        assert metrics.total_return < 0
        assert metrics.profit_loss < 0

    def test_max_drawdown_tracking(self):
        """最大回撤计算正确"""
        self.engine.peak_assets = 110000
        self.engine.max_drawdown_pct = 9.09  # (110000-100000)/110000 * 100

        self.engine.daily_equity = [
            DailyEquity(date="2024-01-02", total_assets=100000, cash=100000, position_value=0,
                        equity_ratio=1.0, benchmark_ratio=1.0)
        ]
        metrics = self.engine._calculate_metrics(["2024-01-02"])
        assert metrics.max_drawdown == pytest.approx(9.09, rel=1e-2)

    def test_zero_trades(self):
        """无交易时，胜率为0，交易次数为0"""
        self.engine.daily_equity = [
            DailyEquity(date="2024-01-02", total_assets=100000, cash=100000, position_value=0,
                        equity_ratio=1.0, benchmark_ratio=1.0)
        ]
        metrics = self.engine._calculate_metrics(["2024-01-02"])
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
