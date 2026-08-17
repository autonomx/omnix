from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.persistence.errors import RevisionConflict
from app.trading.alerts import (
    TradingAlert,
    TradingAlertCreate,
    TradingAlertEvaluation,
    TradingAlertEvaluationPolicy,
    TradingAlertTrigger,
    TradingAlertUpdate,
    alert_condition_value,
    alert_trigger_key,
    cooldown_elapsed,
    crossed_threshold,
)
from app.trading.alerts_api import create_trading_alert_router
from app.trading.alerts_monitor import TradingAlertMonitor, trading_alert_monitor_enabled


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
INSTRUMENT = "crypto:BINANCE:spot:BTC-USDT"


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
        updated = TradingAlert.model_validate(
            {
                **current.model_dump(),
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
            alert_id="price-alert",
            instrument_id=evaluation.instrument_id,
            binding_id=evaluation.resolved_binding_id,
            provider=evaluation.provider,
            observed_value=evaluation.observed_price,
            observed_price=evaluation.observed_price,
            threshold=Decimal("100"),
            condition_type="price_above",
            observed_at=evaluation.observed_at,
            evaluated_at=evaluation.evaluated_at,
            idempotency_key=f"key-{len(self.evaluations)}",
            payload={
                "requested_binding_id": evaluation.binding_id,
                "resolved_binding_id": evaluation.resolved_binding_id,
            },
        )
        self.triggers = [trigger, *self.triggers]
        return [trigger]


class FakeMarketService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, str | None]] = []

    def bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int,
        binding_id: str | None = None,
    ):
        self.calls.append((instrument_id, interval, limit, binding_id))
        bars = [
            SimpleNamespace(
                close=Decimal(90 + index),
                high=Decimal(91 + index),
                low=Decimal(89 + index),
                volume=Decimal(1_000 + index),
                is_final=True,
                end_time=NOW + timedelta(minutes=index),
            )
            for index in range(40)
        ]
        return SimpleNamespace(
            bars=bars,
            binding=SimpleNamespace(
                binding_id="fixture:resolved",
                provider="fixture-provider",
            ),
        )


def alert(
    alert_id: str,
    condition_type: str,
    threshold: Decimal = Decimal("100"),
    **parameters,
) -> TradingAlert:
    return TradingAlert(
        alert_id=alert_id,
        instrument_id=INSTRUMENT,
        binding_id="fixture:requested",
        condition_type=condition_type,
        threshold=threshold,
        parameters=parameters,
        evaluation_policy={"interval": "1m", "allow_partial_bars": False},
        enabled=True,
        cooldown_seconds=0,
        revision=1,
    )


def test_alert_migration_uses_dedicated_complete_authority_tables() -> None:
    migration = Path("src/app/persistence/migrations/0020_trading_alerts.sql").read_text()
    trendline_migration = Path(
        "src/app/persistence/migrations/0036_trading_trendline_alerts.sql"
    ).read_text()
    assert "CREATE TABLE IF NOT EXISTS omnix_trading_alerts" in migration
    assert "CREATE TABLE IF NOT EXISTS omnix_trading_alert_triggers" in migration
    assert "percent_change_above" in migration
    assert "indicator_cross_below" in migration
    assert "volume_above" in migration
    assert "evaluation_policy JSONB" in migration
    assert "evaluated_at TIMESTAMPTZ" in migration
    assert "UNIQUE (workspace_id, idempotency_key)" in migration
    assert "omnix_module_records" not in migration
    assert "trendline_crossing_up" in trendline_migration
    assert "trendline_below" in trendline_migration


def test_all_alert_families_use_restart_safe_threshold_crossings() -> None:
    for condition_type in (
        "price_above",
        "percent_change_above",
        "indicator_above",
        "indicator_cross_above",
        "volume_above",
    ):
        assert crossed_threshold(
            condition_type,
            Decimal("99"),
            Decimal("100"),
            Decimal("100"),
        )
        assert not crossed_threshold(
            condition_type,
            None,
            Decimal("101"),
            Decimal("100"),
        )
    for condition_type in (
        "price_below",
        "percent_change_below",
        "indicator_below",
        "indicator_cross_below",
        "volume_below",
    ):
        assert crossed_threshold(
            condition_type,
            Decimal("101"),
            Decimal("100"),
            Decimal("100"),
        )


def test_condition_values_and_finalized_bar_policy_are_explicit() -> None:
    evaluation = TradingAlertEvaluation(
        instrument_id=INSTRUMENT,
        observed_price=Decimal("101"),
        observed_volume=Decimal("5000"),
        percent_changes={"percent": Decimal("2.5")},
        indicator_values={"indicator": Decimal("71")},
        is_final=False,
    )
    assert alert_condition_value(alert("price", "price_above"), evaluation) == 101
    assert alert_condition_value(alert("volume", "volume_above"), evaluation) == 5000
    assert alert_condition_value(alert("percent", "percent_change_above"), evaluation) == Decimal("2.5")
    assert alert_condition_value(
        alert("indicator", "indicator_cross_above", indicator_id="rsi"),
        evaluation,
    ) == 71
    assert TradingAlertEvaluationPolicy().allow_partial_bars is False
    assert TradingAlertEvaluationPolicy(allow_partial_bars=True).allow_partial_bars is True
    source = Path("src/app/trading/alerts.py").read_text()
    assert "not evaluation.is_final" in source
    assert "allow_partial_bars" in source


def test_trendline_alerts_compare_price_with_extrapolated_line() -> None:
    trendline = alert(
        "trendline",
        "trendline_crossing_up",
        threshold=Decimal("0"),
        trendline_points=[
            {"time": NOW.isoformat(), "price": "100"},
            {"time": (NOW + timedelta(minutes=10)).isoformat(), "price": "110"},
        ],
        trendline_mode="crossing_up",
    )
    evaluation = TradingAlertEvaluation(
        instrument_id=INSTRUMENT,
        observed_price=Decimal("116"),
        observed_at=NOW + timedelta(minutes=15),
    )
    assert alert_condition_value(trendline, evaluation) == Decimal("1")
    assert crossed_threshold("trendline_crossing_up", Decimal("-1"), Decimal("1"), Decimal("0"))
    assert not crossed_threshold("trendline_crossing_up", Decimal("1"), Decimal("2"), Decimal("0"))
    assert crossed_threshold("trendline_crossing", Decimal("1"), Decimal("-1"), Decimal("0"))


def test_cooldown_and_idempotency_boundaries_are_deterministic() -> None:
    assert not cooldown_elapsed(NOW, NOW + timedelta(seconds=59), 60)
    assert cooldown_elapsed(NOW, NOW + timedelta(seconds=60), 60)
    first = alert_trigger_key("alert-1", NOW, Decimal("101.25"), "price_above")
    assert first == alert_trigger_key("alert-1", NOW, Decimal("101.25"), "price_above")
    assert first != alert_trigger_key("alert-1", NOW, Decimal("101.25"), "volume_above")


def test_alert_monitor_groups_targets_and_calculates_all_condition_inputs() -> None:
    repository = FakeAlertRepository()
    repository.alerts = {
        item.alert_id: item
        for item in (
            alert("price-alert", "price_above"),
            alert("percent-alert", "percent_change_above", lookback_bars=5),
            alert("indicator-alert", "indicator_cross_above", indicator_id="rsi", period=14),
            alert("volume-alert", "volume_above"),
        )
    }
    market = FakeMarketService()
    monitor = TradingAlertMonitor(
        repository_factory=lambda: repository,
        market_service_factory=lambda: market,
        interval_seconds=5,
    )

    assert asyncio.run(monitor.run_once()) == 1
    assert len(market.calls) == 1
    assert market.calls[0][0:2] == (INSTRUMENT, "1m")
    evaluation = repository.evaluations[0]
    assert evaluation.binding_id == "fixture:requested"
    assert evaluation.resolved_binding_id == "fixture:resolved"
    assert evaluation.provider == "fixture-provider"
    assert evaluation.is_final is True
    assert evaluation.observed_volume == Decimal("1039")
    assert "percent-alert" in evaluation.percent_changes
    assert "indicator-alert" in evaluation.indicator_values
    assert monitor.diagnostics()["evaluation_count"] == 1


def test_alert_monitor_is_disabled_in_legacy_tests_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.delenv("OMNIX_TRADING_ALERT_MONITOR_IN_TESTS", raising=False)
    assert trading_alert_monitor_enabled() is False


def test_alert_routes_support_revisioned_policy_and_trigger_history() -> None:
    repository = FakeAlertRepository()
    app = FastAPI()
    app.include_router(create_trading_alert_router(repository_factory=lambda: repository))
    client = TestClient(app)

    created = client.post(
        "/api/trading/alerts",
        json={
            "alert_id": "alert-1",
            "instrument_id": INSTRUMENT,
            "binding_id": "fixture:requested",
            "condition_type": "indicator_cross_above",
            "threshold": "70",
            "parameters": {"indicator_id": "rsi", "period": 14},
            "evaluation_policy": {
                "interval": "5m",
                "allow_partial_bars": False,
                "formula_version": "omnix-indicators-v2",
            },
            "cooldown_seconds": 60,
        },
    )
    assert created.status_code == 201
    assert created.json()["parameters"]["indicator_id"] == "rsi"
    assert created.json()["evaluation_policy"]["interval"] == "5m"

    listed = client.get("/api/trading/alerts")
    assert listed.status_code == 200
    assert [item["alert_id"] for item in listed.json()["alerts"]] == ["alert-1"]

    current = created.json()
    updated = client.put(
        "/api/trading/alerts/alert-1",
        headers={"If-Match": "1"},
        json={
            "instrument_id": INSTRUMENT,
            "binding_id": "fixture:requested",
            "condition_type": "percent_change_below",
            "threshold": "-5",
            "parameters": {"lookback_bars": 10},
            "evaluation_policy": current["evaluation_policy"],
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
            "instrument_id": INSTRUMENT,
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
            "instrument_id": INSTRUMENT,
            "binding_id": "fixture:requested",
            "resolved_binding_id": "fixture:resolved",
            "provider": "fixture-provider",
            "interval": "5m",
            "observed_price": "101",
            "observed_volume": "5000",
            "observed_at": NOW.isoformat(),
            "evaluated_at": (NOW + timedelta(seconds=1)).isoformat(),
        },
    )
    assert evaluated.status_code == 200
    trigger = evaluated.json()["triggers"][0]
    assert trigger["binding_id"] == "fixture:resolved"
    assert trigger["provider"] == "fixture-provider"
    assert trigger["evaluated_at"]
    assert client.get("/api/trading/alerts/triggers").json()["triggers"][0]["idempotency_key"] == "key-1"

    archived = client.delete(
        "/api/trading/alerts/alert-1",
        headers={"If-Match": "2"},
    )
    assert archived.status_code == 200
    assert archived.json()["enabled"] is False
