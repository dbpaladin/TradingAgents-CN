import asyncio

import requests

from app.models.config import LLMConfig
from app.services.config_service import ConfigService


class _FakeProvidersCollection:
    async def find_one(self, query):
        if query == {"name": "custom_local"}:
            return {
                "name": "custom_local",
                "display_name": "Custom Local",
                "default_base_url": "http://127.0.0.1:11434/v1",
            }
        return None


class _FakeDb:
    llm_providers = _FakeProvidersCollection()


class _FakeResponse:
    status_code = 200
    text = '{"choices":[{"message":{"content":"OK"}}]}'

    def json(self):
        return {"choices": [{"message": {"content": "OK"}}]}


def test_local_llm_config_can_be_tested_without_api_key(monkeypatch):
    captured = {}
    service = ConfigService()

    async def fake_get_db():
        return _FakeDb()

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(service, "_get_db", fake_get_db)
    monkeypatch.setattr(requests, "post", fake_post)

    result = asyncio.run(
        service.test_llm_config(
            LLMConfig(
                provider="custom_local",
                model_name="qwen2.5:7b",
                api_base="http://127.0.0.1:11434/v1",
            )
        )
    )

    assert result["success"] is True
    assert result["message"] == "成功连接到 custom_local qwen2.5:7b"
    assert captured["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert "Authorization" not in captured["headers"]


def test_remote_llm_config_still_requires_valid_api_key(monkeypatch):
    service = ConfigService()

    async def fake_get_db():
        return _FakeDb()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("requests.post should not be called when API key is missing for remote endpoints")

    monkeypatch.setattr(service, "_get_db", fake_get_db)
    monkeypatch.setattr(requests, "post", fail_if_called)

    result = asyncio.run(
        service.test_llm_config(
            LLMConfig(
                provider="custom_local",
                model_name="qwen2.5:7b",
                api_base="https://api.example.com/v1",
            )
        )
    )

    assert result["success"] is False
    assert result["message"] == "custom_local 未配置有效的API密钥"
