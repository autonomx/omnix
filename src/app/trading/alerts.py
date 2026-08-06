from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict
from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work


AlertCondition = Literal["price_above", "price_below"]


class TradingAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alert_id: str
    instrument_id: str
    binding_id: str | None = None
    condition_type: AlertCondition
    threshold: Decimal
    enabled: bool = True
    cooldown_seconds: int = Field(default=0, ge=0)
    last_observed_price: Decimal | None = None
    last_triggered_at: datetime | None = None
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TradingAlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alert_id: str = Field(min_length=1, max_length=200)
    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    condition_type: AlertCondition
    threshold: Decimal
    cooldown_seconds: int = Field(default=0, ge=0, le=31_536_000)


class TradingAlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    condition_type: AlertCondition
    threshold: Decimal
    enabled: bool = True
    cooldown_seconds: int = Field(default=0, ge=0, le=31_536_000)


class TradingAlertEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: str
    observed_price: Decimal
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TradingAlertTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger_id: str
    alert_id: str
    instrument_id: str
    observed_price: Decimal
    threshold: Decimal
    condition_type: AlertCondition
    observed_at: datetime
    idempotency_key: str
    payload: dict[str, object] = Field(default_factory=dict)


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


def crossed_threshold(
    condition_type: AlertCondition,
    previous_price: Decimal | None,
    observed_price: Decimal,
    threshold: Decimal,
) -> bool:
    if previous_price is None:
        return False
    if condition_type == "price_above":
        return previous_price < threshold <= observed_price
    return previous_price > threshold >= observed_price


def cooldown_elapsed(
    last_triggered_at: datetime | None,
    observed_at: datetime,
    cooldown_seconds: int,
) -> bool:
    if last_triggered_at is None or cooldown_seconds <= 0:
        return True
    return observed_at >= last_triggered_at + timedelta(seconds=cooldown_seconds)


def alert_trigger_key(alert_id: str, observed_at: datetime, observed_price: Decimal) -> str:
    raw = f"{alert_id}|{observed_at.astimezone(timezone.utc).isoformat()}|{observed_price}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _alert(row) -> TradingAlert:
    return TradingAlert(
        alert_id=str(row[0]),
        instrument_id=str(row[1]),
        binding_id=str(row[2]) if row[2] is not None else None,
        condition_type=str(row[3]),
        threshold=Decimal(row[4]),
        enabled=bool(row[5]),
        cooldown_seconds=int(row[6]),
        last_observed_price=Decimal(row[7]) if row[7] is not None else None,
        last_triggered_at=row[8],
        revision=int(row[9]),
        created_at=row[10],
        updated_at=row[11],
    )


def _trigger(row) -> TradingAlertTrigger:
    return TradingAlertTrigger(
        trigger_id=str(row[0]),
        alert_id=str(row[1]),
        instrument_id=str(row[2]),
        observed_price=Decimal(row[3]),
        threshold=Decimal(row[4]),
        condition_type=str(row[5]),
        observed_at=row[6],
        idempotency_key=str(row[7]),
        payload=dict(row[8] or {}),
    )


class TradingAlertRepository:
    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory: UnitOfWorkFactory = unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def list_alerts(self, limit: int = 200) -> list[TradingAlert]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT alert_id, instrument_id, binding_id, condition_type, threshold,
                       enabled, cooldown_seconds, last_observed_price, last_triggered_at,
                       revision, created_at, updated_at
                  FROM omnix_trading_alerts
                 WHERE workspace_id = %s
                 ORDER BY updated_at DESC, alert_id
                 LIMIT %s
                """,
                (self.context.workspace_id, limit),
            ).fetchall()
            return [_alert(row) for row in rows]

    def create(self, request: TradingAlertCreate) -> TradingAlert:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                INSERT INTO omnix_trading_alerts (
                    workspace_id, alert_id, owner_user_id, instrument_id, binding_id,
                    condition_type, threshold, cooldown_seconds
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING alert_id, instrument_id, binding_id, condition_type, threshold,
                          enabled, cooldown_seconds, last_observed_price, last_triggered_at,
                          revision, created_at, updated_at
                """,
                (
                    self.context.workspace_id,
                    request.alert_id,
                    self.context.user_id,
                    request.instrument_id,
                    request.binding_id,
                    request.condition_type,
                    request.threshold,
                    request.cooldown_seconds,
                ),
            ).fetchone()
            uow.commit()
            return _alert(row)

    def update(self, alert_id: str, request: TradingAlertUpdate, expected_revision: int) -> TradingAlert:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                UPDATE omnix_trading_alerts
                   SET instrument_id = %s, binding_id = %s, condition_type = %s,
                       threshold = %s, enabled = %s, cooldown_seconds = %s,
                       revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND alert_id = %s AND revision = %s
                RETURNING alert_id, instrument_id, binding_id, condition_type, threshold,
                          enabled, cooldown_seconds, last_observed_price, last_triggered_at,
                          revision, created_at, updated_at
                """,
                (
                    request.instrument_id,
                    request.binding_id,
                    request.condition_type,
                    request.threshold,
                    request.enabled,
                    request.cooldown_seconds,
                    self.context.workspace_id,
                    alert_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(f"Trading alert expected revision {expected_revision}: {alert_id}")
            uow.commit()
            return _alert(row)

    def archive(self, alert_id: str, expected_revision: int) -> TradingAlert:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                UPDATE omnix_trading_alerts
                   SET enabled = FALSE, revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND alert_id = %s AND revision = %s
                RETURNING alert_id, instrument_id, binding_id, condition_type, threshold,
                          enabled, cooldown_seconds, last_observed_price, last_triggered_at,
                          revision, created_at, updated_at
                """,
                (self.context.workspace_id, alert_id, expected_revision),
            ).fetchone()
            if row is None:
                raise RevisionConflict(f"Trading alert expected revision {expected_revision}: {alert_id}")
            uow.commit()
            return _alert(row)

    def list_triggers(self, limit: int = 200) -> list[TradingAlertTrigger]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT trigger_id, alert_id, instrument_id, observed_price, threshold,
                       condition_type, observed_at, idempotency_key, payload
                  FROM omnix_trading_alert_triggers
                 WHERE workspace_id = %s
                 ORDER BY observed_at DESC, trigger_id
                 LIMIT %s
                """,
                (self.context.workspace_id, limit),
            ).fetchall()
            return [_trigger(row) for row in rows]

    def evaluate(self, evaluation: TradingAlertEvaluation) -> list[TradingAlertTrigger]:
        triggers: list[TradingAlertTrigger] = []
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT alert_id, instrument_id, binding_id, condition_type, threshold,
                       enabled, cooldown_seconds, last_observed_price, last_triggered_at,
                       revision, created_at, updated_at
                  FROM omnix_trading_alerts
                 WHERE workspace_id = %s AND instrument_id = %s AND enabled = TRUE
                 FOR UPDATE
                """,
                (self.context.workspace_id, evaluation.instrument_id),
            ).fetchall()
            for row in rows:
                alert = _alert(row)
                should_trigger = crossed_threshold(
                    alert.condition_type,
                    alert.last_observed_price,
                    evaluation.observed_price,
                    alert.threshold,
                ) and cooldown_elapsed(
                    alert.last_triggered_at,
                    evaluation.observed_at,
                    alert.cooldown_seconds,
                )
                triggered_at = alert.last_triggered_at
                if should_trigger:
                    key = alert_trigger_key(alert.alert_id, evaluation.observed_at, evaluation.observed_price)
                    trigger_id = key[:32]
                    payload = {
                        "binding_id": alert.binding_id,
                        "previous_price": str(alert.last_observed_price),
                    }
                    inserted = uow.connection.execute(
                        """
                        INSERT INTO omnix_trading_alert_triggers (
                            workspace_id, trigger_id, alert_id, instrument_id,
                            observed_price, threshold, condition_type, observed_at,
                            idempotency_key, payload
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
                        RETURNING trigger_id, alert_id, instrument_id, observed_price,
                                  threshold, condition_type, observed_at, idempotency_key, payload
                        """,
                        (
                            self.context.workspace_id,
                            trigger_id,
                            alert.alert_id,
                            alert.instrument_id,
                            evaluation.observed_price,
                            alert.threshold,
                            alert.condition_type,
                            evaluation.observed_at,
                            key,
                            json.dumps(payload),
                        ),
                    ).fetchone()
                    if inserted is not None:
                        triggers.append(_trigger(inserted))
                        triggered_at = evaluation.observed_at
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_alerts
                       SET last_observed_price = %s, last_triggered_at = %s,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND alert_id = %s
                    """,
                    (
                        evaluation.observed_price,
                        triggered_at,
                        self.context.workspace_id,
                        alert.alert_id,
                    ),
                )
            uow.commit()
        return triggers


AlertRepositoryFactory = Callable[[], TradingAlertRepository]


def default_alert_repository() -> TradingAlertRepository:
    return TradingAlertRepository()
