import asyncio
import pytest
from types import SimpleNamespace

from app.core.unified_config import UnifiedConfigManager
from app.models.config import LLMConfig
from app.services.config_provider import ConfigProvider


def test_unified_config_falls_back_to_default_llm(tmp_path):
    manager = UnifiedConfigManager()
    manager.paths.models_json = tmp_path / "models.json"
    manager.paths.settings_json = tmp_path / "settings.json"

    assert manager.save_system_settings({"default_llm": "qwen3.5-plus"})

    assert manager.get_default_model() == "qwen3.5-plus"
    assert manager.get_quick_analysis_model() == "qwen3.5-plus"
    assert manager.get_deep_analysis_model() == "qwen3.5-plus"


def test_save_llm_config_persists_default_flag_consistently(tmp_path):
    manager = UnifiedConfigManager()
    manager.paths.models_json = tmp_path / "models.json"
    manager.paths.settings_json = tmp_path / "settings.json"

    assert manager.save_system_settings({"default_llm": "qwen3.5-plus"})
    assert manager.save_llm_config(
        LLMConfig(provider="bailiancoding", model_name="qwen3.5-plus", is_default=True)
    )
    assert manager.save_llm_config(
        LLMConfig(provider="dashscope", model_name="qwen-plus", is_default=False)
    )

    configs = {cfg.model_name: cfg for cfg in manager.get_llm_configs()}
    assert configs["qwen3.5-plus"].is_default is True
    assert configs["qwen-plus"].is_default is False


def test_config_provider_does_not_override_model_selection_from_env(monkeypatch):
    provider = ConfigProvider(ttl_seconds=0)

    async def fake_get_system_config():
        return SimpleNamespace(
            system_settings={
                "quick_analysis_model": "db-quick",
                "deep_analysis_model": "db-deep",
                "default_llm": "db-default",
                "log_level": "INFO",
            }
        )

    monkeypatch.setattr("app.services.config_provider.config_service.get_system_config", fake_get_system_config)
    monkeypatch.setenv("QUICK_ANALYSIS_MODEL", "env-quick")
    monkeypatch.setenv("DEEP_ANALYSIS_MODEL", "env-deep")
    monkeypatch.setenv("DEFAULT_LLM", "env-default")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = asyncio.run(provider.get_effective_system_settings())

    assert settings["quick_analysis_model"] == "db-quick"
    assert settings["deep_analysis_model"] == "db-deep"
    assert settings["default_llm"] == "db-default"
    assert settings["log_level"] == "DEBUG"
