from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.persistence.errors import RevisionConflict
from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .indicators.engine import CORE_INDICATOR_FORMULA_VERSION


AlertCondition = Literal[
    "price_above",
    "price_below",
    "percent_change_above",
    "percent_change_below",
    "indicator_above",
    "indicator_below",
    "indicator_cross_above",
    "indicator_cross_below",
    "volume_above",
    "volume_below",
    "trendline_crossing",
    "trendline_crossing_up",
    "trendline_crossing_down",
    "trendline_above",
    "trendline_below",
]
IndicatorId = Literal["sma", "ema", "rsi", "macd", "bollinger", "atr", "vwap"]
TrendlineMode = Literal[
    "crossing",
    "crossing_up",
    "crossing_down",
    "greater_than",
    "less_than",
]


class TrendlineAlertPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: datetime
    price: Decimal


class TradingAlertParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lookback_bars: int = Field(default=1, ge=1, le=500)
    indicator_id: IndicatorId | None = None
    period: int = Field(default=14, ge=1, le=500)
    fast_period: int = Field(default=12, ge=1, le=500)
    slow_period: int = Field(default=26, ge=1, le=500)
    signal_period: int = Field(default=9, ge=1, le=500)
    component: Literal[
        "value", "line", "signal", "histogram", "upper", "middle", "lower"
    ] = "value"
    anchor_bars_ago: int = Field(default=0, ge=0, le=499)
    message: str = Field(default="", max_length=500)
    notification_channels: list[Literal["app", "toast", "sound"]] = Field(
        default_factory=lambda: ["app", "toast"],
        max_length=3,
    )
    trigger_policy: Literal["once", "once_per_bar", "every_time"] = "every_time"
    trendline_points: list[TrendlineAlertPoint] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )
    trendline_mode: TrendlineMode | None = None


class TradingAlertEvaluationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval: str = Field(default="1m", min_length=1, max_length=16)
    allow_partial_bars: bool = False
    formula_version: str = CORE_INDICATOR_FORMULA_VERSION


class _AlertContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    condition_type: AlertCondition
    threshold: Decimal
    parameters: TradingAlertParameters = Field(default_factory=TradingAlertParameters)
    evaluation_policy: TradingAlertEvaluationPolicy = Field(
        default_factory=TradingAlertEvaluationPolicy
    )
    cooldown_seconds: int = Field(default=0, ge=0, le=31_536_000)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_condition_contract(self):
        if (
            self.condition_type.startswith("indicator_")
            and self.parameters.indicator_id is None
        ):
            raise ValueError("indicator conditions require parameters.indicator_id")
        if self.evaluation_policy.formula_version != CORE_INDICATOR_FORMULA_VERSION:
            raise ValueError(
                f"unsupported alert formula version: {self.evaluation_policy.formula_version}"
            )
        if (
            self.parameters.indicator_id == "macd"
            and self.parameters.fast_period >= self.parameters.slow_period
        ):
            raise ValueError("MACD fast_period must be smaller than slow_period")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        if self.condition_type.startswith("trendline_"):
            if self.parameters.trendline_points is None:
                raise ValueError("trendline conditions require two trendline points")
            if self.threshold != 0:
                raise ValueError("trendline conditions use a zero threshold")
            expected_mode = {
                "trendline_crossing": "crossing",
                "trendline_crossing_up": "crossing_up",
                "trendline_crossing_down": "crossing_down",
                "trendline_above": "greater_than",
                "trendline_below": "less_than",
            }[self.condition_type]
            if self.parameters.trendline_mode not in (None, expected_mode):
                raise ValueError("trendline_mode must match condition_type")
        return self


class TradingAlert(_AlertContract):
    alert_id: str
    enabled: bool = True
    last_observed_price: Decimal | None = None
    last_observed_value: Decimal | None = None
    last_triggered_at: datetime | None = None
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def is_expired(self, at: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        moment = at or datetime.now(timezone.utc)
        return self.expires_at <= moment


class TradingAlertCreate(_AlertContract):
    alert_id: str = Field(min_length=1, max_length=200)


class TradingAlertUpdate(_AlertContract):
    enabled: bool = True


class TradingAlertEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    binding_id: str | None = None
    resolved_binding_id: str | None = None
    provider: str | None = None
    interval: str = "1m"
    observed_price: Decimal
    observed_volume: Decimal | None = None
    is_final: bool = True
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    percent_changes: dict[str, Decimal] = Field(default_factory=dict)
    indicator_values: dict[str, Decimal] = Field(default_factory=dict)


class TradingAlertTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_id: str
    alert_id: str
    instrument_id: str
    binding_id: str | None = None
    provider: str | None = None
    observed_value: Decimal
    observed_price: Decimal
    threshold: Decimal
    condition_type: AlertCondition
    observed_at: datetime
    evaluated_at: datetime
    idempotency_key: str
    payload: dict[str, object] = Field(default_factory=dict)


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


def _is_above(condition_type: AlertCondition) -> bool:
    return condition_type.endswith("_above") or condition_type in {
        "trendline_crossing_up",
        "trendline_above",
    }


def crossed_threshold(
    condition_type: AlertCondition,
    previous_value: Decimal | None,
    observed_value: Decimal,
    threshold: Decimal,
) -> bool:
    if previous_value is None:
        return False
    if condition_type == "trendline_crossing":
        return (previous_value < threshold <= observed_value) or (
            previous_value > threshold >= observed_value
        )
    if _is_above(condition_type):
        return previous_value < threshold <= observed_value
    return previous_value > threshold >= observed_value


def cooldown_elapsed(
    last_triggered_at: datetime | None,
    evaluated_at: datetime,
    cooldown_seconds: int,
) -> bool:
    if last_triggered_at is None or cooldown_seconds <= 0:
        return True
    return evaluated_at >= last_triggered_at + timedelta(seconds=cooldown_seconds)


def alert_trigger_key(
    alert_id: str,
    observed_at: datetime,
    observed_value: Decimal,
    condition_type: AlertCondition = "price_above",
) -> str:
    raw = (
        f"{alert_id}|{condition_type}|"
        f"{observed_at.astimezone(timezone.utc).isoformat()}|{observed_value}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def alert_condition_value(
    alert: TradingAlert,
    evaluation: TradingAlertEvaluation,
) -> Decimal | None:
    if alert.condition_type.startswith("trendline_"):
        points = alert.parameters.trendline_points
        if points is None or len(points) != 2:
            return None
        first, second = points
        first_time = first.time.astimezone(timezone.utc)
        second_time = second.time.astimezone(timezone.utc)
        observed_time = evaluation.observed_at.astimezone(timezone.utc)
        duration = Decimal(str((second_time - first_time).total_seconds()))
        if duration == 0:
            return None
        elapsed = Decimal(str((observed_time - first_time).total_seconds()))
        line_price = first.price + (second.price - first.price) * elapsed / duration
        return evaluation.observed_price - line_price
    if alert.condition_type.startswith("price_"):
        return evaluation.observed_price
    if alert.condition_type.startswith("volume_"):
        return evaluation.observed_volume
    if alert.condition_type.startswith("percent_change_"):
        return evaluation.percent_changes.get(alert.alert_id)
    return evaluation.indicator_values.get(alert.alert_id)


def _alert(row) -> TradingAlert:
    return TradingAlert(
        alert_id=str(row[0]),
        instrument_id=str(row[1]),
        binding_id=str(row[2]) if row[2] is not None else None,
        condition_type=str(row[3]),
        threshold=Decimal(row[4]),
        parameters=dict(row[5] or {}),
        evaluation_policy=dict(row[6] or {}),
        enabled=bool(row[7]),
        cooldown_seconds=int(row[8]),
        expires_at=row[9],
        last_observed_price=Decimal(row[10]) if row[10] is not None else None,
        last_observed_value=Decimal(row[11]) if row[11] is not None else None,
        last_triggered_at=row[12],
        revision=int(row[13]),
        created_at=row[14],
        updated_at=row[15],
    )


def _trigger(row) -> TradingAlertTrigger:
    return TradingAlertTrigger(
        trigger_id=str(row[0]),
        alert_id=str(row[1]),
        instrument_id=str(row[2]),
        binding_id=str(row[3]) if row[3] is not None else None,
        provider=str(row[4]) if row[4] is not None else None,
        observed_value=Decimal(row[5]),
        observed_price=Decimal(row[6]),
        threshold=Decimal(row[7]),
        condition_type=str(row[8]),
        observed_at=row[9],
        evaluated_at=row[10],
        idempotency_key=str(row[11]),
        payload=dict(row[12] or {}),
    )


_ALERT_COLUMNS = """
    alert_id, instrument_id, binding_id, condition_type, threshold,
    condition_parameters, evaluation_policy, enabled, cooldown_seconds,
    expires_at, last_observed_price, last_observed_value, last_triggered_at,
    revision, created_at, updated_at
"""
_TRIGGER_COLUMNS = """
    trigger_id, alert_id, instrument_id, binding_id, provider,
    observed_value, observed_price, threshold, condition_type,
    observed_at, evaluated_at, idempotency_key, payload
"""


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
                f"""
                SELECT {_ALERT_COLUMNS}
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
                f"""
                INSERT INTO omnix_trading_alerts (
                    workspace_id, alert_id, owner_user_id, instrument_id, binding_id,
                    condition_type, threshold, condition_parameters, evaluation_policy,
                    cooldown_seconds, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                RETURNING {_ALERT_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    request.alert_id,
                    self.context.user_id,
                    request.instrument_id,
                    request.binding_id,
                    request.condition_type,
                    request.threshold,
                    request.parameters.model_dump_json(),
                    request.evaluation_policy.model_dump_json(),
                    request.cooldown_seconds,
                    request.expires_at,
                ),
            ).fetchone()
            uow.commit()
            return _alert(row)

    def update(
        self,
        alert_id: str,
        request: TradingAlertUpdate,
        expected_revision: int,
    ) -> TradingAlert:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_alerts
                   SET instrument_id = %s, binding_id = %s, condition_type = %s,
                       threshold = %s, condition_parameters = %s::jsonb,
                       evaluation_policy = %s::jsonb, enabled = %s,
                       cooldown_seconds = %s, expires_at = %s,
                       last_observed_price = NULL, last_observed_value = NULL,
                       last_triggered_at = NULL, revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND alert_id = %s AND revision = %s
                RETURNING {_ALERT_COLUMNS}
                """,
                (
                    request.instrument_id,
                    request.binding_id,
                    request.condition_type,
                    request.threshold,
                    request.parameters.model_dump_json(),
                    request.evaluation_policy.model_dump_json(),
                    request.enabled,
                    request.cooldown_seconds,
                    request.expires_at,
                    self.context.workspace_id,
                    alert_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"Trading alert expected revision {expected_revision}: {alert_id}"
                )
            uow.commit()
            return _alert(row)

    def archive(self, alert_id: str, expected_revision: int) -> TradingAlert:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_alerts
                   SET enabled = FALSE, revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND alert_id = %s AND revision = %s
                RETURNING {_ALERT_COLUMNS}
                """,
                (self.context.workspace_id, alert_id, expected_revision),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"Trading alert expected revision {expected_revision}: {alert_id}"
                )
            uow.commit()
            return _alert(row)

    def list_triggers(self, limit: int = 200) -> list[TradingAlertTrigger]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"""
                SELECT {_TRIGGER_COLUMNS}
                  FROM omnix_trading_alert_triggers
                 WHERE workspace_id = %s
                 ORDER BY observed_at DESC, evaluated_at DESC, trigger_id
                 LIMIT %s
                """,
                (self.context.workspace_id, limit),
            ).fetchall()
            return [_trigger(row) for row in rows]

    def evaluate(self, evaluation: TradingAlertEvaluation) -> list[TradingAlertTrigger]:
        triggers: list[TradingAlertTrigger] = []
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"""
                SELECT {_ALERT_COLUMNS}
                  FROM omnix_trading_alerts
                 WHERE workspace_id = %s AND instrument_id = %s AND enabled = TRUE
                   AND (expires_at IS NULL OR expires_at > %s)
                 FOR UPDATE
                """,
                (
                    self.context.workspace_id,
                    evaluation.instrument_id,
                    evaluation.evaluated_at,
                ),
            ).fetchall()
            for row in rows:
                alert = _alert(row)
                if alert.binding_id and alert.binding_id != evaluation.binding_id:
                    continue
                if alert.evaluation_policy.interval != evaluation.interval:
                    continue
                if (
                    not evaluation.is_final
                    and not alert.evaluation_policy.allow_partial_bars
                ):
                    continue
                observed_value = alert_condition_value(alert, evaluation)
                if observed_value is None:
                    continue
                should_trigger = crossed_threshold(
                    alert.condition_type,
                    alert.last_observed_value,
                    observed_value,
                    alert.threshold,
                ) and cooldown_elapsed(
                    alert.last_triggered_at,
                    evaluation.evaluated_at,
                    alert.cooldown_seconds,
                )
                triggered_at = alert.last_triggered_at
                if should_trigger:
                    key = alert_trigger_key(
                        alert.alert_id,
                        evaluation.observed_at,
                        observed_value,
                        alert.condition_type,
                    )
                    trigger_id = key[:32]
                    resolved_binding_id = (
                        evaluation.resolved_binding_id or evaluation.binding_id
                    )
                    payload = {
                        "instrument_id": alert.instrument_id,
                        "condition_type": alert.condition_type,
                        "condition_parameters": alert.parameters.model_dump(mode="json"),
                        "evaluation_policy": alert.evaluation_policy.model_dump(mode="json"),
                        "provider": evaluation.provider,
                        "requested_binding_id": evaluation.binding_id,
                        "resolved_binding_id": resolved_binding_id,
                        "source_time": evaluation.observed_at.isoformat(),
                        "evaluation_time": evaluation.evaluated_at.isoformat(),
                        "previous_value": str(alert.last_observed_value),
                        "observed_value": str(observed_value),
                        "threshold": str(alert.threshold),
                        "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
                    }
                    inserted = uow.connection.execute(
                        f"""
                        INSERT INTO omnix_trading_alert_triggers (
                            workspace_id, trigger_id, alert_id, instrument_id,
                            binding_id, provider, observed_value, observed_price,
                            threshold, condition_type, observed_at, evaluated_at,
                            idempotency_key, payload
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s::jsonb
                        )
                        ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
                        RETURNING {_TRIGGER_COLUMNS}
                        """,
                        (
                            self.context.workspace_id,
                            trigger_id,
                            alert.alert_id,
                            alert.instrument_id,
                            resolved_binding_id,
                            evaluation.provider,
                            observed_value,
                            evaluation.observed_price,
                            alert.threshold,
                            alert.condition_type,
                            evaluation.observed_at,
                            evaluation.evaluated_at,
                            key,
                            json.dumps(payload),
                        ),
                    ).fetchone()
                    if inserted is not None:
                        triggers.append(_trigger(inserted))
                        triggered_at = evaluation.evaluated_at
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_alerts
                       SET last_observed_price = %s, last_observed_value = %s,
                           last_triggered_at = %s, updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND alert_id = %s
                    """,
                    (
                        evaluation.observed_price,
                        observed_value,
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
