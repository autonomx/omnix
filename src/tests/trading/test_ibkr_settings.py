from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.trading.market_data_api import create_trading_market_data_router
from app.trading.ibkr_settings import load_ibkr_settings, save_ibkr_settings
from app.trading.providers.ibkr_runtime import IbkrRuntime


def test_saved_ibkr_settings_are_durable_and_drive_default_runtime(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(shared, "SETTINGS_FILE", str(settings_file))
    for name in (
        "OMNIX_IBKR_ENABLED",
        "OMNIX_IBKR_MONITOR",
        "OMNIX_IBKR_HOST",
        "OMNIX_IBKR_PORT",
        "OMNIX_IBKR_CLIENT_ID",
        "OMNIX_IBKR_LIVE_AUTHORITY",
        "OMNIX_IBKR_RECOVERY_AUTHORITY",
    ):
        monkeypatch.delenv(name, raising=False)

    saved = save_ibkr_settings(
        {
            "enabled": True,
            "monitor_enabled": False,
            "host": "192.168.1.50",
            "port": 4001,
            "client_id": 93,
        }
    )

    assert saved.enabled is True
    assert saved.host == "192.168.1.50"
    assert load_ibkr_settings()[1] == "omnix_settings"
    assert json.loads(settings_file.read_text(encoding="utf-8"))["trading_market_data"]["ibkr"] == {
        "enabled": True,
        "monitor_enabled": False,
        "host": "192.168.1.50",
        "port": 4001,
        "client_id": 93,
        "live_authority_enabled": False,
        "recovery_authority_enabled": False,
    }

    runtime = IbkrRuntime()
    diagnostics = runtime.diagnostics()
    assert diagnostics["settings_source"] == "omnix_settings"
    assert diagnostics["enabled"] is True
    assert diagnostics["monitor_enabled"] is False
    assert diagnostics["host"] == "192.168.1.50"
    assert diagnostics["port"] == 4001
    assert diagnostics["client_id"] == 93
    assert diagnostics["live_authority_enabled"] is False
    assert diagnostics["recovery_authority_enabled"] is False


def test_saved_settings_override_legacy_environment_configuration(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    monkeypatch.setattr(shared, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("OMNIX_IBKR_ENABLED", "1")
    monkeypatch.setenv("OMNIX_IBKR_HOST", "environment-host")
    save_ibkr_settings({"enabled": False, "host": "omnix-host"})

    settings, source = load_ibkr_settings()

    assert source == "omnix_settings"
    assert settings.enabled is False
    assert settings.host == "omnix-host"


def test_ibkr_settings_endpoint_returns_status_and_persists_update(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    monkeypatch.setattr(shared, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    app = FastAPI()
    app.include_router(create_trading_market_data_router())
    client = TestClient(app)

    initial = client.get("/api/trading/market-data/providers/ibkr/settings")
    assert initial.status_code == 200
    assert initial.json()["connection_status"] == "disabled"
    assert initial.json()["official_ibapi_available"] is True

    updated = client.put(
        "/api/trading/market-data/providers/ibkr/settings",
        json={"enabled": True, "port": 4001, "client_id": 94},
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["settings_source"] == "omnix_settings"
    assert payload["settings"]["enabled"] is True
    assert payload["settings"]["port"] == 4001
    assert payload["settings"]["client_id"] == 94
    assert payload["connection_status"] == "disconnected"
