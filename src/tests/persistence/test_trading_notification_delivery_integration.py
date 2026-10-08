"""The alert notification outbox against PostgreSQL (TVP-0.5a)."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.apps.trading.alerts import TradingAlertCreate, TradingAlertEvaluation, TradingAlertRepository
from app.apps.trading.alerts_delivery import (
    DeliveryResult,
    MAX_WEBHOOK_ATTEMPTS,
    NotificationDeliveryMonitor,
    NotificationDeliveryRepository,
    retry_delay_seconds,
)
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

CLOSE = {"kind": "price", "field": "close"}
# Far in the future, so these rows are the only ones due in the tests' clock and other tests' rows never are.
BASE = datetime(2090, 1, 1, tzinfo=timezone.utc)


@pytest.fixture()
def outbox():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-notification-delivery-tests",
        )
    )
    try:
        context = ensure_local_identity(database)

        def uow():
            return unit_of_work(database)

        alerts = TradingAlertRepository(context=context, uow_factory=uow)
        deliveries = NotificationDeliveryRepository(context=context, uow_factory=uow)
        suffix = uuid.uuid4().hex[:10].upper()
        instrument = f"crypto:BINANCE:spot:W{suffix}-USDT"
        env = SimpleNamespace(alerts=alerts, deliveries=deliveries, instrument=instrument, suffix=suffix, uow=uow, context=context)
        yield env
        with uow() as work:
            work.connection.execute(
                "DELETE FROM omnix_trading_notification_deliveries WHERE workspace_id = %s AND alert_id LIKE %s",
                (context.workspace_id, f"%-{suffix}"),
            )
            work.commit()
        for alert in alerts.list_alerts(500):
            if alert.instrument_id == instrument:
                alerts.archive(alert.alert_id, alert.revision)
    finally:
        database.close()


def _alert(env, name: str, *, channels: list[str], webhook_ref: str | None, message: str = ""):
    return env.alerts.create(
        TradingAlertCreate(
            alert_id=f"{name}-{env.suffix}",
            instrument_id=env.instrument,
            conditions=[{"source": CLOSE, "operator": "crossing_up", "target": {"kind": "value", "value": "100"}}],
            parameters={"notification_channels": channels, "message": message},
        ),
        webhook_ref=webhook_ref,
    )


def _trigger(env, minute: int = 0):
    """Pushes 99 then 101 (a crossing up) and returns the triggers."""
    observed = BASE - timedelta(days=1) + timedelta(minutes=minute)
    env.alerts.evaluate(TradingAlertEvaluation(instrument_id=env.instrument, observed_price=Decimal("99"), observed_at=observed))
    return env.alerts.evaluate(
        TradingAlertEvaluation(instrument_id=env.instrument, observed_price=Decimal("101"), observed_at=observed + timedelta(seconds=30))
    )


def _rows(env, alert_id: str):
    with env.uow() as work:
        return work.connection.execute(
            """
            SELECT delivery_id, trigger_id, channel, status, attempts, message, last_error, lease_expires_at
              FROM omnix_trading_notification_deliveries
             WHERE workspace_id = %s AND alert_id = %s
             ORDER BY created_at
            """,
            (env.context.workspace_id, alert_id),
        ).fetchall()


def _claim(env, now: datetime):
    return [item for item in env.deliveries.claim_due(now, limit=50) if item.alert_id.endswith(env.suffix)]


def test_a_trigger_enqueues_one_webhook_delivery_in_its_transaction(outbox) -> None:
    hooked = _alert(outbox, "hooked", channels=["app", "webhook"], webhook_ref="ref-1", message='{"text": "BTC up"}')
    _alert(outbox, "plain", channels=["app", "toast"], webhook_ref=None)
    _alert(outbox, "no-ref", channels=["webhook"], webhook_ref=None)
    triggers = _trigger(outbox)
    assert {trigger.alert_id for trigger in triggers} == {f"{name}-{outbox.suffix}" for name in ("hooked", "plain", "no-ref")}
    rows = _rows(outbox, hooked.alert_id)
    assert len(rows) == 1
    _, trigger_id, channel, status, attempts, message, _, _ = rows[0]
    assert (channel, status, attempts, message) == ("webhook", "pending", 0, '{"text": "BTC up"}')
    assert trigger_id == next(trigger.trigger_id for trigger in triggers if trigger.alert_id == hooked.alert_id)
    assert _rows(outbox, f"plain-{outbox.suffix}") == []
    assert _rows(outbox, f"no-ref-{outbox.suffix}") == []
    # The same observation again is the same trigger: no second delivery.
    _trigger(outbox)
    assert len(_rows(outbox, hooked.alert_id)) == 1


def test_claim_send_retry_and_deliver(outbox) -> None:
    hooked = _alert(outbox, "retry", channels=["webhook"], webhook_ref="ref-2")
    _trigger(outbox)
    [claimed] = _claim(outbox, BASE)
    assert (claimed.attempt, claimed.webhook_ref, claimed.channel) == (1, "ref-2", "webhook")
    assert claimed.message.endswith("triggered at 101")
    # Leased: a second pass doesn't take it.
    assert _claim(outbox, BASE) == []
    assert outbox.deliveries.record(claimed, DeliveryResult("retry", "http_503", 503), BASE) == "pending"
    [row] = _rows(outbox, hooked.alert_id)
    assert (row[3], row[4], row[6], row[7]) == ("pending", 1, "http_503", None)
    # Not before the backoff.
    assert _claim(outbox, BASE + timedelta(seconds=retry_delay_seconds(1) - 1)) == []
    [again] = _claim(outbox, BASE + timedelta(seconds=retry_delay_seconds(1)))
    assert again.attempt == 2
    assert outbox.deliveries.record(again, DeliveryResult("delivered", status_code=204), BASE) == "delivered"
    [listed] = outbox.deliveries.list_deliveries(alert_id=hooked.alert_id)
    assert (listed.status, listed.attempts, listed.last_error, listed.last_status_code) == ("delivered", 2, None, 204)
    assert listed.next_attempt_at is None
    assert "ref-2" not in listed.model_dump_json()


def test_an_expired_lease_is_claimed_again_and_the_stale_result_is_ignored(outbox) -> None:
    hooked = _alert(outbox, "lease", channels=["webhook"], webhook_ref="ref-3")
    _trigger(outbox)
    [first] = _claim(outbox, BASE)
    # The first sender stalls past its lease (a restart, say); the next pass sends again: at-least-once.
    [second] = _claim(outbox, BASE + timedelta(minutes=5))
    assert (first.delivery_id, second.attempt) == (second.delivery_id, 2)
    assert outbox.deliveries.record(first, DeliveryResult("delivered", status_code=200), BASE) is None
    assert outbox.deliveries.record(second, DeliveryResult("delivered", status_code=200), BASE) == "delivered"
    assert _rows(outbox, hooked.alert_id)[0][3] == "delivered"


def test_attempts_run_out_and_permanent_errors_fail_at_once(outbox) -> None:
    exhausted = _alert(outbox, "exhausted", channels=["webhook"], webhook_ref="ref-4")
    _trigger(outbox)
    now = BASE
    for attempt in range(1, MAX_WEBHOOK_ATTEMPTS + 1):
        [claimed] = _claim(outbox, now)
        assert claimed.attempt == attempt
        status = outbox.deliveries.record(claimed, DeliveryResult("retry", "timeout"), now)
        now += timedelta(seconds=retry_delay_seconds(attempt))
    assert status == "failed"
    [row] = _rows(outbox, exhausted.alert_id)
    assert (row[3], row[4], row[6]) == ("failed", MAX_WEBHOOK_ATTEMPTS, "timeout:attempts_exhausted")
    assert _claim(outbox, now + timedelta(days=1)) == []

    permanent = _alert(outbox, "permanent", channels=["webhook"], webhook_ref="ref-5")
    _trigger(outbox, minute=10)
    [claimed] = [item for item in _claim(outbox, BASE) if item.alert_id == permanent.alert_id]
    assert outbox.deliveries.record(claimed, DeliveryResult("failed", "http_404", 404), BASE) == "failed"


def test_the_monitor_sends_due_deliveries_and_records_them(outbox) -> None:
    hooked = _alert(outbox, "monitor", channels=["webhook"], webhook_ref="ref-6")
    _trigger(outbox)
    sent = []

    class Sender:
        def send(self, delivery):
            sent.append(delivery.delivery_id)
            return DeliveryResult("delivered", status_code=200)

    monitor = NotificationDeliveryMonitor(
        repository_factory=lambda: outbox.deliveries, senders={"webhook": Sender()}, clock=lambda: BASE
    )
    asyncio.run(monitor.run_once())
    [row] = _rows(outbox, hooked.alert_id)
    assert row[3] == "delivered"
    assert row[0] in sent


def test_the_outbox_enforces_row_level_security(outbox) -> None:
    # The generic probe in test_row_level_security.py checks isolation with a non-superuser role.
    with outbox.uow() as work:
        row = work.connection.execute(
            """
            SELECT relation.relrowsecurity, relation.relforcerowsecurity,
                   EXISTS (SELECT 1 FROM pg_policies WHERE tablename = relation.relname AND policyname = 'tenant_isolation')
              FROM pg_class AS relation
             WHERE relation.relname = 'omnix_trading_notification_deliveries'
            """
        ).fetchone()
    assert row == (True, True, True)
