from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExecutionSession = Literal["extended_pre", "regular", "extended_post", "closed", "unknown"]
ExecutionFreshness = Literal["live", "polled", "delayed", "cached", "fallback", "unknown"]


class ExecutionEligibilityPolicy(BaseModel):
    """Versioned fail-closed rules for prices that may drive paper execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["execution-data-v1"] = "execution-data-v1"
    max_age_seconds: Decimal = Field(default=Decimal("5"), gt=0, le=300)
    max_future_skew_seconds: Decimal = Field(default=Decimal("2"), ge=0, le=60)
    max_spread_bps: Decimal = Field(default=Decimal("300"), gt=0, le=10_000)
    allowed_sessions: tuple[ExecutionSession, ...] = (
        "extended_pre",
        "regular",
        "extended_post",
    )
    require_bid_ask: bool = True


class ExecutionObservation(BaseModel):
    """Normalized observation accepted by the shared paper/backtest execution layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    binding_id: str
    provider: str
    bid: Decimal | None = Field(default=None, gt=0)
    ask: Decimal | None = Field(default=None, gt=0)
    bid_size: Decimal | None = Field(default=None, ge=0)
    ask_size: Decimal | None = Field(default=None, ge=0)
    last: Decimal = Field(gt=0)
    high: Decimal | None = Field(default=None, gt=0)
    low: Decimal | None = Field(default=None, gt=0)
    bar_volume: Decimal | None = Field(default=None, ge=0)
    bar_start_time: datetime | None = None
    cumulative_volume: Decimal | None = Field(default=None, ge=0)
    source_time: datetime
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session: ExecutionSession = "unknown"
    freshness_mode: ExecutionFreshness = "unknown"
    provider_sequence: int | None = None
    halted: bool | None = None
    execution_eligible: bool = False
    rejection_reasons: tuple[str, ...] = ()
    policy_version: str = "execution-data-v1"

    @model_validator(mode="after")
    def validate_times_and_book(self):
        if self.source_time.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError("execution observation timestamps must be timezone-aware")
        if self.bar_start_time is not None and self.bar_start_time.tzinfo is None:
            raise ValueError("execution bar_start_time must be timezone-aware")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("execution bid cannot exceed ask")
        if self.high is not None and self.low is not None and self.low > self.high:
            raise ValueError("execution low cannot exceed high")
        return self

    @property
    def midpoint(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread_bps(self) -> Decimal | None:
        midpoint = self.midpoint
        if midpoint is None or midpoint <= 0:
            return None
        assert self.bid is not None and self.ask is not None
        return (self.ask - self.bid) / midpoint * Decimal("10000")

    @property
    def signed_age_seconds(self) -> Decimal:
        delta = self.received_at.astimezone(timezone.utc) - self.source_time.astimezone(timezone.utc)
        return Decimal(str(delta.total_seconds()))

    @property
    def age_seconds(self) -> Decimal:
        return max(Decimal("0"), self.signed_age_seconds)


def _time(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decimal_optional(value: object) -> Decimal | None:
    if value in {None, ""}:
        return None
    return Decimal(str(value))


def execution_observation_from_quote(
    quote: dict[str, object],
    *,
    binding_id: str,
    provider: str,
    received_at: datetime | None = None,
) -> ExecutionObservation:
    received = received_at or datetime.now(timezone.utc)
    last_value = quote.get("last", quote.get("price"))
    if last_value is None:
        raise ValueError("execution quote requires last/price")
    freshness = str(quote.get("freshness_mode") or "unknown")
    if freshness not in {"live", "polled", "delayed", "cached", "fallback", "unknown"}:
        freshness = "unknown"
    session = str(quote.get("session") or "unknown")
    if session not in {"extended_pre", "regular", "extended_post", "closed", "unknown"}:
        session = "unknown"
    halted_value = quote.get("halted")
    halted = halted_value if isinstance(halted_value, bool) else None
    return ExecutionObservation(
        instrument_id=str(quote["instrument_id"]),
        binding_id=str(quote.get("binding_id") or binding_id),
        provider=str(quote.get("provider") or provider),
        bid=_decimal_optional(quote.get("bid")),
        ask=_decimal_optional(quote.get("ask")),
        bid_size=_decimal_optional(quote.get("bid_size")),
        ask_size=_decimal_optional(quote.get("ask_size")),
        last=Decimal(str(last_value)),
        high=_decimal_optional(quote.get("high")),
        low=_decimal_optional(quote.get("low")),
        bar_volume=_decimal_optional(quote.get("bar_volume")),
        bar_start_time=(
            _time(quote.get("bar_start_time"), received)
            if quote.get("bar_start_time") not in {None, ""}
            else None
        ),
        cumulative_volume=_decimal_optional(quote.get("cumulative_volume")),
        source_time=_time(quote.get("source_time") or quote.get("received_at"), received),
        received_at=received,
        session=session,  # type: ignore[arg-type]
        freshness_mode=freshness,  # type: ignore[arg-type]
        provider_sequence=(
            int(quote["provider_sequence"])
            if quote.get("provider_sequence") is not None
            else None
        ),
        halted=halted,
    )


def assess_execution_observation(
    observation: ExecutionObservation,
    policy: ExecutionEligibilityPolicy | None = None,
) -> ExecutionObservation:
    """Return an immutable observation carrying explicit eligibility evidence."""

    active = policy or ExecutionEligibilityPolicy()
    reasons: list[str] = []
    if observation.session not in active.allowed_sessions:
        reasons.append("SESSION_NOT_EXECUTABLE")
    if observation.signed_age_seconds < -active.max_future_skew_seconds:
        reasons.append("SOURCE_TIME_IN_FUTURE")
    elif observation.age_seconds > active.max_age_seconds:
        reasons.append("STALE_MARKET_DATA")
    if active.require_bid_ask and (observation.bid is None or observation.ask is None):
        reasons.append("BID_ASK_UNAVAILABLE")
    spread = observation.spread_bps
    if spread is not None and spread > active.max_spread_bps:
        reasons.append("SPREAD_TOO_WIDE")
    if observation.freshness_mode in {"cached", "fallback", "unknown"}:
        reasons.append("NON_EXECUTION_FRESHNESS")
    if observation.halted is True:
        reasons.append("MARKET_HALTED")
    return observation.model_copy(
        update={
            "execution_eligible": not reasons,
            "rejection_reasons": tuple(reasons),
            "policy_version": active.policy_version,
        }
    )
