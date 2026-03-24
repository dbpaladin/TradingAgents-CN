from tradingagents.dataflows.data_source_manager import ChinaDataSource, DataSourceManager


class _FakeCollection:
    def __init__(self, config):
        self._config = config

    def find_one(self, *args, **kwargs):
        return self._config


class _FakeDB:
    def __init__(self, config):
        self.system_configs = _FakeCollection(config)


def _build_config(tushare_enabled: bool = False):
    return {
        "is_active": True,
        "version": 1,
        "data_source_configs": [
            {
                "name": "AKShare",
                "type": "akshare",
                "enabled": True,
                "priority": 1,
                "market_categories": ["a_shares"],
            },
            {
                "name": "Tushare",
                "type": "tushare",
                "enabled": tushare_enabled,
                "priority": 2,
                "api_key": "your-tushare-token",
                "endpoint": "http://api.tushare.pro",
                "market_categories": ["a_shares"],
            },
        ],
    }


def test_custom_tushare_endpoint_overrides_disabled_db_flag(monkeypatch):
    config = _build_config(tushare_enabled=False)

    monkeypatch.setenv("TUSHARE_ENDPOINT", "http://118.25.178.42:5000")
    monkeypatch.setenv("TUSHARE_TOKEN", "third-party-token")
    monkeypatch.setattr(DataSourceManager, "_check_mongodb_enabled", lambda self: False)
    monkeypatch.setattr(
        "app.core.database.get_mongo_db_sync",
        lambda: _FakeDB(config),
    )

    manager = DataSourceManager()

    assert ChinaDataSource.TUSHARE in manager.available_sources
    assert manager._get_data_source_priority_order("600519")[0] == ChinaDataSource.TUSHARE


def test_official_tushare_endpoint_does_not_override_disabled_db_flag(monkeypatch):
    config = _build_config(tushare_enabled=False)

    monkeypatch.setenv("TUSHARE_ENDPOINT", "http://api.tushare.pro")
    monkeypatch.setenv("TUSHARE_TOKEN", "third-party-token")
    monkeypatch.setattr(DataSourceManager, "_check_mongodb_enabled", lambda self: False)
    monkeypatch.setattr(
        "app.core.database.get_mongo_db_sync",
        lambda: _FakeDB(config),
    )

    manager = DataSourceManager()

    assert ChinaDataSource.TUSHARE not in manager.available_sources
    assert ChinaDataSource.TUSHARE not in manager._get_data_source_priority_order("600519")
