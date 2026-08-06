from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.persistence.errors import RevisionConflict
from app.trading.alerts import (
    TradingAlert,
    TradingAlertCreate,
    TradingAlertEvaluation,
    TradingAlertTrigger,
    TradingAlertUpdate,
    alert_trigger_key,
    cooldown_elapsed,
    crossed_threshold,
)
from app.trading.alerts_api import create_trading_alert_router
from app.trading.alerts_monitor import TradingAlertMonitor, trading_alert_monitor_enabled


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


class FakeAlertRepository:
    def __init__(self) -> None:
        self.alerts: dict[str, TradingAlert] = {}
        self.triggers: list[TradingAlertTrigger] = []
        self.evaluations: list[TradingAlertEvaluation] = []

    def list_alerts(self, limit: int = 200):
        return list(self.alerts.values())[:limit]

    def create(self, request: TradingAlertCreate):
        alert = TradingAlert(
            **request.model_dump(),
            enabled=True,
            revision=1,
            created_at=NOW,
            updated_at=NOW,
        )
        self.alerts[alert.alert_id] = alert
        return alert

    def update(self, alert_id: str, request: TradingAlertUpdate, expected_revision: int):
        current = self.alerts[alert_id]
        if current.revision != expected_revision:
            raise RevisionConflict("stale alert")
        updated = current.model_copy(
            update={
                **request.model_dump(),
                "revision": current.revision + 1,
                "updated_at": NOW + timedelta(minutes=1),
            }
        )
        self.alerts[alert_id] = updated
        return updated

    def archive(self, alert_id: str, expected_revision: int):
        current = self.alerts[alert_id]
        if current.revision != expected_revision:
            raise RevisionConflict("stale alert")
        archived = current.model_copy(
            update={"enabled": False, "revision": current.revision + 1}
        )
        self.alerts[alert_id] = archived
        return archived

    def list_triggers(self, limit: int = 200):
        return self.triggers[:limit]

    def evaluate(self, evaluation: TradingAlertEvaluation):
        self.evaluations.append(evaluation)
        trigger = TradingAlertTrigger(
            trigger_id=f"trigger-{len(self.evaluations)}",
            alert_id="alert-1",
            instrument_id=evaluation.instrument_id,
            observed_price=evaluation.observed_price,
            threshold=Decimal("100"),
            condition_type="price_above",
            observed_at=evaluation.observed_at,
            idempotency_key=f"key-{len(self.evaluations)}",
            payload={},
        )
        self.triggers = [trigger, *self.triggers]
        return [trigger]


class FakeMarketService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def quote(self, instrument_id: str, binding_id: str | None = None):
        self.calls.append((instrument_id, binding_id))
        return {
            "instrument_id": instrument_id,
            "binding_id": binding_id or "default",
            "provider": "fixture",
            "price": "101",
            "received_at": NOW.isoformat(),
            "freshness_mode": "polled",
        }


def test_alert_migration_uses_dedicated_authority_tables() -> None:
    migration = Path(
        "src/app/persistence/migrations/0020_trading_alerts.sql"
    ).read_text()
    assert "CREATE TABLE IF NOT EXISTS omnix_trading_alerts" in migration
    assert "CREATE TABLE IF NOT EXISTS omnix_trading_alert_triggers" in migration
    assert "UNIQUE (workspace_id, idempotency_key)" in migration
    assert "omnix_module_records" not in migration


def test_price_alerts_trigger_only_on_threshold_crossings() -> None:
    assert crossed_threshold("price_above", Decimal("99"), Decimal("100"), Decimal("100"))
    assert not crossed_threshold("price_above", Decimal("100"), Decimal("101"), Decimal("100"))
    assert crossed_threshold("price_below", Decimal("101"), Decimal("100"), Decimal("100"))
    assert not crossed_threshold("price_below", Decimal("100"), Decimal("99"), Decimal("100"))
    assert not crossed_threshold("price_above", None, Decimal("101"), Decimal("100"))


def test_cooldown_and_idempotency_boundaries_are_deterministic() -> None:
    assert not cooldown_elapsed(NOW, NOW + timedelta(seconds=59), 60)
    assert cooldown_elapsed(NOW, NOW + timedelta(seconds=60), 60)
    first = alert_trigger_key("alert-1", NOW, Decimal("101.25"))
    assert first == alert_trigger_key("alert-1", NOW, Decimal("101.25"))
    assert first != alert_trigger_key("alert-1", NOW, Decimal("101.26"))


def test_alert_monitor_groups_targets_and_runs_without_browser() -> None:
    repository = FakeAlertRepository()
    repository.alerts = {
        alert_id: TradingAlert(
            alert_id=alert_id,
            instrument_id="crypto:BINANCE:spot:BTC-USDT",
            binding_id="binance:fixture",
            condition_type="price_above",
            threshold=Decimal("100"),
            enabled=True,
            cooldown_seconds=0,
            revision=1,
        )
        for alert_id in ("alert-1", "alert-2")
    }
    market = FakeMarketService()
    monitor = TradingAlertMonitor(
        repository_factory=lambda: repository,
        market_service_factory=lambda: market,
        interval_seconds=5,
    )

    assert asyncio.run(monitor.run_once()) == 1
    assert market.calls == [
        ("crypto:BINANCE:spot:BTC-USDT", "binance:fixture")
    ]
    assert len(repository.evaluations) == 1
    assert monitor.diagnostics()["evaluation_count"] == 1


def test_alert_monitor_is_disabled_in_legacy_tests_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.delenv("OMNIX_TRADING_ALERT_MONITOR_IN_TESTS", raising=False)
    assert trading_alert_monitor_enabled() is False


def test_alert_routes_support_revisioned_management_and_trigger_history() -> None:
    repository = FakeAlertRepository()
    app = FastAPI()
    app.include_router(create_trading_alert_router(repository_factory=lambda: repository))
    client = TestClient(app)

    created = client.post(
        "/api/trading/alerts",
        json={
            "alert_id": "alert-1",
            "instrument_id": "crypto:BINANCE:spot:BTC-USDT",
            "binding_id": None,
            "condition_type": "price_above",
            "threshold": "100",
            "cooldown_seconds": 60,
        },
    )
    assert created.status_code == 201
    assert created.json()["revision"] == 1

    listed = client.get("/api/trading/alerts")
    assert listed.status_code == 200
    assert [item["alert_id"] for item in listed.json()["alerts"]] == ["alert-1"]

    updated = client.put(
        "/api/trading/alerts/alert-1",
        headers={"If-Match": "1"},
        json={
            "instrument_id": "crypto:BINANCE:spot:BTC-USDT",
            "binding_id": None,
            "condition_type": "price_below",
            "threshold": "90",
            "enabled": True,
            "cooldown_seconds": 120,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2

    stale = client.put(
        "/api/trading/alerts/alert-1",
        headers={"If-Match": "1"},
        json={
            "instrument_id": "crypto:BINANCE:spot:BTC-USDT",
            "binding_id": None,
            "condition_type": "price_below",
            "threshold": "80",
            "enabled": True,
            "cooldown_seconds": 0,
        },
    )
    assert stale.status_code == 409

    evaluated = client.post(
        "/api/trading/alerts/evaluate",
        json={
            "instrument_id": "crypto:BINANCE:spot:BTC-USDT",
            "observed_price": "101",
            "observed_at": NOW.isoformat(),
        },
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["triggers"][0]["trigger_id"] == "trigger-1"
    assert client.get("/api/trading/alerts/triggers").json()["triggers"][0]["idempotency_key"] == "key-1"

    archived = client.delete(
        "/api/trading/alerts/alert-1",
        headers={"If-Match": "2"},
    )
    assert archived.status_code == 200
    assert archived.json()["enabled"] is False
