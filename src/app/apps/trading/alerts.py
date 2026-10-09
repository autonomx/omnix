from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, ValidationError, model_validator

from app.persistence.errors import RevisionConflict
from app.security.tenant_context import RequestTenant, TenantContext
from app.security.url_policy import UrlPolicyError, check_outbound_url
from app.persistence.transaction_binding import share_transaction
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .alert_conditions import (
    MAX_ALERT_CONDITIONS,
    AlertConditionSpec,
    AlertFrequency,
    ChannelTarget,
    PriceSource,
    TrendlineAlertPoint,
    TrendlineSource,
    ValueTarget,
    condition_sources,
    legacy_conditions,
    validate_conditions_against_registry,
)
from .alerts_delivery import enqueue_alert_deliveries
from .alerts_message import message_values, render_alert_message
from .alerts_evaluation import AlertConditionOutcome, ConditionObservation, operator_met, validate_conditions_can_fire
from .indicators.engine import CORE_INDICATOR_FORMULA_VERSION

logger = logging.getLogger(__name__)


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

    # Write-only: a webhook URL can carry its token, so it is kept with the
    # secret in the protected store and never returned. Omit it on an update
    # to keep the stored one. The outbound URL policy is a write rule.
    url: str | None = Field(default=None, min_length=1, max_length=2000, exclude=True)
    # Read-only, set by the server: scheme and host of the stored URL.
    display_url: str | None = None
    # Read-only, set by the server: whether a signing secret is stored.
    has_secret: bool = False


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
    # The alert's name, for the list and the {{alert_name}} placeholder (TVP-1.5).
    name: str = Field(default="", max_length=120)
    # The drawing (and which of its levels) a line alert follows (TVP-1.4): the chart moves the alert's line with
    # the drawing. The server evaluates trendline_points as usual; these only link the alert back.
    drawing_id: str | None = Field(default=None, max_length=200)
    drawing_level: str | None = Field(default=None, max_length=100)
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


# Watchlist alerts (TVP-1.7): an alert on every symbol of a watchlist has the instrument ``watchlist:<record id>``.
WATCHLIST_INSTRUMENT_PREFIX = "watchlist:"
# The most symbols one watchlist alert evaluates; the default and each provider's own cap are lower.
WATCHLIST_SYMBOL_MAX = 1_000
WATCHLIST_SYMBOL_DEFAULT = 100


def watchlist_id_of(instrument_id: str) -> str | None:
    """The watchlist record id of a watchlist alert's instrument, or None for an ordinary alert."""
    if not instrument_id.startswith(WATCHLIST_INSTRUMENT_PREFIX):
        return None
    record_id = instrument_id[len(WATCHLIST_INSTRUMENT_PREFIX):]
    return record_id or None


def watchlist_symbols(payload: Mapping[str, Any]) -> list[str]:
    """A watchlist document's symbols, in list order and once each (``instrumentIds``, else its symbol items)."""
    raw = payload.get("instrumentIds")
    if not isinstance(raw, list):
        raw = [item.get("instrumentId") for item in payload.get("items", []) if isinstance(item, dict) and item.get("type") == "symbol"]
    symbols: list[str] = []
    for value in raw:
        if isinstance(value, str) and value and not value.startswith(WATCHLIST_INSTRUMENT_PREFIX) and value not in symbols:
            symbols.append(value)
    return symbols


class TradingAlertEvaluationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval: str = Field(default="1m", min_length=1, max_length=16)
    allow_partial_bars: bool = False
    formula_version: str = CORE_INDICATOR_FORMULA_VERSION
    # Watchlist alerts (TVP-1.7): the most symbols of the list evaluated, in list order; the server also caps it by
    # what the symbols' providers can serve each pass (``watchlist_symbol_cap``). Stored only when set.
    symbol_limit: int | None = Field(default=None, ge=1, le=WATCHLIST_SYMBOL_MAX)


def policy_json(policy: TradingAlertEvaluationPolicy) -> str:
    """The policy as stored: without unset optional fields, so alerts written before them keep the same JSON."""
    return policy.model_dump_json(exclude_none=True)


# Settings that say how an alert notifies, not when it fires. They are stored
# apart from condition_parameters (notification_settings), so editing them
# keeps the alert's trigger history.
NOTIFICATION_PARAMETER_FIELDS = ("message", "notification_channels", "delivery")


class _AlertContract(BaseModel):
    """Fields shared by stored alerts and requests.

    Validators here only normalise: reading a stored alert must never fail
    because a write rule changed. Write rules live in ``_AlertWrite``.
    """

    model_config = ConfigDict(extra="forbid")

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
    def normalize_contract(self):
        if "frequency" not in self.model_fields_set:
            self.frequency = self.parameters.trigger_policy
        self.parameters.trigger_policy = self.frequency
        if self.condition_type != "conditions" and not self.conditions:
            try:
                self.conditions = legacy_conditions(self.condition_type, self.threshold, self.parameters)
            except (ValueError, ValidationError):
                # A stored legacy alert that cannot be described has no conditions and never fires.
                self.conditions = []
        return self


class TradingAlert(_AlertContract):
    alert_id: str
    enabled: bool = True
    last_observed_price: Decimal | None = None
    last_observed_value: Decimal | None = None
    last_triggered_at: datetime | None = None
    revision: int = Field(default=1, ge=1)
    # Bumped only when what the alert watches changes (not by notification or
    # lifecycle edits); per-bar trigger keys use it.
    definition_revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # The protected-store reference of the alert's webhook; never serialised.
    _webhook_ref: str | None = PrivateAttr(default=None)

    @property
    def webhook_ref(self) -> str | None:
        return self._webhook_ref

    @property
    def watchlist_id(self) -> str | None:
        """The watchlist a watchlist alert watches (TVP-1.7): its instrument is ``watchlist:<record id>``."""
        return watchlist_id_of(self.instrument_id)

    def is_expired(self, at: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        moment = at or datetime.now(timezone.utc)
        return self.expires_at <= moment


class _AlertWrite(_AlertContract):
    # Write-only; stored in the protected secret store, never returned.
    webhook_secret: SecretStr | None = Field(default=None, max_length=500, exclude=True)

    @model_validator(mode="after")
    def validate_write(self):
        if self.evaluation_policy.formula_version != CORE_INDICATOR_FORMULA_VERSION:
            raise ValueError(
                f"unsupported alert formula version: {self.evaluation_policy.formula_version}"
            )
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        webhook = self.parameters.delivery.webhook
        if webhook is not None and webhook.url is not None:
            try:
                # HTTPS only; loopback and private hosts only where OMNIX_ALLOWED_PRIVATE_NETWORKS allows them.
                # Hostnames are resolved and checked again before every delivery (TVP-0.5a).
                webhook.url = check_outbound_url(webhook.url.strip(), strict=True, https_only=True)
            except UrlPolicyError as exc:
                raise ValueError(f"webhook url is not allowed: {exc}") from exc
        if self.condition_type == "conditions":
            if not self.conditions:
                raise ValueError("condition_type 'conditions' needs one to five conditions")
            if self.threshold != 0:
                raise ValueError("alerts described by conditions use a zero threshold")
        else:
            self._validate_legacy_fields()
            derived = legacy_conditions(self.condition_type, self.threshold, self.parameters)
            if "conditions" in self.model_fields_set and self.conditions and self.conditions != derived:
                raise ValueError(
                    "conditions disagree with the legacy condition_type; send condition_type 'conditions'"
                )
            self.conditions = derived
        if watchlist_id_of(self.instrument_id) is not None:
            # One definition for every symbol of a list: a trendline is drawn on one symbol's chart.
            if any(isinstance(source, TrendlineSource) for condition in self.conditions for source in condition_sources(condition)):
                raise ValueError("a watchlist alert cannot use a trendline")
            if self.binding_id is not None:
                raise ValueError("a watchlist alert uses each symbol's own feed, not a binding")
        elif self.evaluation_policy.symbol_limit is not None:
            raise ValueError("symbol_limit is for watchlist alerts")
        validate_conditions_against_registry(self.conditions)
        validate_conditions_can_fire(self.conditions)
        # Only "once per bar close" waits for closed bars; every other frequency
        # is intrabar, whatever an older client sends.
        self.evaluation_policy.allow_partial_bars = self.frequency != "once_per_bar_close"
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


class TradingAlertCreate(_AlertWrite):
    # No "/" or other separators: alert ids are part of protected-store references.
    alert_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


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
    frequency: str,
    outcome: AlertConditionOutcome,
    *,
    revision: int,
    definition_revision: int,
) -> str:
    """The idempotency key of a trigger.

    ``once`` has one key per alert revision, so re-enabling a fired alert
    re-arms it. The others use the definition revision, which notification
    and lifecycle edits leave alone, so such an edit cannot let the same bar
    trigger twice. The per-bar frequencies have one key per bar. ``every_time`` and ``once_per_minute`` have one per closed bar, and
    on a forming bar one per bar and observed values, so a revised or
    re-served closed bar (provider failover) cannot trigger twice. Keys live
    in PostgreSQL, so a restart cannot trigger the same thing twice either.
    """
    parts = [alert_id, frequency, str(revision if frequency == "once" else definition_revision)]
    if frequency != "once":
        parts.append(outcome.bar_start.astimezone(timezone.utc).isoformat())
    if frequency in {"every_time", "once_per_minute"}:
        if outcome.bar_is_final:
            parts.append("closed")
        else:
            parts.append("forming")
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
        volume_known=evaluation.observed_volume is not None,
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


def _split_parameters(parameters: TradingAlertParameters, webhook_ref: str | None) -> tuple[str, str]:
    """(condition_parameters, notification_settings) JSON for storage."""
    data = parameters.model_dump(mode="json")
    notification = {name: data.pop(name) for name in NOTIFICATION_PARAMETER_FIELDS}
    if webhook_ref is not None:
        notification["webhook_ref"] = webhook_ref
    return json.dumps(data), json.dumps(notification)


def _validation_reason(exc: ValidationError) -> str:
    """Where and why a stored row failed to read, without the stored values."""
    reasons = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        reasons.append(f"{location or 'alert'}: {error.get('type', 'invalid')}")
    return "; ".join(reasons) or "invalid"


def _alert(row, conditions: list[Any] | None = None) -> TradingAlert:
    # Rows are trusted on read: only normalising validators run (see _AlertContract).
    notification = dict(row[17] or {})
    webhook_ref = notification.pop("webhook_ref", None)
    alert = TradingAlert(
        alert_id=str(row[0]),
        instrument_id=str(row[1]),
        binding_id=str(row[2]) if row[2] is not None else None,
        condition_type=cast(Any, str(row[3])),
        threshold=Decimal(row[4]),
        parameters=cast(Any, {**dict(row[5] or {}), **notification}),
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
        definition_revision=int(row[18]),
        conditions=conditions or [],
    )
    alert._webhook_ref = str(webhook_ref) if webhook_ref else None
    return alert


def _stub_alert(row) -> TradingAlert:
    """The identity of a row that cannot be read, for responses about it."""
    return TradingAlert(
        alert_id=str(row[0]),
        instrument_id=str(row[1]),
        enabled=False,
        revision=int(row[13]),
        definition_revision=int(row[18]),
    )


class TradingAlertUnreadable(BaseModel):
    """A stored alert that no longer reads; archive it with its revision."""

    alert_id: str
    instrument_id: str
    revision: int
    reason: str


@dataclass(frozen=True)
class AlertLockState:
    exists: bool
    webhook_ref: str | None


@dataclass(frozen=True)
class AlertListing:
    alerts: list[TradingAlert]
    unreadable: list[TradingAlertUnreadable]


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
    revision, created_at, updated_at, frequency, notification_settings,
    definition_revision
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

    def _condition_rows(self, connection, alert_ids: Iterable[str]) -> dict[str, list[Any]]:
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
        grouped: dict[str, list[Any]] = {}
        for row in rows:
            grouped.setdefault(str(row[0]), []).append(row)
        return grouped

    def _stored_conditions(self, connection, alert_id: str) -> list[AlertConditionSpec] | None:
        """An alert's stored conditions; None when they cannot be read."""
        try:
            return [_condition(row) for row in self._condition_rows(connection, [alert_id]).get(alert_id, [])]
        except ValidationError:
            return None

    def _listing(self, connection, rows) -> AlertListing:
        condition_rows = self._condition_rows(connection, (str(row[0]) for row in rows))
        alerts: list[TradingAlert] = []
        unreadable: list[TradingAlertUnreadable] = []
        for row in rows:
            try:
                conditions = [_condition(item) for item in condition_rows.get(str(row[0]), [])]
                alerts.append(_alert(row, conditions))
            except ValidationError as exc:
                # One unreadable row (or condition row) must not hide every other
                # alert or stop the monitor; it is reported so it can be archived.
                reason = _validation_reason(exc)
                logger.warning("trading_alert_unreadable alert_id=%s reason=%s", row[0], reason)
                unreadable.append(
                    TradingAlertUnreadable(
                        alert_id=str(row[0]), instrument_id=str(row[1]), revision=int(row[13]), reason=reason
                    )
                )
        return AlertListing(alerts, unreadable)

    def _alerts(self, connection, rows) -> list[TradingAlert]:
        return self._listing(connection, rows).alerts

    def get(self, alert_id: str) -> TradingAlert | None:
        """The alert, or None when it does not exist or cannot be read."""
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                SELECT {_ALERT_COLUMNS}
                  FROM omnix_trading_alerts
                 WHERE workspace_id = %s AND alert_id = %s
                """,
                (self.context.workspace_id, alert_id),
            ).fetchone()
            if row is None:
                return None
            alerts = self._alerts(uow.connection, [row])
            return alerts[0] if alerts else None

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

    def list_alerts_report(self, limit: int = 200) -> AlertListing:
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
            return self._listing(uow.connection, rows)

    def list_alerts(self, limit: int = 200) -> list[TradingAlert]:
        return self.list_alerts_report(limit).alerts

    @contextmanager
    def alert_transaction(self, alert_id: str) -> Iterator[AlertLockState]:
        """One transaction around an alert write and its protected-store changes.

        Holds a per-(workspace, alert) PostgreSQL advisory lock across
        processes, locks the row if it exists, and yields what it currently
        references. Repository calls inside join this transaction; it commits
        when the block ends without an error.
        """
        with self.uow_factory() as uow:
            # Two keys hashed separately, so no workspace/alert pair can alias another
            # through its separators; a hash collision only serialises two writes.
            uow.connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                (f"omnix-trading-alert-workspace:{self.context.workspace_id}", alert_id),
            )
            row = uow.connection.execute(
                """
                SELECT notification_settings->>'webhook_ref'
                  FROM omnix_trading_alerts
                 WHERE workspace_id = %s AND alert_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, alert_id),
            ).fetchone()
            with share_transaction(uow):
                yield AlertLockState(exists=row is not None, webhook_ref=row[0] if row else None)
            uow.commit()

    def create(self, request: TradingAlertCreate, *, webhook_ref: str | None) -> TradingAlert:
        """Create an alert. webhook_ref names its webhook in the protected store (the API sets it)."""
        condition_parameters, notification_settings = _split_parameters(request.parameters, webhook_ref)
        with self.uow_factory() as uow:
            if uow.connection.execute(
                "SELECT 1 FROM omnix_trading_alerts WHERE workspace_id = %s AND alert_id = %s",
                (self.context.workspace_id, request.alert_id),
            ).fetchone() is not None:
                raise RevisionConflict(f"Trading alert already exists: {request.alert_id}")
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_alerts (
                    workspace_id, alert_id, owner_user_id, instrument_id, binding_id,
                    condition_type, threshold, condition_parameters, evaluation_policy,
                    cooldown_seconds, expires_at, frequency, notification_settings
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s::jsonb)
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
                    condition_parameters,
                    policy_json(request.evaluation_policy),
                    request.cooldown_seconds,
                    request.expires_at,
                    request.frequency,
                    notification_settings,
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
        *,
        webhook_ref: str | None,
    ) -> TradingAlert:
        """Replace an alert at expected_revision. webhook_ref as for create."""
        condition_parameters, notification_settings = _split_parameters(request.parameters, webhook_ref)
        with self.uow_factory() as uow:
            previous_conditions = self._stored_conditions(uow.connection, alert_id)
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_alerts
                   SET instrument_id = %s, binding_id = %s, condition_type = %s,
                       threshold = %s, condition_parameters = %s::jsonb,
                       evaluation_policy = %s::jsonb, enabled = %s,
                       cooldown_seconds = %s, expires_at = %s, frequency = %s,
                       notification_settings = %s::jsonb,
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
                    condition_parameters,
                    policy_json(request.evaluation_policy),
                    request.enabled,
                    request.cooldown_seconds,
                    request.expires_at,
                    request.frequency,
                    notification_settings,
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
                # The lifecycle trigger keeps observation history and the definition
                # revision when the alert's own columns are unchanged; a new
                # condition set is a new definition with a new history.
                row = uow.connection.execute(
                    f"""
                    UPDATE omnix_trading_alerts
                       SET last_observed_price = NULL, last_observed_value = NULL,
                           last_triggered_at = NULL,
                           definition_revision = definition_revision + 1
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
            conditions = self._stored_conditions(uow.connection, alert_id)
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
            try:
                archived = _alert(row, conditions)
            except ValidationError:
                archived = _stub_alert(row)
            return archived.model_copy(update={"enabled": False})

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
                if alert.frequency in {"once_per_bar", "once_per_bar_close"}:
                    continue  # a pushed price carries no bar
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

    def record_watchlist_outcomes(
        self,
        context: AlertEvaluationContext,
        outcomes: Iterable[AlertOutcomeRecord],
    ) -> list[TradingAlertTrigger]:
        """Watchlist alerts' outcomes on one symbol (``context.instrument_id``), with that symbol's own state (TVP-1.7).

        Frequency, cooldown and ``once`` apply per symbol: the alert stays on when one symbol fires once, and its
        trigger key names the symbol, so each symbol fires on its own.
        """
        records = list(outcomes)
        triggers: list[TradingAlertTrigger] = []
        if not records:
            return triggers
        symbol = context.instrument_id
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"""
                SELECT {_ALERT_COLUMNS}
                  FROM omnix_trading_alerts
                 WHERE workspace_id = %s AND alert_id = ANY(%s) AND enabled = TRUE
                   AND (expires_at IS NULL OR expires_at > %s)
                 ORDER BY alert_id
                 FOR UPDATE
                """,
                (self.context.workspace_id, [record.alert_id for record in records], context.evaluated_at),
            ).fetchall()
            by_alert = {record.alert_id: record for record in records}
            for alert in self._alerts(uow.connection, rows):
                record = by_alert.get(alert.alert_id)
                # An alert edited since its bars were evaluated waits for the next pass.
                if record is None or record.revision != alert.revision or alert.watchlist_id is None:
                    continue
                trigger = self._apply_symbol(uow.connection, alert, symbol, record.outcome, context)
                if trigger is not None:
                    triggers.append(trigger)
            uow.commit()
        return triggers

    def _apply_symbol(
        self,
        connection,
        alert: TradingAlert,
        symbol: str,
        outcome: AlertConditionOutcome,
        context: AlertEvaluationContext,
    ) -> TradingAlertTrigger | None:
        final_only = alert.frequency == "once_per_bar_close" or not alert.evaluation_policy.allow_partial_bars
        if final_only and not outcome.bar_is_final:
            return None
        state = connection.execute(
            """
            SELECT alert_revision, definition_revision, last_triggered_at, fired_once
              FROM omnix_trading_alert_symbol_states
             WHERE workspace_id = %s AND alert_id = %s AND instrument_id = %s
             FOR UPDATE
            """,
            (self.context.workspace_id, alert.alert_id, symbol),
        ).fetchone()
        # A state written under an older definition (or, for 'once', an older revision) starts afresh.
        current = state is not None and int(state[1]) == alert.definition_revision
        last_triggered_at = state[2] if current else None
        fired_once = current and bool(state[3]) and int(state[0]) == alert.revision
        evaluated_at = context.evaluated_at
        should_trigger = (
            outcome.met
            and not fired_once
            and not (outcome.bar_is_final and alert.updated_at is not None and outcome.bar_end <= alert.updated_at)
            and cooldown_elapsed(last_triggered_at, evaluated_at, alert.cooldown_seconds)
            and frequency_allows(alert.frequency, last_triggered_at, evaluated_at)
        )
        inserted_trigger: TradingAlertTrigger | None = None
        if should_trigger:
            # The symbol is part of the key, so each symbol of the list fires on its own.
            key = alert_trigger_key(
                f"{alert.alert_id}|{symbol}",
                alert.frequency,
                outcome,
                revision=alert.revision,
                definition_revision=alert.definition_revision,
            )
            inserted_trigger = self._record_trigger(connection, alert.model_copy(update={"instrument_id": symbol}), outcome, context, key)
            if inserted_trigger is not None:
                last_triggered_at = evaluated_at
                fired_once = alert.frequency == "once"
        connection.execute(
            """
            INSERT INTO omnix_trading_alert_symbol_states (
                workspace_id, alert_id, instrument_id, alert_revision, definition_revision,
                last_observed_price, last_observed_value, last_triggered_at, fired_once
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, alert_id, instrument_id) DO UPDATE
               SET alert_revision = EXCLUDED.alert_revision,
                   definition_revision = EXCLUDED.definition_revision,
                   last_observed_price = EXCLUDED.last_observed_price,
                   last_observed_value = COALESCE(EXCLUDED.last_observed_value, omnix_trading_alert_symbol_states.last_observed_value),
                   last_triggered_at = EXCLUDED.last_triggered_at,
                   fired_once = EXCLUDED.fired_once,
                   updated_at = CURRENT_TIMESTAMP
            """,
            (
                self.context.workspace_id, alert.alert_id, symbol, alert.revision, alert.definition_revision,
                outcome.close, outcome.primary_value, last_triggered_at, fired_once,
            ),
        )
        if inserted_trigger is not None:
            # The alert's own row shows when any of its symbols last fired.
            connection.execute(
                "UPDATE omnix_trading_alerts SET last_triggered_at = %s WHERE workspace_id = %s AND alert_id = %s",
                (evaluated_at, self.context.workspace_id, alert.alert_id),
            )
        return inserted_trigger

    def _record_trigger(
        self,
        connection,
        alert: TradingAlert,
        outcome: AlertConditionOutcome,
        context: AlertEvaluationContext,
        key: str,
    ) -> TradingAlertTrigger | None:
        """Insert a trigger with this idempotency key and its outbox rows; None when the key was already used.

        For a watchlist alert ``alert`` is a copy whose instrument is the symbol that fired (TVP-1.7).
        """
        evaluated_at = context.evaluated_at
        primary_value = outcome.primary_value
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
            "interval": context.interval,
        }
        # The message with its placeholders filled in, as every channel shows it (TVP-1.5).
        names, plots = message_values(alert, outcome, interval=context.interval, evaluated_at=evaluated_at)
        payload["message"] = render_alert_message(alert.parameters.message.strip(), names, plots)
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
            # The outbox rows commit with the trigger: no trigger is lost or delivered twice by the outbox.
            enqueue_alert_deliveries(connection, self.context.workspace_id, alert, inserted_trigger)
            return inserted_trigger
        return None

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
            key = alert_trigger_key(
                alert.alert_id,
                alert.frequency,
                outcome,
                revision=alert.revision,
                definition_revision=alert.definition_revision,
            )
            inserted_trigger = self._record_trigger(connection, alert, outcome, context, key)
            if inserted_trigger is not None:
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
