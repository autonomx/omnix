from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.trading.providers.alpaca_iex_status import AlpacaIexStatusMonitor
from app.trading.strategy_deep_recovery_monitor import TradingStrategyDeepRecoveryShadowMonitor
from app.trading.strategy_monitor import TradingStrategyMonitor
from app.trading.strategy_operations_api import create_trading_strategy_operations_router
from app.trading.strategy_universe_archive_monitor import TradingStrategyUniverseArchiveMonitor
from app.trading.strategy_v2_qualification_monitor import TradingStrategyV2QualificationMonitor


def test_strategy_operations_status_reports_registered_monitor_runtime_without_execution_authority(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_TRADING_STRATEGY_MONITOR_IN_TESTS", "0")
    monkeypatch.setenv("OMNIX_TRADING_DEEP_RECOVERY_SHADOW_MONITOR_IN_TESTS", "0")
    monkeypatch.setenv("OMNIX_TRADING_UNIVERSE_ARCHIVER_IN_TESTS", "0")
    monkeypatch.setenv("OMNIX_TRADING_V2_QUALIFICATION_IN_TESTS", "0")
    monkeypatch.setenv("OMNIX_ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("OMNIX_ALPACA_API_SECRET_KEY", "test-secret")

    app = FastAPI()
    app.state._omnix_trading_strategy_monitor = TradingStrategyMonitor(interval_seconds=17)
    app.state._omnix_trading_strategy_deep_recovery_shadow_monitor = TradingStrategyDeepRecoveryShadowMonitor(interval_seconds=23)
    app.state._omnix_trading_strategy_universe_archive_monitor = TradingStrategyUniverseArchiveMonitor(interval_seconds=19)
    app.state._omnix_trading_strategy_v2_qualification_monitor = TradingStrategyV2QualificationMonitor(interval_seconds=61)
    app.state._omnix_alpaca_iex_status_monitor = AlpacaIexStatusMonitor()
    app.include_router(create_trading_strategy_operations_router())

    response = TestClient(app).get("/api/trading/strategy-operations/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_authority"] is False
    assert payload["strategy_monitor"] == {
        "configured_enabled": False,
        "registered": True,
        "running": False,
        "interval_seconds": 17.0,
        "last_run_at": None,
        "last_error": None,
        "counters": {
            "evaluation_count": 0,
            "signal_count": 0,
            "paper_order_count": 0,
        },
    }
    assert payload["deep_recovery_shadow_monitor"] == {
        "configured_enabled": False,
        "registered": True,
        "running": False,
        "interval_seconds": 23.0,
        "last_run_at": None,
        "last_error": None,
        "counters": {
            "evaluation_count": 0,
            "signal_count": 0,
            "execution_observation_count": 0,
        },
    }
    assert payload["universe_archive_monitor"]["interval_seconds"] == 19.0
    assert payload["universe_archive_monitor"]["counters"] == {"archive_count": 0}
    assert payload["v2_qualification_monitor"]["interval_seconds"] == 61.0
    assert payload["v2_qualification_monitor"]["counters"] == {"replay_count": 0}
    assert payload["alpaca_status_monitor"] == {
        "configured_enabled": True,
        "registered": True,
        "running": False,
        "interval_seconds": None,
        "last_run_at": None,
        "last_error": None,
        "counters": {
            "reconnect_count": 0,
            "disconnect_count": 0,
            "known_halts": 0,
            "history_symbols": 0,
        },
    }


def test_strategy_operations_status_marks_missing_monitor_unregistered(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_TRADING_STRATEGY_MONITOR_IN_TESTS", "1")
    monkeypatch.setenv("OMNIX_TRADING_DEEP_RECOVERY_SHADOW_MONITOR_IN_TESTS", "1")
    monkeypatch.setenv("OMNIX_TRADING_UNIVERSE_ARCHIVER_IN_TESTS", "1")
    monkeypatch.setenv("OMNIX_TRADING_V2_QUALIFICATION_IN_TESTS", "1")
    monkeypatch.setenv("OMNIX_ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("OMNIX_ALPACA_API_SECRET_KEY", "test-secret")

    app = FastAPI()
    app.include_router(create_trading_strategy_operations_router())
    payload = TestClient(app).get("/api/trading/strategy-operations/status").json()

    for key in (
        "strategy_monitor",
        "deep_recovery_shadow_monitor",
        "universe_archive_monitor",
        "v2_qualification_monitor",
        "alpaca_status_monitor",
    ):
        assert payload[key]["configured_enabled"] is True
        assert payload[key]["registered"] is False
        assert payload[key]["running"] is False
