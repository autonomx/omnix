from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, ClassVar, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.persistence.errors import RevisionConflict
from app.security.tenant_context import RequestTenant, TenantContext
from app.security.url_policy import UrlPolicyError, check_outbound_url
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .alert_conditions import (
    MAX_ALERT_CONDITIONS,
    AlertConditionSpec,
    AlertFrequency,
    ChannelTarget,
    PriceSource,
    TrendlineAlertPoint,
    ValueTarget,
    legacy_conditions,
    validate_conditions_against_registry,
)
from .alerts_evaluation import AlertConditionOutcome, ConditionObservation, operator_met
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
    # TVP-1.2: the alert is described by its ``conditions``.
    "conditions",
]
IndicatorId = Literal[
    "sma",
    "ema",
    "rsi",
    "macd",
    "bollinger",
    "atr",
    "vwap",
    "stochastic-rsi",
]
TrendlineMode = Literal[
    "crossing",
    "crossing_up",
    "crossing_down",
    "greater_than",
    "less_than",
]
AlertNotificationChannel = Literal["app", "toast", "sound", "webhook", "email", "push"]

class AlertWebhookSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2000)
    # Read-only: the server sets it from the protected secret store.
    has_secret: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            return check_outbound_url(value.strip())
        except UrlPolicyError as exc:
            raise ValueError(f"webhook url is not allowed: {exc}") from exc


class AlertEmailSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")


class AlertSoundSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)


class AlertDeliverySettings(BaseModel):
    """Per-alert channel settings (TVP-1.2 schema; delivery itself is TVP-0.5a-c / TVP-1.5)."""

    model_config = ConfigDict(extra="forbid")

    webhook: AlertWebhookSettings | None = None
    email: AlertEmailSettings | None = None
    sound: AlertSoundSettings | None = None


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
    notification_channels: list[AlertNotificationChannel] = Field(
        default_factory=lambda: list[AlertNotificationChannel](["app", "toast"]),
        max_length=6,
    )
    # Deprecated mirror of the alert's ``frequency``; requests without a
    # ``frequency`` still set it here.
    trigger_policy: AlertFrequency = "every_time"
    delivery: AlertDeliverySettings = Field(default_factory=AlertDeliverySettings)
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
    # Requests must not send conditions that disagree with a legacy condition_type.
    _require_legacy_agreement: ClassVar[bool] = False

    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    condition_type: AlertCondition = "conditions"
    threshold: Decimal = Decimal("0")
    conditions: list[AlertConditionSpec] = Field(default_factory=list, max_length=MAX_ALERT_CONDITIONS)
    frequency: AlertFrequency = "every_time"
    parameters: TradingAlertParameters = Field(default_factory=TradingAlertParameters)
    evaluation_policy: TradingAlertEvaluationPolicy = Field(
        default_factory=TradingAlertEvaluationPolicy
    )
    cooldown_seconds: int = Field(default=0, ge=0, le=31_536_000)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_condition_contract(self):
        if "frequency" not in self.model_fields_set:
            self.frequency = self.parameters.trigger_policy
        self.parameters.trigger_policy = self.frequency
        if self.evaluation_policy.formula_version != CORE_INDICATOR_FORMULA_VERSION:
            raise ValueError(
                f"unsupported alert formula version: {self.evaluation_policy.formula_version}"
            )
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        if self.condition_type == "conditions":
            if not self.conditions:
                raise ValueError("condition_type 'conditions' needs one to five conditions")
            if self.threshold != 0:
                raise ValueError("alerts described by conditions use a zero threshold")
            return self
        self._validate_legacy_fields()
        derived = legacy_conditions(self.condition_type, self.threshold, self.parameters)
        if not self.conditions:
            self.conditions = derived
        elif self._require_legacy_agreement and self.conditions != derived:
            raise ValueError(
                "conditions disagree with the legacy condition_type; send condition_type 'conditions'"
            )
        return self

    def _validate_legacy_fields(self) -> None:
        if (
            self.condition_type.startswith("indicator_")
            and self.parameters.indicator_id is None
        ):
            raise ValueError("indicator conditions require parameters.indicator_id")
        if (
            self.parameters.indicator_id == "macd"
            and self.parameters.fast_period >= self.parameters.slow_period
        ):
            raise ValueError("MACD fast_period must be smaller than slow_period")
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


class _AlertWrite(_AlertContract):
    _require_legacy_agreement: ClassVar[bool] = True

    # Write-only; stored in the protected secret store, never returned.
    webhook_secret: SecretStr | None = Field(default=None, max_length=500, exclude=True)

    @model_validator(mode="after")
    def validate_against_registry(self):
        validate_conditions_against_registry(self.conditions)
        return self


class TradingAlertCreate(_AlertWrite):
    alert_id: str = Field(min_length=1, max_length=200)


class TradingAlertUpdate(_AlertWrite):
    enabled: bool = True


class TradingAlertEvaluation(BaseModel):
    """An observed price pushed to ``POST /api/trading/alerts/evaluate``."""

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
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class AlertEvaluationContext:
    """Where one batch of outcomes came from."""

    instrument_id: str
    interval: str
    evaluated_at: datetime
    binding_id: str | None = None
    resolved_binding_id: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class AlertOutcomeRecord:
    """An outcome computed for one revision of one alert."""

    alert_id: str
    revision: int
    outcome: AlertConditionOutcome


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


def cooldown_elapsed(
    last_triggered_at: datetime | None,
    evaluated_at: datetime,
    cooldown_seconds: int,
) -> bool:
    if last_triggered_at is None or cooldown_seconds <= 0:
        return True
    return evaluated_at >= last_triggered_at + timedelta(seconds=cooldown_seconds)


ONCE_PER_MINUTE = timedelta(seconds=60)


def frequency_allows(
    frequency: str,
    last_triggered_at: datetime | None,
    evaluated_at: datetime,
) -> bool:
    """The time-based part of a frequency; per-bar and once limits are idempotency keys."""
    if frequency != "once_per_minute" or last_triggered_at is None:
        return True
    return evaluated_at >= last_triggered_at + ONCE_PER_MINUTE


def alert_trigger_key(
    alert_id: str,
    revision: int,
    frequency: str,
    outcome: AlertConditionOutcome,
) -> str:
    """The idempotency key of a trigger.

    ``once`` has one key per alert revision; the per-bar frequencies one per
    bar; ``every_time`` and ``once_per_minute`` one per bar and observed values.
    Keys live in PostgreSQL, so a restart cannot trigger the same thing twice.
    """
    parts = [alert_id, str(revision), frequency]
    if frequency != "once":
        parts.append(outcome.bar_start.astimezone(timezone.utc).isoformat())
    if frequency in {"every_time", "once_per_minute"}:
        parts.append(outcome.bar_end.astimezone(timezone.utc).isoformat())
        parts.extend(json.dumps(observation.payload(), sort_keys=True) for observation in outcome.observations)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def pushed_price_outcome(
    alert: TradingAlert,
    evaluation: TradingAlertEvaluation,
) -> AlertConditionOutcome | None:
    """``POST /evaluate``: the pushed price against the previous observation.

    Only alerts whose conditions all read one price field (close from
    ``observed_price``, or volume from ``observed_volume``) against value
    targets qualify; ``last_observed_value`` is the previous value.
    """
    fields = {
        condition.source.field if isinstance(condition.source, PriceSource) else None
        for condition in alert.conditions
    }
    if len(fields) != 1 or not fields <= {"close", "volume"}:
        return None
    current = evaluation.observed_volume if fields == {"volume"} else evaluation.observed_price
    if current is None:
        return None
    previous = alert.last_observed_value
    observations: list[ConditionObservation] = []
    for position, condition in enumerate(alert.conditions):
        target = condition.target
        if isinstance(target, ValueTarget):
            pair = (target.value, target.value)
            met = operator_met(condition.operator, (previous, current), target=pair)
            observations.append(
                ConditionObservation(position, condition.operator, met, current, previous, target.value, target.value)
            )
        elif (
            isinstance(target, ChannelTarget)
            and isinstance(target.upper, ValueTarget)
            and isinstance(target.lower, ValueTarget)
        ):
            upper = (target.upper.value, target.upper.value)
            lower = (target.lower.value, target.lower.value)
            met = operator_met(condition.operator, (previous, current), upper=upper, lower=lower)
            observations.append(
                ConditionObservation(
                    position, condition.operator, met, current, previous,
                    upper=upper[1], lower=lower[1], upper_previous=upper[0], lower_previous=lower[0],
                )
            )
        else:
            return None
    return AlertConditionOutcome(
        met=all(observation.met for observation in observations),
        bar_start=evaluation.observed_at,
        bar_end=evaluation.observed_at,
        bar_is_final=evaluation.is_final,
        close=evaluation.observed_price,
        volume=evaluation.observed_volume or Decimal("0"),
        observations=tuple(observations),
    )


def _condition(row) -> AlertConditionSpec:
    return AlertConditionSpec.model_validate(
        {
            "source": row[2],
            "operator": str(row[3]),
            "target": row[4],
            "amount": Decimal(row[5]) if row[5] is not None else None,
            "bars": int(row[6]) if row[6] is not None else None,
        }
    )


def _alert(row, conditions: list[AlertConditionSpec] | None = None) -> TradingAlert:
    return TradingAlert(
        alert_id=str(row[0]),
        instrument_id=str(row[1]),
        binding_id=str(row[2]) if row[2] is not None else None,
        condition_type=cast(Any, str(row[3])),
        threshold=Decimal(row[4]),
        parameters=cast(Any, dict(row[5] or {})),
        evaluation_policy=cast(Any, dict(row[6] or {})),
        enabled=bool(row[7]),
        cooldown_seconds=int(row[8]),
        expires_at=row[9],
        last_observed_price=Decimal(row[10]) if row[10] is not None else None,
        last_observed_value=Decimal(row[11]) if row[11] is not None else None,
        last_triggered_at=row[12],
        revision=int(row[13]),
        created_at=row[14],
        updated_at=row[15],
        frequency=cast(Any, str(row[16])),
        conditions=conditions or [],
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
        condition_type=cast(Any, str(row[8])),
        observed_at=row[9],
        evaluated_at=row[10],
        idempotency_key=str(row[11]),
        payload=dict(row[12] or {}),
    )


_ALERT_COLUMNS = """
    alert_id, instrument_id, binding_id, condition_type, threshold,
    condition_parameters, evaluation_policy, enabled, cooldown_seconds,
    expires_at, last_observed_price, last_observed_value, last_triggered_at,
    revision, created_at, updated_at, frequency
"""
_TRIGGER_COLUMNS = """
    trigger_id, alert_id, instrument_id, binding_id, provider,
    observed_value, observed_price, threshold, condition_type,
    observed_at, evaluated_at, idempotency_key, payload
"""
_CONDITION_COLUMNS = "alert_id, position, source, operator, target, amount, bars"


class TradingAlertRepository:
    context = RequestTenant()
    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory: UnitOfWorkFactory = unit_of_work,
    ) -> None:
        self.context = context
        self.uow_factory = uow_factory

    def _conditions(self, connection, alert_ids: Iterable[str]) -> dict[str, list[AlertConditionSpec]]:
        ids = list(alert_ids)
        if not ids:
            return {}
        rows = connection.execute(
            f"""
            SELECT {_CONDITION_COLUMNS}
              FROM omnix_trading_alert_conditions
             WHERE workspace_id = %s AND alert_id = ANY(%s)
             ORDER BY alert_id, position
            """,
            (self.context.workspace_id, ids),
        ).fetchall()
        grouped: dict[str, list[AlertConditionSpec]] = {}
        for row in rows:
            grouped.setdefault(str(row[0]), []).append(_condition(row))
        return grouped

    def _alerts(self, connection, rows) -> list[TradingAlert]:
        conditions = self._conditions(connection, (str(row[0]) for row in rows))
        return [_alert(row, conditions.get(str(row[0]))) for row in rows]

    def _write_conditions(self, connection, alert_id: str, conditions: list[AlertConditionSpec]) -> None:
        connection.execute(
            "DELETE FROM omnix_trading_alert_conditions WHERE workspace_id = %s AND alert_id = %s",
            (self.context.workspace_id, alert_id),
        )
        for position, condition in enumerate(conditions):
            connection.execute(
                """
                INSERT INTO omnix_trading_alert_conditions (
                    workspace_id, alert_id, position, source, operator, target, amount, bars
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
                """,
                (
                    self.context.workspace_id,
                    alert_id,
                    position,
                    condition.source.model_dump_json(),
                    condition.operator,
                    condition.target.model_dump_json() if condition.target is not None else None,
                    condition.amount,
                    condition.bars,
                ),
            )

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
            return self._alerts(uow.connection, rows)

    def create(self, request: TradingAlertCreate) -> TradingAlert:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_alerts (
                    workspace_id, alert_id, owner_user_id, instrument_id, binding_id,
                    condition_type, threshold, condition_parameters, evaluation_policy,
                    cooldown_seconds, expires_at, frequency
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
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
                    request.frequency,
                ),
            ).fetchone()
            self._write_conditions(uow.connection, request.alert_id, request.conditions)
            uow.commit()
            return _alert(row, request.conditions)

    def update(
        self,
        alert_id: str,
        request: TradingAlertUpdate,
        expected_revision: int,
    ) -> TradingAlert:
        with self.uow_factory() as uow:
            previous_conditions = self._conditions(uow.connection, [alert_id]).get(alert_id)
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_alerts
                   SET instrument_id = %s, binding_id = %s, condition_type = %s,
                       threshold = %s, condition_parameters = %s::jsonb,
                       evaluation_policy = %s::jsonb, enabled = %s,
                       cooldown_seconds = %s, expires_at = %s, frequency = %s,
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
                    request.frequency,
                    self.context.workspace_id,
                    alert_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"Trading alert expected revision {expected_revision}: {alert_id}"
                )
            if previous_conditions != request.conditions:
                # The lifecycle trigger keeps observation history when the alert's own
                # columns are unchanged; a new condition set starts a new history.
                row = uow.connection.execute(
                    f"""
                    UPDATE omnix_trading_alerts
                       SET last_observed_price = NULL, last_observed_value = NULL,
                           last_triggered_at = NULL
                     WHERE workspace_id = %s AND alert_id = %s
                    RETURNING {_ALERT_COLUMNS}
                    """,
                    (self.context.workspace_id, alert_id),
                ).fetchone()
                self._write_conditions(uow.connection, alert_id, request.conditions)
            uow.commit()
            return _alert(row, request.conditions)

    def archive(self, alert_id: str, expected_revision: int) -> TradingAlert:
        with self.uow_factory() as uow:
            conditions = self._conditions(uow.connection, [alert_id]).get(alert_id)
            row = uow.connection.execute(
                f"""
                DELETE FROM omnix_trading_alerts
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
            return _alert(row, conditions).model_copy(update={"enabled": False})

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

    def _locked_alerts(self, connection, instrument_id: str, evaluated_at: datetime) -> list[TradingAlert]:
        rows = connection.execute(
            f"""
            SELECT {_ALERT_COLUMNS}
              FROM omnix_trading_alerts
             WHERE workspace_id = %s AND instrument_id = %s AND enabled = TRUE
               AND (expires_at IS NULL OR expires_at > %s)
             ORDER BY alert_id
             FOR UPDATE
            """,
            (self.context.workspace_id, instrument_id, evaluated_at),
        ).fetchall()
        return self._alerts(connection, rows)

    def evaluate(self, evaluation: TradingAlertEvaluation) -> list[TradingAlertTrigger]:
        """Evaluate a pushed price; see ``pushed_price_outcome`` for which alerts qualify."""
        context = AlertEvaluationContext(
            instrument_id=evaluation.instrument_id,
            interval=evaluation.interval,
            evaluated_at=evaluation.evaluated_at,
            binding_id=evaluation.binding_id,
            resolved_binding_id=evaluation.resolved_binding_id,
            provider=evaluation.provider,
        )
        triggers: list[TradingAlertTrigger] = []
        with self.uow_factory() as uow:
            for alert in self._locked_alerts(uow.connection, evaluation.instrument_id, evaluation.evaluated_at):
                if alert.binding_id and alert.binding_id != evaluation.binding_id:
                    continue
                if alert.evaluation_policy.interval != evaluation.interval:
                    continue
                outcome = pushed_price_outcome(alert, evaluation)
                if outcome is None:
                    continue
                trigger = self._apply(uow.connection, alert, outcome, context)
                if trigger is not None:
                    triggers.append(trigger)
            uow.commit()
        return triggers

    def record_outcomes(
        self,
        context: AlertEvaluationContext,
        outcomes: Iterable[AlertOutcomeRecord],
    ) -> list[TradingAlertTrigger]:
        """Apply frequency, cooldown and idempotency to outcomes computed on bars."""
        by_alert: Mapping[str, AlertOutcomeRecord] = {record.alert_id: record for record in outcomes}
        triggers: list[TradingAlertTrigger] = []
        if not by_alert:
            return triggers
        with self.uow_factory() as uow:
            for alert in self._locked_alerts(uow.connection, context.instrument_id, context.evaluated_at):
                record = by_alert.get(alert.alert_id)
                # An alert edited since its bars were evaluated waits for the next pass.
                if record is None or record.revision != alert.revision:
                    continue
                trigger = self._apply(uow.connection, alert, record.outcome, context)
                if trigger is not None:
                    triggers.append(trigger)
            uow.commit()
        return triggers

    def _apply(
        self,
        connection,
        alert: TradingAlert,
        outcome: AlertConditionOutcome,
        context: AlertEvaluationContext,
    ) -> TradingAlertTrigger | None:
        final_only = alert.frequency == "once_per_bar_close" or not alert.evaluation_policy.allow_partial_bars
        if final_only and not outcome.bar_is_final:
            return None
        evaluated_at = context.evaluated_at
        should_trigger = (
            outcome.met
            # A bar that closed before the alert was created, edited or re-enabled is history.
            and not (outcome.bar_is_final and alert.updated_at is not None and outcome.bar_end <= alert.updated_at)
            and cooldown_elapsed(alert.last_triggered_at, evaluated_at, alert.cooldown_seconds)
            and frequency_allows(alert.frequency, alert.last_triggered_at, evaluated_at)
        )
        triggered_at = alert.last_triggered_at
        enabled = alert.enabled
        inserted_trigger: TradingAlertTrigger | None = None
        primary_value = outcome.primary_value
        if should_trigger:
            key = alert_trigger_key(alert.alert_id, alert.revision, alert.frequency, outcome)
            resolved_binding_id = context.resolved_binding_id or context.binding_id
            payload = {
                "instrument_id": alert.instrument_id,
                "condition_type": alert.condition_type,
                "frequency": alert.frequency,
                "conditions": [condition.model_dump(mode="json") for condition in alert.conditions],
                "observations": outcome.observation_payload(),
                "condition_parameters": alert.parameters.model_dump(mode="json"),
                "evaluation_policy": alert.evaluation_policy.model_dump(mode="json"),
                "provider": context.provider,
                "requested_binding_id": context.binding_id,
                "resolved_binding_id": resolved_binding_id,
                "bar_start": outcome.bar_start.isoformat(),
                "bar_is_final": outcome.bar_is_final,
                "source_time": outcome.bar_end.isoformat(),
                "evaluation_time": evaluated_at.isoformat(),
                "previous_value": str(outcome.observations[0].source_previous) if outcome.observations else None,
                "observed_value": str(primary_value),
                "threshold": str(alert.threshold),
                "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
            }
            inserted = connection.execute(
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
                    key[:32],
                    alert.alert_id,
                    alert.instrument_id,
                    resolved_binding_id,
                    context.provider,
                    primary_value if primary_value is not None else outcome.close,
                    outcome.close,
                    alert.threshold,
                    alert.condition_type,
                    outcome.bar_end,
                    evaluated_at,
                    key,
                    json.dumps(payload),
                ),
            ).fetchone()
            if inserted is not None:
                inserted_trigger = _trigger(inserted)
                triggered_at = evaluated_at
                if alert.frequency == "once":
                    enabled = False
        connection.execute(
            """
            UPDATE omnix_trading_alerts
               SET last_observed_price = %s,
                   last_observed_value = COALESCE(%s, last_observed_value),
                   last_triggered_at = %s,
                   enabled = %s,
                   updated_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE updated_at END
             WHERE workspace_id = %s AND alert_id = %s
            """,
            (
                outcome.close,
                primary_value,
                triggered_at,
                enabled,
                enabled != alert.enabled,
                self.context.workspace_id,
                alert.alert_id,
            ),
        )
        return inserted_trigger


AlertRepositoryFactory = Callable[[], TradingAlertRepository]


def default_alert_repository() -> TradingAlertRepository:
    return TradingAlertRepository()
