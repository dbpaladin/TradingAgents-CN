import asyncio
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_simple_analysis_service_module():
    trading_graph = types.ModuleType("tradingagents.graph.trading_graph")
    trading_graph.TradingAgentsGraph = object
    sys.modules["tradingagents.graph.trading_graph"] = trading_graph

    default_config = types.ModuleType("tradingagents.default_config")
    default_config.DEFAULT_CONFIG = {}
    sys.modules["tradingagents.default_config"] = default_config

    logging_init = types.ModuleType("tradingagents.utils.logging_init")
    logging_init.init_logging = lambda: None
    sys.modules["tradingagents.utils.logging_init"] = logging_init

    analysis_models = types.ModuleType("app.models.analysis")
    analysis_models.AnalysisTask = object
    analysis_models.AnalysisStatus = object
    analysis_models.SingleAnalysisRequest = object
    analysis_models.AnalysisParameters = object
    sys.modules["app.models.analysis"] = analysis_models

    user_models = types.ModuleType("app.models.user")
    user_models.PyObjectId = str
    sys.modules["app.models.user"] = user_models

    notification_models = types.ModuleType("app.models.notification")
    notification_models.NotificationCreate = object
    sys.modules["app.models.notification"] = notification_models

    bson_module = types.ModuleType("bson")

    class ObjectId(str):
        def __new__(cls, value="507f1f77bcf86cd799439011"):
            return str.__new__(cls, value)

    bson_module.ObjectId = ObjectId
    sys.modules["bson"] = bson_module

    database_module = types.ModuleType("app.core.database")
    database_module.get_mongo_db = lambda: None
    sys.modules["app.core.database"] = database_module

    config_service_module = types.ModuleType("app.services.config_service")

    class ConfigService:
        async def get_system_config(self):
            return None

    config_service_module.ConfigService = ConfigService
    sys.modules["app.services.config_service"] = config_service_module

    memory_state_module = types.ModuleType("app.services.memory_state_manager")

    class DummyMemoryManager:
        def set_websocket_manager(self, manager):
            self.manager = manager

    memory_state_module.get_memory_state_manager = lambda: DummyMemoryManager()
    memory_state_module.TaskStatus = types.SimpleNamespace(RUNNING="RUNNING")
    sys.modules["app.services.memory_state_manager"] = memory_state_module

    redis_progress_module = types.ModuleType("app.services.redis_progress_tracker")
    redis_progress_module.RedisProgressTracker = object
    redis_progress_module.get_progress_by_id = lambda task_id: None
    sys.modules["app.services.redis_progress_tracker"] = redis_progress_module

    progress_log_module = types.ModuleType("app.services.progress_log_handler")
    progress_log_module.register_analysis_tracker = lambda *args, **kwargs: None
    progress_log_module.unregister_analysis_tracker = lambda *args, **kwargs: None
    sys.modules["app.services.progress_log_handler"] = progress_log_module

    path = Path(__file__).resolve().parents[1] / "app" / "services" / "simple_analysis_service.py"
    spec = spec_from_file_location("simple_analysis_service_under_test", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_service(module):
    service = module.SimpleAnalysisService.__new__(module.SimpleAnalysisService)
    service._stock_name_cache = {}
    return service


def test_normalize_probability_score_and_report_text():
    module = _load_simple_analysis_service_module()
    service = _make_service(module)

    assert service._normalize_probability_score(78) == 0.78
    assert service._normalize_probability_score("69%") == 0.69
    assert service._normalize_probability_score(0.72) == 0.72

    normalized = service._normalize_report_score_text("**置信度：0.69**\n**风险评分：72**")
    assert "69.0%" in normalized
    assert "72.0%" in normalized


def test_save_modular_reports_writes_news_fallback_and_normalizes_scores(tmp_path, monkeypatch):
    module = _load_simple_analysis_service_module()
    service = _make_service(module)
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))

    result = {
        "analysis_date": "2026-04-21",
        "state": {
            "company_of_interest": "工业富联",
            "trader_investment_plan": "**置信度：0.69**\n**风险评分：0.72**\n最终交易建议: **卖出**",
            "final_trade_decision": "建议：卖出",
        },
        "decision": {
            "action": "卖出",
            "confidence": 78,
            "risk_score": 62,
            "target_price": 56,
            "reasoning": "趋势仍强但短线过热，先以减仓和风控为主。",
        },
        "research_depth": "标准",
        "analysts": ["news", "market"],
    }

    saved_files = asyncio.run(service._save_modular_reports_to_data_dir(result, "601138"))

    news_report = Path(saved_files["news_report"])
    assert news_report.exists()
    assert news_report.read_text(encoding="utf-8").strip()
    assert "降级报告" in news_report.read_text(encoding="utf-8")

    trader_report = Path(saved_files["trader_investment_plan"]).read_text(encoding="utf-8")
    assert "69.0%" in trader_report
    assert "72.0%" in trader_report

    final_decision = Path(saved_files["final_trade_decision"]).read_text(encoding="utf-8")
    assert "78.0%" in final_decision
    assert "62.0%" in final_decision
