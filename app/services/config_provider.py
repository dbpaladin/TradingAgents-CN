from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import os

from app.services.config_service import config_service


class ConfigProvider:
    """Effective configuration provider with simple env→DB merge and TTL cache.

    - Priority: ENV > DB
    - Cache TTL: configurable (default 60s)
    - Invalidate on writes: caller should invoke `invalidate()` after writes
    """

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._cache_settings: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None

    def invalidate(self) -> None:
        self._cache_settings = None
        self._cache_time = None

    @staticmethod
    def _is_model_setting_key(key: str) -> bool:
        return str(key) in {
            "llm_provider",
            "backend_url",
            "default_llm",
            "default_model",
            "quick_analysis_model",
            "deep_analysis_model",
            "quick_think_llm",
            "deep_think_llm",
            "module_model_overrides",
        }

    def _is_cache_valid(self) -> bool:
        return (
            self._cache_settings is not None
            and self._cache_time is not None
            and __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - self._cache_time < self._ttl
        )

    async def get_effective_system_settings(self) -> Dict[str, Any]:
        if self._is_cache_valid():
            return dict(self._cache_settings or {})

        # Load DB settings
        cfg = await config_service.get_system_config()
        base: Dict[str, Any] = {}
        if cfg and getattr(cfg, "system_settings", None):
            try:
                base = dict(cfg.system_settings)
            except Exception:
                base = {}

        default_llm = None
        if cfg:
            default_llm = getattr(cfg, "default_llm", None) or base.get("default_llm")

        default_provider = None
        if cfg and default_llm:
            try:
                for llm_cfg in getattr(cfg, "llm_configs", []) or []:
                    if getattr(llm_cfg, "model_name", None) == default_llm:
                        default_provider = getattr(llm_cfg, "provider", None)
                        if default_provider:
                            break
            except Exception:
                default_provider = None

        # Merge ENV over DB (best-effort heuristics):
        # - if ENV with exact key exists -> override
        # - try uppercased and dot/space to underscore variants
        merged: Dict[str, Any] = dict(base)
        for k, v in list(base.items()):
            if self._is_model_setting_key(str(k)):
                continue
            candidates = [
                k,
                k.upper(),
                str(k).replace(".", "_").replace(" ", "_").upper(),
            ]
            found = None
            for ek in candidates:
                if ek in os.environ:
                    found = os.environ.get(ek)
                    break
            if found is not None:
                merged[k] = found

        # 将 system_configs 根级别的默认模型信息补齐到 settings 视图中，
        # 避免前端在 quick/deep 未单独设置时错误回退到硬编码 qwen-*。
        if default_llm:
            merged.setdefault("default_llm", default_llm)
            merged.setdefault("default_model", default_llm)
            merged.setdefault("quick_analysis_model", default_llm)
            merged.setdefault("deep_analysis_model", default_llm)
            merged.setdefault("quick_think_llm", default_llm)
            merged.setdefault("deep_think_llm", default_llm)

        if default_provider:
            merged.setdefault("default_provider", default_provider)

        # Optionally: allow whitelisting additional env-only keys via prefix
        # For now, keep minimal behavior to avoid surprising surfaces.

        # Cache
        self._cache_settings = dict(merged)
        self._cache_time = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        return dict(merged)
    async def get_system_settings_meta(self) -> Dict[str, Dict[str, Any]]:
        """Return metadata for system settings keys including sensitivity, editability and source.
        Fields per key:
          - sensitive: bool (by keyword patterns)
          - editable: bool (False if sensitive or source is environment; True otherwise)
          - source: 'environment' | 'database' | 'default'
          - has_value: bool (effective value is not None/empty)
        """
        # Load DB settings raw
        cfg = await config_service.get_system_config()
        db_settings: Dict[str, Any] = {}
        if cfg and getattr(cfg, "system_settings", None):
            try:
                db_settings = dict(cfg.system_settings)
            except Exception:
                db_settings = {}

        def _env_override_for_key(key: str) -> Optional[Any]:
            candidates = [
                key,
                key.upper(),
                str(key).replace(".", "_").replace(" ", "_").upper(),
            ]
            for ek in candidates:
                if ek in os.environ:
                    return os.environ.get(ek)
            return None

        sens_patterns = ("key", "secret", "password", "token", "client_secret")
        meta: Dict[str, Dict[str, Any]] = {}
        for k, v in db_settings.items():
            env_v = None if self._is_model_setting_key(str(k)) else _env_override_for_key(k)
            source = "environment" if env_v is not None else ("database" if v is not None else "default")
            sensitive = isinstance(k, str) and any(p in k.lower() for p in sens_patterns)
            editable = not sensitive and source != "environment"
            effective_val = env_v if env_v is not None else v
            has_value = effective_val not in (None, "")
            meta[k] = {
                "sensitive": bool(sensitive),
                "editable": bool(editable),
                "source": source,
                "has_value": bool(has_value),
            }
        return meta



# Module-level singleton
provider = ConfigProvider(ttl_seconds=60)
