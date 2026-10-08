"""Alert conditions, frequencies and channels against PostgreSQL (TVP-1.1, TVP-1.2)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.apps.trading.alert_conditions import legacy_conditions
from app.apps.trading.alerts import (
    TradingAlertCreate,
    TradingAlertEvaluation,
    TradingAlertParameters,
    TradingAlertRepository,
    TradingAlertUpdate,
)
from app.apps.trading.alerts_api import create_trading_alert_router
from app.apps.trading.alerts_channels import ProtectedAlertSecretStore
from app.apps.trading.alerts_monitor import TradingAlertMonitor
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

MIGRATION = Path("src/app/apps/trading/migrations/0141_trading_alert_conditions.sql")
CLOSE = {"kind": "price", "field": "close"}


@pytest.fixture()
def alerts():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-alert-condition-tests",
        )
    )
    try:
        context = ensure_local_identity(database)

        def uow():
            return unit_of_work(database)

        repository = TradingAlertRepository(context=context, uow_factory=uow)
        suffix = uuid.uuid4().hex[:10].upper()
        instrument = f"crypto:BINANCE:spot:T{suffix}-USDT"
        yield SimpleNamespace(repository=repository, instrument=instrument, uow=uow, context=context, suffix=suffix)
        for alert in repository.list_alerts(500):
            if alert.instrument_id == instrument:
                repository.archive(alert.alert_id, alert.revision)
    finally:
        database.close()


def _create(env, alert_id: str, **data):
    data.setdefault("conditions", [{"source": CLOSE, "operator": "crossing_up", "target": {"kind": "value", "value": "100"}}])
    return env.repository.create(TradingAlertCreate(alert_id=f"{alert_id}-{env.suffix}", instrument_id=env.instrument, **data))


def _alert(env, alert_id: str):
    return next(alert for alert in env.repository.list_alerts(500) if alert.alert_id == f"{alert_id}-{env.suffix}")


def _child_rows(env, alert_id: str):
    with env.uow() as uow:
        return uow.connection.execute(
            "SELECT position, source, operator, target FROM omnix_trading_alert_conditions"
            " WHERE workspace_id = %s AND alert_id = %s ORDER BY position",
            (env.context.workspace_id, alert_id),
        ).fetchall()


class Market:
    """Bars whose times lie after the alerts were created, so none of them is history."""

    def __init__(self) -> None:
        self.base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=1)
        self.bars: list[SimpleNamespace] = []

    def set(self, closes, forming=None) -> None:
        values = [(close, True) for close in closes] + ([(forming, False)] if forming is not None else [])
        self.bars = [
            SimpleNamespace(
                start_time=self.base + timedelta(minutes=index),
                end_time=self.base + timedelta(minutes=index + 1),
                open=Decimal(str(close)), high=Decimal(str(close)), low=Decimal(str(close)), close=Decimal(str(close)),
                volume=Decimal("10"), is_final=final,
            )
            for index, (close, final) in enumerate(values)
        ]

    def bars_for(self, *args, **kwargs):
        return SimpleNamespace(bars=list(self.bars), binding=SimpleNamespace(binding_id="fixture:resolved", provider="fixture"))


def _run(env, market: Market, repository=None) -> list[str]:
    target = repository or env.repository
    service = SimpleNamespace(bars=market.bars_for)
    monitor = TradingAlertMonitor(repository_factory=lambda: target, market_service_factory=lambda: service, interval_seconds=5)
    before = {trigger.trigger_id for trigger in env.repository.list_triggers(500)}
    asyncio.run(monitor.run_once())
    assert monitor.last_error is None
    return sorted(
        trigger.alert_id.removesuffix(f"-{env.suffix}")
        for trigger in env.repository.list_triggers(500)
        if trigger.trigger_id not in before and trigger.instrument_id == env.instrument
    )


PARTIAL = {"interval": "1m", "allow_partial_bars": True}


def test_conditions_round_trip_update_and_cascade(alerts) -> None:
    sma = {"kind": "indicator", "indicator_id": "sma", "inputs": {"period": 3}, "output": "sma:3"}
    created = _create(
        alerts,
        "round-trip",
        frequency="once_per_bar_close",
        conditions=[
            {"source": CLOSE, "operator": "crossing_up", "target": {"kind": "source", "source": sma}},
            {"source": {"kind": "change_percent", "lookback_bars": 2}, "operator": "moving_up", "amount": "1.5", "bars": 3},
            {"source": CLOSE, "operator": "inside_channel", "target": {"kind": "channel", "upper": {"kind": "value", "value": "120"}, "lower": {"kind": "source", "source": sma}}},
        ],
    )
    listed = _alert(alerts, "round-trip")
    assert listed.condition_type == "conditions" and listed.threshold == 0
    assert listed.frequency == "once_per_bar_close" and listed.parameters.trigger_policy == "once_per_bar_close"
    assert listed.conditions == created.conditions
    assert [row[2] for row in _child_rows(alerts, created.alert_id)] == ["crossing_up", "moving_up", "inside_channel"]

    updated = alerts.repository.update(
        created.alert_id,
        TradingAlertUpdate(instrument_id=alerts.instrument, conditions=[{"source": CLOSE, "operator": "less_than", "target": {"kind": "value", "value": "5"}}]),
        expected_revision=created.revision,
    )
    assert updated.frequency == "every_time"
    assert _alert(alerts, "round-trip").conditions == updated.conditions
    assert [row[2] for row in _child_rows(alerts, created.alert_id)] == ["less_than"]

    alerts.repository.archive(created.alert_id, updated.revision)
    assert _child_rows(alerts, created.alert_id) == []


def test_legacy_requests_store_their_derived_condition(alerts) -> None:
    created = _create(alerts, "legacy", conditions=[], condition_type="indicator_cross_below", threshold="30", parameters={"indicator_id": "rsi", "period": 9, "trigger_policy": "once"})
    assert created.frequency == "once"
    rows = _child_rows(alerts, created.alert_id)
    assert len(rows) == 1
    assert rows[0][1]["output"] == "rsi:9" and rows[0][2] == "crossing_down"
    assert _alert(alerts, "legacy").conditions == created.conditions


def test_once_per_bar_close_waits_for_the_close_and_fires_once(alerts) -> None:
    market = Market()
    _create(alerts, "close", frequency="once_per_bar_close", evaluation_policy=PARTIAL)
    _create(alerts, "per-bar", frequency="once_per_bar", evaluation_policy=PARTIAL)
    _create(alerts, "every", frequency="every_time", evaluation_policy=PARTIAL)

    market.set([98, 99], forming=101)  # true intrabar
    assert _run(alerts, market) == ["every", "per-bar"]
    market.set([98, 99], forming=102)  # same bar, new value
    assert _run(alerts, market) == ["every"]
    market.set([98, 99, 99.5], forming=100)  # the bar closed below: no close alert
    assert _run(alerts, market) == ["every", "per-bar"]
    market.set([98, 99, 99.5, 101], forming=101.5)  # this bar closed above
    assert _run(alerts, market) == ["close"]
    assert _run(alerts, market) == []
    # A restarted monitor with a fresh repository does not trigger again.
    restarted = TradingAlertRepository(context=alerts.context, uow_factory=alerts.uow)
    assert _run(alerts, market, restarted) == []
    close_alert = _alert(alerts, "close")
    assert close_alert.last_observed_value == Decimal("101")  # evaluation state is kept
    assert close_alert.last_triggered_at is not None


def test_once_disables_the_alert_in_the_same_transaction(alerts) -> None:
    market = Market()
    _create(alerts, "once", frequency="once", cooldown_seconds=0)
    market.set([99, 101])
    assert _run(alerts, market) == ["once"]
    alert = _alert(alerts, "once")
    assert alert.enabled is False and alert.last_triggered_at is not None
    market.set([99, 101, 99, 102])
    assert _run(alerts, market) == []
    # Re-enabling is a new revision, so it may fire once more.
    enabled = alerts.repository.update(
        alert.alert_id,
        TradingAlertUpdate(**alert.model_dump(include=set(TradingAlertUpdate.model_fields) - {"enabled", "webhook_secret"}), enabled=True),
        expected_revision=alert.revision,
    )
    assert enabled.last_triggered_at == alert.last_triggered_at  # lifecycle edit keeps history
    market.base += timedelta(minutes=10)
    market.set([99, 103])
    assert _run(alerts, market) == ["once"]


def test_once_per_minute_rate_limit(alerts) -> None:
    market = Market()
    created = _create(
        alerts,
        "minute",
        frequency="once_per_minute",
        evaluation_policy=PARTIAL,
        conditions=[{"source": CLOSE, "operator": "greater_than", "target": {"kind": "value", "value": "100"}}],
    )
    market.set([99], forming=101)
    assert _run(alerts, market) == ["minute"]
    market.set([99], forming=102)
    assert _run(alerts, market) == []
    with alerts.uow() as uow:
        uow.connection.execute(
            "UPDATE omnix_trading_alerts SET last_triggered_at = last_triggered_at - INTERVAL '61 seconds'"
            " WHERE workspace_id = %s AND alert_id = %s",
            (alerts.context.workspace_id, created.alert_id),
        )
        uow.commit()
    assert _run(alerts, market) == ["minute"]


def test_bars_closed_before_the_alert_existed_are_history(alerts) -> None:
    market = Market()
    _create(alerts, "stale")
    market.base -= timedelta(hours=1)
    market.set([99, 101])
    assert _run(alerts, market) == []
    market.base += timedelta(hours=2)
    market.set([99, 101])
    assert _run(alerts, market) == ["stale"]


def test_trigger_payload_lists_each_condition(alerts) -> None:
    market = Market()
    _create(
        alerts,
        "payload",
        conditions=[
            {"source": CLOSE, "operator": "crossing_up", "target": {"kind": "value", "value": "100"}},
            {"source": {"kind": "price", "field": "volume"}, "operator": "greater_than", "target": {"kind": "value", "value": "5"}},
        ],
    )
    market.set([99, 101])
    assert _run(alerts, market) == ["payload"]
    trigger = next(t for t in alerts.repository.list_triggers(500) if t.instrument_id == alerts.instrument)
    assert trigger.condition_type == "conditions"
    assert trigger.observed_value == Decimal("101") and trigger.threshold == 0
    assert [(item["source"], item.get("target")) for item in trigger.payload["observations"]] == [("101", "100"), ("10", "5")]
    assert trigger.payload["frequency"] == "every_time" and trigger.payload["bar_is_final"] is True


def test_pushed_prices_evaluate_price_alerts_only(alerts) -> None:
    price = _create(alerts, "push", conditions=[], condition_type="price_above", threshold="100")
    _create(alerts, "push-rsi", conditions=[], condition_type="indicator_above", threshold="50", parameters={"indicator_id": "rsi"})
    now = datetime.now(timezone.utc) + timedelta(minutes=1)

    def push(value: str, minute: int):
        return alerts.repository.evaluate(
            TradingAlertEvaluation(instrument_id=alerts.instrument, observed_price=Decimal(value), observed_at=now + timedelta(minutes=minute))
        )

    assert push("99", 0) == []
    triggers = push("101", 1)
    assert [trigger.alert_id for trigger in triggers] == [price.alert_id]
    assert push("101", 1) == []  # same observation: idempotent
    assert _alert(alerts, "push-rsi").last_observed_value is None


def test_pushed_prices_skip_per_bar_frequencies(alerts) -> None:
    for frequency in ("once_per_bar", "once_per_bar_close"):
        _create(alerts, frequency, frequency=frequency)
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    for minute, price in enumerate(("99", "101")):
        assert alerts.repository.evaluate(
            TradingAlertEvaluation(instrument_id=alerts.instrument, observed_price=Decimal(price), observed_at=now + timedelta(minutes=minute))
        ) == []
    assert _alert(alerts, "once_per_bar").last_observed_value is None


def test_migration_backfills_legacy_alerts(alerts) -> None:
    points = [{"time": "2026-08-05T12:00:00+00:00", "price": "100"}, {"time": "2026-08-05T13:00:00+00:00", "price": "110"}]
    legacy = {
        "price_above": ({}, "101.5"),
        "price_below": ({}, "99"),
        "percent_change_above": ({"lookback_bars": 3}, "2"),
        "percent_change_below": ({"lookback_bars": 1}, "-2"),
        "volume_above": ({}, "1000"),
        "volume_below": ({}, "10"),
        "indicator_above": ({"indicator_id": "bollinger", "period": 20, "component": "lower"}, "1"),
        "indicator_below": ({"indicator_id": "macd", "fast_period": 5, "slow_period": 13, "signal_period": 4, "component": "signal"}, "0"),
        "indicator_cross_above": ({"indicator_id": "stochastic-rsi", "period": 14, "fast_period": 3, "signal_period": 3}, "80"),
        "indicator_cross_below": ({"indicator_id": "vwap", "anchor_bars_ago": 5}, "50"),
        "trendline_crossing": ({"trendline_points": points}, "0"),
        "trendline_crossing_up": ({"trendline_points": points}, "0"),
        "trendline_crossing_down": ({"trendline_points": points}, "0"),
        "trendline_above": ({"trendline_points": points}, "0"),
        "trendline_below": ({"trendline_points": points}, "0"),
    }
    policies = {"price_above": "once", "price_below": "once_per_bar", "volume_above": "every_time"}
    workspace = alerts.context.workspace_id
    with alerts.uow() as uow:
        connection = uow.connection
        for index, (condition_type, (parameters, threshold)) in enumerate(legacy.items()):
            stored = TradingAlertParameters(**parameters, trigger_policy=policies.get(condition_type, "every_time"))
            connection.execute(
                "INSERT INTO omnix_trading_alerts (workspace_id, alert_id, instrument_id, condition_type, threshold,"
                " condition_parameters, cooldown_seconds, last_triggered_at)"
                " VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
                (
                    workspace, f"legacy-{index}-{alerts.suffix}", alerts.instrument, condition_type, Decimal(threshold),
                    stored.model_dump_json(), 31_536_000 if condition_type == "price_above" else 60,
                    datetime.now(timezone.utc) if condition_type == "price_above" else None,
                ),
            )
        connection.execute("DELETE FROM omnix_trading_alert_conditions WHERE workspace_id = %s AND alert_id LIKE %s", (workspace, f"legacy-%-{alerts.suffix}"))
        connection.execute(MIGRATION.read_text(encoding="utf-8"))
        connection.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent
        rows = connection.execute(
            "SELECT alert_id, frequency, cooldown_seconds, enabled, condition_parameters, notification_settings,"
            " evaluation_policy FROM omnix_trading_alerts WHERE workspace_id = %s AND alert_id LIKE %s",
            (workspace, f"legacy-%-{alerts.suffix}"),
        ).fetchall()
        stored_rows = {str(row[0]): row for row in rows}
        for index, (condition_type, (parameters, threshold)) in enumerate(legacy.items()):
            alert_id = f"legacy-{index}-{alerts.suffix}"
            children = connection.execute(
                "SELECT position, source, operator, target, amount, bars FROM omnix_trading_alert_conditions"
                " WHERE workspace_id = %s AND alert_id = %s",
                (workspace, alert_id),
            ).fetchall()
            assert len(children) == 1, condition_type
            from app.apps.trading.alert_conditions import AlertConditionSpec

            stored_condition = AlertConditionSpec.model_validate(
                {"source": children[0][1], "operator": children[0][2], "target": children[0][3]}
            )
            expected = legacy_conditions(condition_type, Decimal(threshold), TradingAlertParameters(**parameters))
            assert [stored_condition] == expected, condition_type
        assert stored_rows[f"legacy-0-{alerts.suffix}"][1:4] == ("once", 0, False)  # already fired: stays stopped
        assert stored_rows[f"legacy-1-{alerts.suffix}"][1:4] == ("once_per_bar", 0, True)
        assert stored_rows[f"legacy-4-{alerts.suffix}"][1:4] == ("every_time", 60, True)
        for row in stored_rows.values():
            # Notification settings moved out of condition_parameters; intrabar evaluation follows the frequency.
            assert not {"message", "notification_channels", "delivery"} & set(row[4])
            assert row[5]["notification_channels"] == ["app", "toast"] and row[5]["message"] == ""
            assert row[6]["allow_partial_bars"] is (row[1] != "once_per_bar_close")
        uow.rollback()


class MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def save(self, workspace_id, alert_id, secret) -> None:
        if secret:
            self.values[(workspace_id, alert_id)] = secret
        else:
            self.values.pop((workspace_id, alert_id), None)

    def has(self, workspace_id, alert_id) -> bool:
        return (workspace_id, alert_id) in self.values

    def available(self) -> bool:
        return True


def _client(env, secrets):
    from app.errors import install_error_envelope

    app = FastAPI()
    install_error_envelope(app)
    app.include_router(create_trading_alert_router(repository_factory=lambda: env.repository, secret_store=secrets))
    return TestClient(app)


def test_api_rejects_unavailable_channels_and_never_returns_the_webhook_secret(alerts) -> None:
    secrets = MemorySecrets()
    client = _client(alerts, secrets)
    alert_id = f"api-{alerts.suffix}"
    key = (alerts.context.workspace_id, alert_id)
    body = {
        "alert_id": alert_id,
        "instrument_id": alerts.instrument,
        "conditions": [{"source": CLOSE, "operator": "greater_than", "target": {"kind": "value", "value": "1"}}],
        "parameters": {"notification_channels": ["app", "webhook"]},
    }
    rejected = client.post("/api/trading/alerts", json=body)
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "alert channel webhook is not available yet"
    for channel in ("email", "push"):
        assert client.post("/api/trading/alerts", json={**body, "parameters": {"notification_channels": [channel]}}).status_code == 422

    body["parameters"] = {
        "notification_channels": ["app", "sound"],
        "delivery": {"webhook": {"url": "https://hooks.example.com/a", "has_secret": False}, "sound": {"name": "chime"}},
    }
    created = client.post("/api/trading/alerts", json={**body, "webhook_secret": "very-secret-value"})
    assert created.status_code == 201, created.text
    assert "very-secret-value" not in created.text and "webhook_secret" not in created.text
    assert created.json()["parameters"]["delivery"]["webhook"]["has_secret"] is True
    assert secrets.values[key] == "very-secret-value"
    with alerts.uow() as uow:
        stored = uow.connection.execute(
            "SELECT condition_parameters::text || notification_settings::text FROM omnix_trading_alerts"
            " WHERE workspace_id = %s AND alert_id = %s",
            (alerts.context.workspace_id, alert_id),
        ).fetchone()[0]
    assert "very-secret-value" not in stored and "hooks.example.com" in stored
    assert "very-secret-value" not in client.get("/api/trading/alerts").text

    # Reusing the alert id fails without touching the stored secret.
    duplicate = client.post("/api/trading/alerts", json={**body, "webhook_secret": "other-secret"})
    assert duplicate.status_code == 409
    assert secrets.values[key] == "very-secret-value"

    # An update without a secret keeps it.
    update = {name: value for name, value in body.items() if name != "alert_id"}
    kept = client.put(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "1"}, json=update)
    assert kept.status_code == 200 and kept.json()["parameters"]["delivery"]["webhook"]["has_secret"] is True
    # A stale update fails without touching the secret.
    stale = client.put(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "1"}, json={**update, "webhook_secret": "stale-secret"})
    assert stale.status_code == 409
    assert secrets.values[key] == "very-secret-value"
    cleared = client.put(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "2"}, json={**update, "webhook_secret": ""})
    assert cleared.json()["parameters"]["delivery"]["webhook"]["has_secret"] is False
    assert secrets.values == {}
    # A client cannot claim a secret: the stored flag decides.
    claim = {**update, "parameters": {**update["parameters"], "delivery": {"webhook": {"url": "https://hooks.example.com/a", "has_secret": True}}}}
    claimed = client.put(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "3"}, json=claim)
    assert claimed.json()["parameters"]["delivery"]["webhook"]["has_secret"] is False
    replaced = client.put(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "4"}, json={**update, "webhook_secret": "new-secret"})
    assert replaced.json()["parameters"]["delivery"]["webhook"]["has_secret"] is True
    # Removing the webhook removes its secret.
    removed = client.put(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "5"}, json={**update, "parameters": {"notification_channels": ["app"]}})
    assert removed.status_code == 200 and secrets.values == {}
    again = client.put(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "6"}, json={**update, "webhook_secret": "last"})
    assert again.status_code == 200 and secrets.values[key] == "last"
    assert client.delete(f"/api/trading/alerts/{alert_id}", headers={"If-Match": "7"}).status_code == 200
    assert secrets.values == {}

    no_webhook = client.post("/api/trading/alerts", json={**body, "parameters": {}, "webhook_secret": "x"})
    assert no_webhook.status_code == 422


def test_validation_errors_never_echo_the_webhook_secret(alerts) -> None:
    client = _client(alerts, MemorySecrets())
    base = {
        "alert_id": f"leak-{alerts.suffix}",
        "instrument_id": alerts.instrument,
        "parameters": {"delivery": {"webhook": {"url": "https://hooks.example.com/a"}}},
        "webhook_secret": "leaky-secret-value",
    }
    for body in (
        {**base, "conditions": []},  # model-level error: the whole body is the input
        {**base, "conditions": [{"source": CLOSE, "operator": "inside_channel", "target": {"kind": "value", "value": "1"}}]},
        {**base, "condition_type": "conditions", "threshold": "5"},
        {**base, "webhook_secret": "leaky-secret-value" * 40},  # field error on the secret itself
        {**base, "parameters": {"delivery": {"webhook": {"url": "file:///etc/passwd"}}}},
    ):
        response = client.post("/api/trading/alerts", json=body)
        assert response.status_code == 422, response.text
        assert "leaky-secret-value" not in response.text
    update = {name: value for name, value in base.items() if name != "alert_id"}
    put = client.put(f"/api/trading/alerts/{base['alert_id']}", headers={"If-Match": "1"}, json=update)
    assert put.status_code == 422 and "leaky-secret-value" not in put.text


def test_editing_notification_settings_keeps_trigger_state(alerts) -> None:
    market = Market()
    created = _create(
        alerts, "notify", frequency="once_per_minute",
        conditions=[{"source": CLOSE, "operator": "greater_than", "target": {"kind": "value", "value": "100"}}],
    )
    market.set([99], forming=101)
    assert _run(alerts, market) == ["notify"]
    fired = _alert(alerts, "notify")
    fields = set(TradingAlertUpdate.model_fields) - {"webhook_secret"}
    update = TradingAlertUpdate(**{
        **fired.model_dump(include=fields),
        "parameters": {
            **fired.parameters.model_dump(),
            "message": "new text",
            "notification_channels": ["app", "sound"],
            "delivery": {"sound": {"name": "bell"}},
        },
    })
    edited = alerts.repository.update(created.alert_id, update, expected_revision=fired.revision)
    assert edited.parameters.message == "new text"
    assert _alert(alerts, "notify").last_triggered_at == fired.last_triggered_at
    market.set([99], forming=102)
    assert _run(alerts, market) == []  # still inside the minute
    # A condition change starts a new history.
    changed = TradingAlertUpdate(**{
        **edited.model_dump(include=fields),
        "conditions": [{"source": CLOSE, "operator": "greater_than", "target": {"kind": "value", "value": "101"}}],
    })
    alerts.repository.update(created.alert_id, changed, expected_revision=edited.revision)
    assert _alert(alerts, "notify").last_triggered_at is None


def test_unreadable_rows_do_not_break_listing_or_the_monitor(alerts) -> None:
    market = Market()
    _create(alerts, "healthy")
    workspace = alerts.context.workspace_id
    with alerts.uow() as uow:
        for alert_id, condition_type, notification in (
            # Breaks today's write rules but reads: a blocked webhook URL, a legacy indicator without an id.
            (f"blocked-url-{alerts.suffix}", "price_above", {"delivery": {"webhook": {"url": "http://169.254.169.254/"}}}),
            (f"no-indicator-{alerts.suffix}", "indicator_above", {}),
            # Cannot be read at all.
            (f"broken-{alerts.suffix}", "price_above", {"notification_channels": ["fax"]}),
        ):
            uow.connection.execute(
                "INSERT INTO omnix_trading_alerts (workspace_id, alert_id, instrument_id, condition_type, threshold,"
                " notification_settings) VALUES (%s, %s, %s, %s, 100, %s::jsonb)",
                (workspace, alert_id, alerts.instrument, condition_type, json.dumps(notification)),
            )
        uow.commit()
    try:
        listed = {alert.alert_id for alert in alerts.repository.list_alerts(500) if alert.instrument_id == alerts.instrument}
        assert listed == {f"healthy-{alerts.suffix}", f"blocked-url-{alerts.suffix}", f"no-indicator-{alerts.suffix}"}
        market.set([99, 101])
        assert _run(alerts, market) == ["blocked-url", "healthy"]
    finally:
        with alerts.uow() as uow:
            uow.connection.execute(
                "DELETE FROM omnix_trading_alerts WHERE workspace_id = %s AND alert_id = %s",
                (workspace, f"broken-{alerts.suffix}"),
            )
            uow.commit()


def test_migrated_legacy_alerts_ignore_bars_closed_before_the_migration(alerts) -> None:
    market = Market()
    workspace = alerts.context.workspace_id
    alert_id = f"stale-legacy-{alerts.suffix}"
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    with alerts.uow() as uow:
        uow.connection.execute(
            "INSERT INTO omnix_trading_alerts (workspace_id, alert_id, instrument_id, condition_type, threshold,"
            " condition_parameters, created_at, updated_at)"
            " VALUES (%s, %s, %s, 'price_above', 100, %s::jsonb, %s, %s)",
            (workspace, alert_id, alerts.instrument, json.dumps({"message": "old", "trigger_policy": "every_time"}), month_ago, month_ago),
        )
        uow.connection.execute(MIGRATION.read_text(encoding="utf-8"))
        uow.commit()
    alert = next(item for item in alerts.repository.list_alerts(500) if item.alert_id == alert_id)
    assert alert.updated_at > month_ago + timedelta(days=29)
    assert alert.parameters.message == "old" and alert.evaluation_policy.allow_partial_bars is True
    # Bars that closed after the alert's old updated_at but before the migration are history.
    market.base = datetime.now(timezone.utc) - timedelta(hours=2)
    market.set([99, 101])
    assert _run(alerts, market) == []
    market.base = datetime.now(timezone.utc) + timedelta(minutes=1)
    market.set([99, 101])
    assert _run(alerts, market) == ["stale-legacy"]


@pytest.mark.skipif(sys.platform != "win32", reason="the protected store needs DPAPI")
def test_protected_secret_store_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(tmp_path / "secrets.dpapi"))
    store = ProtectedAlertSecretStore()
    assert not store.has("w", "a")
    store.save("w", "a", "s3cret")
    assert store.has("w", "a") and not store.has("w", "b")
    assert b"s3cret" not in (tmp_path / "secrets.dpapi").read_bytes()
    store.save("w", "a", None)
    assert not store.has("w", "a")
