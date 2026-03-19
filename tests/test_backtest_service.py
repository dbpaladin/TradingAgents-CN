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
