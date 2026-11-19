from __future__ import annotations

"""Continuously refreshed causal execution-observation plane.

AI decisions consume this cache after they become actionable.  A fill is never
backfilled from a quote that existed before the model completed merely because a
later price move makes that counterfactual attractive.

A quote line that is proven live can also price a fill from the quote standing at
the moment of action: IBKR sends a quote only when it changes, so a quiet small cap's
book can stand unchanged for a minute while staying the market's book. Which basis a
fill takes depends only on the line's health, never on price.
"""

from collections import OrderedDict, deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock
from time import monotonic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .binding_authority import BindingPurpose
from .execution import ExecutionObservation

_DEFAULT_MAX_INSTRUMENTS = 512
_DEFAULT_RETENTION_SECONDS = 3600.0
_MAX_LINE_CONFIRMATIONS = 1024
# A live IBKR line's quote that stood at the trigger prices a research fill if its book is
# at most this old (owner decision 2026-11-12): quiet small caps went 14-111 s without a
# new quote, and the first-quote-after rule rejected two of every three entries.
STANDING_QUOTE_MAX_AGE_SECONDS = Decimal("30")
# How long a standing quote waits for the line check that proves it still stood.
_LINE_CONFIRMATION_GRACE_SECONDS = 15.0

SelectionBasis = Literal["first_after", "standing"]


class ExecutionObservationEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: ExecutionObservation
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("execution-plane recorded_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class LineConfirmation(BaseModel):
    """A quote line checked live: connected, subscribed, unbroken since ``up_since``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: str
    up_since: datetime
    confirmed_at: datetime

    @field_validator("up_since", "confirmed_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("line confirmation timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class CausalExecutionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    binding_id: str
    provider: str
    market_snapshot_as_of: datetime
    decision_completed_at: datetime
    actionable_at: datetime
    first_post_decision_quote_at: datetime
    quote_source_at: datetime
    quote_received_at: datetime
    capture_lag_seconds: Decimal = Field(ge=0)
    observation: ExecutionObservation
    # "standing": the quote held when the order became active, on a line proven live
    # through that moment (priced_at); first_post_decision_quote_at is then the line
    # check that proved it, and quote_age_seconds how long the book had stood.
    selection_basis: SelectionBasis = "first_after"
    priced_at: datetime | None = None
    quote_age_seconds: Decimal | None = Field(default=None, ge=0)

    @field_validator(
        "market_snapshot_as_of",
        "decision_completed_at",
        "actionable_at",
        "first_post_decision_quote_at",
        "quote_source_at",
        "quote_received_at",
    )
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("causal execution timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class ExecutionObservationPlane:
    def __init__(
        self,
        *,
        max_observations_per_instrument: int = 600,
        max_instruments: int = _DEFAULT_MAX_INSTRUMENTS,
        retention_seconds: float = _DEFAULT_RETENTION_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_observations_per_instrument < 2:
            raise ValueError("execution plane requires at least two observations")
        if max_instruments < 1 or retention_seconds <= 0:
            raise ValueError("execution plane bounds must be positive")
        self.max_observations_per_instrument = max_observations_per_instrument
        self.max_instruments = max_instruments
        self.retention_seconds = retention_seconds
        self._clock = clock
        self._lock = RLock()
        self._rows: OrderedDict[str, deque[ExecutionObservationEnvelope]] = OrderedDict()
        self._seen: dict[str, set[tuple[object, ...]]] = {}
        self._last_touched: OrderedDict[str, float] = OrderedDict()
        self._lines: dict[str, deque[LineConfirmation]] = {}

    @staticmethod
    def _identity(observation: ExecutionObservation) -> tuple[object, ...]:
        return (
            observation.binding_id,
            observation.binding_purpose,
            observation.provider,
            observation.source_time.astimezone(timezone.utc),
            observation.provider_sequence,
            observation.bid,
            observation.ask,
            observation.last,
            observation.market_data_type,
            observation.live_entitled,
            observation.contract_id,
        )

    def record(
        self,
        observation: ExecutionObservation,
        *,
        recorded_at: datetime | None = None,
    ) -> bool:
        recorded = recorded_at or datetime.now(timezone.utc)
        if recorded.tzinfo is None:
            raise ValueError("execution plane record clock must be timezone-aware")
        envelope = ExecutionObservationEnvelope(
            observation=observation,
            recorded_at=recorded,
        )
        key = self._identity(observation)
        instrument_id = observation.instrument_id
        now = self._clock()
        with self._lock:
            self._prune_expired_locked(now)
            rows = self._rows.get(instrument_id)
            if rows is not None:
                self._touch_instrument_locked(instrument_id, now)
            else:
                self._ensure_capacity_locked()
                rows = deque(maxlen=self.max_observations_per_instrument)
                self._rows[instrument_id] = rows
                self._seen[instrument_id] = set()
                self._touch_instrument_locked(instrument_id, now)
            seen = self._seen[instrument_id]
            if key in seen:
                return False
            if len(rows) == rows.maxlen and rows:
                old = rows[0]
                seen.discard(self._identity(old.observation))
            rows.append(envelope)
            seen.add(key)
        return True

    def observations(self, instrument_id: str) -> tuple[ExecutionObservationEnvelope, ...]:
        with self._lock:
            now = self._clock()
            self._prune_expired_locked(now)
            rows = self._rows.get(instrument_id)
            if rows is None:
                return ()
            self._touch_instrument_locked(instrument_id, now)
            return tuple(rows)

    def latest(
        self,
        instrument_id: str,
        *,
        as_of: datetime | None = None,
    ) -> ExecutionObservationEnvelope | None:
        cutoff = as_of.astimezone(timezone.utc) if as_of is not None else None
        rows = self.observations(instrument_id)
        eligible = [
            row
            for row in rows
            if cutoff is None or row.recorded_at <= cutoff
        ]
        return max(
            eligible,
            key=lambda row: (
                row.recorded_at,
                row.observation.source_time,
                row.observation.provider_sequence or -1,
            ),
            default=None,
        )

    def first_causal_after(
        self,
        instrument_id: str,
        *,
        decision_completed_at: datetime,
        actionable_at: datetime | None = None,
        market_snapshot_as_of: datetime | None = None,
        binding_id: str | None = None,
        purpose: BindingPurpose = "EXECUTION",
    ) -> CausalExecutionSelection | None:
        if decision_completed_at.tzinfo is None:
            raise ValueError("decision_completed_at must be timezone-aware")
        actionable = actionable_at or decision_completed_at
        if actionable.tzinfo is None:
            raise ValueError("actionable_at must be timezone-aware")
        decision_utc = decision_completed_at.astimezone(timezone.utc)
        actionable_utc = actionable.astimezone(timezone.utc)
        rows = self.observations(instrument_id)
        eligible = []
        for row in rows:
            observation = row.observation
            if observation.binding_purpose != purpose:
                continue
            if binding_id is not None and observation.binding_id != binding_id:
                continue
            # Both the market source clock and Omnix receipt/record clock must be
            # after the action became possible. This is intentionally stricter
            # than choosing a pre-decision quote from history.
            if observation.source_time.astimezone(timezone.utc) < actionable_utc:
                continue
            if row.recorded_at < actionable_utc:
                continue
            eligible.append(row)
        if not eligible:
            return None
        selected = min(
            eligible,
            key=lambda row: (
                row.recorded_at,
                row.observation.source_time,
                row.observation.provider_sequence or -1,
            ),
        )
        observation = selected.observation
        snapshot_as_of = market_snapshot_as_of or decision_completed_at
        lag = Decimal(
            str((selected.recorded_at - actionable_utc).total_seconds())
        )
        return CausalExecutionSelection(
            instrument_id=instrument_id,
            binding_id=observation.binding_id,
            provider=observation.provider,
            market_snapshot_as_of=snapshot_as_of,
            decision_completed_at=decision_utc,
            actionable_at=actionable_utc,
            first_post_decision_quote_at=selected.recorded_at,
            quote_source_at=observation.source_time,
            quote_received_at=observation.received_at,
            capture_lag_seconds=max(Decimal("0"), lag),
            observation=observation,
        )

    def confirm_line(
        self,
        instrument_id: str,
        *,
        binding_id: str,
        up_since: datetime,
        confirmed_at: datetime,
    ) -> None:
        """Record that the line was live and unbroken from ``up_since`` to ``confirmed_at``."""
        confirmation = LineConfirmation(
            binding_id=binding_id,
            up_since=up_since,
            confirmed_at=confirmed_at,
        )
        with self._lock:
            if instrument_id not in self._rows:
                return  # nothing recorded yet, so nothing for the check to vouch for
            lines = self._lines.get(instrument_id)
            if lines is None:
                lines = deque(maxlen=_MAX_LINE_CONFIRMATIONS)
                self._lines[instrument_id] = lines
            lines.append(confirmation)

    def line_confirmations(self, instrument_id: str) -> tuple[LineConfirmation, ...]:
        with self._lock:
            return tuple(self._lines.get(instrument_id, ()))

    def standing_quote(
        self,
        instrument_id: str,
        *,
        at: datetime,
        max_age_seconds: Decimal,
        purpose: BindingPurpose = "LIVE_DATA",
        provider: str = "ibkr",
    ) -> ExecutionObservationEnvelope | None:
        """The latest quote in hand at ``at``, if its book is at most ``max_age_seconds`` old."""
        moment = at.astimezone(timezone.utc)
        rows = [
            row
            for row in self.observations(instrument_id)
            if row.observation.binding_purpose == purpose
            and row.observation.provider == provider
            and row.recorded_at <= moment
            and row.observation.source_time.astimezone(timezone.utc) <= moment
        ]
        latest = max(
            rows,
            key=lambda row: (
                row.recorded_at,
                row.observation.source_time,
                row.observation.provider_sequence or -1,
            ),
            default=None,
        )
        if latest is None:
            return None
        age = Decimal(str((moment - latest.observation.source_time.astimezone(timezone.utc)).total_seconds()))
        return latest if age <= max_age_seconds else None

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()
            self._seen.clear()
            self._last_touched.clear()
            self._lines.clear()

    def _touch_instrument_locked(self, instrument_id: str, now: float) -> None:
        self._last_touched[instrument_id] = now
        self._last_touched.move_to_end(instrument_id)
        self._rows.move_to_end(instrument_id)

    def _prune_expired_locked(self, now: float) -> None:
        while self._last_touched:
            instrument_id, touched = next(iter(self._last_touched.items()))
            if now - touched <= self.retention_seconds:
                break
            self._last_touched.pop(instrument_id, None)
            self._rows.pop(instrument_id, None)
            self._seen.pop(instrument_id, None)
            self._lines.pop(instrument_id, None)

    def _ensure_capacity_locked(self) -> None:
        while len(self._rows) >= self.max_instruments:
            instrument_id, _ = self._last_touched.popitem(last=False)
            self._rows.pop(instrument_id, None)
            self._seen.pop(instrument_id, None)
            self._lines.pop(instrument_id, None)


_DEFAULT_PLANE = ExecutionObservationPlane(
    max_instruments=_DEFAULT_MAX_INSTRUMENTS,
    retention_seconds=_DEFAULT_RETENTION_SECONDS,
)


def first_causal_execution(
    plane: ExecutionObservationPlane,
    instrument_id: str,
    *,
    decision_completed_at: datetime,
    actionable_at: datetime,
    market_snapshot_as_of: datetime,
    binding_id: str | None,
    ibkr_live: bool,
    standing_max_age_seconds: Decimal | None = None,
    standing_latency_seconds: Decimal = Decimal("0"),
    now: datetime | None = None,
) -> CausalExecutionSelection | None:
    """The first quote after the decision, from IBKR's live NBBO when authorized.

    IEX's own book is thin for small caps: it can sit unchanged for minutes and
    is far wider than the market. The source is fixed by policy, never chosen by
    price, and each source still contributes only its first post-decision quote.

    With ``standing_max_age_seconds``, an authorized IBKR line proven live through the
    moment the order becomes active (the later of trigger and decision, plus
    ``standing_latency_seconds``) prices the fill from the quote standing then, at most
    that old. While that proof is pending this returns None so the caller asks again.
    """
    timing: dict[str, Any] = dict(
        decision_completed_at=decision_completed_at,
        actionable_at=actionable_at,
        market_snapshot_as_of=market_snapshot_as_of,
    )
    if ibkr_live and standing_max_age_seconds is not None:
        standing = _standing_selection(
            plane,
            instrument_id,
            max_age_seconds=standing_max_age_seconds,
            latency_seconds=standing_latency_seconds,
            now=now or datetime.now(timezone.utc),
            **timing,
        )
        if standing == "pending":
            return None
        if standing is not None:
            return standing
    if ibkr_live:
        live = plane.first_causal_after(instrument_id, purpose="LIVE_DATA", **timing)
        if live is not None and live.provider == "ibkr":
            return live
    return plane.first_causal_after(instrument_id, binding_id=binding_id, **timing)


def _standing_selection(
    plane: ExecutionObservationPlane,
    instrument_id: str,
    *,
    decision_completed_at: datetime,
    actionable_at: datetime,
    market_snapshot_as_of: datetime,
    max_age_seconds: Decimal,
    latency_seconds: Decimal,
    now: datetime,
) -> CausalExecutionSelection | Literal["pending"] | None:
    """The IBKR quote standing when the order became active, on a line proven live through it.

    The moment is the later of the trigger and the decision plus the order's latency, so the
    book never predates the decision. "pending" means the line was live at its last check but no check since that
    moment has come yet; the caller waits rather than falling back on another quote.
    """
    moment = max(actionable_at, decision_completed_at).astimezone(timezone.utc) + timedelta(
        seconds=float(latency_seconds)
    )
    standing = plane.standing_quote(instrument_id, at=moment, max_age_seconds=max_age_seconds)
    if standing is None:
        return None
    binding_id = standing.observation.binding_id
    lines = [line for line in plane.line_confirmations(instrument_id) if line.binding_id == binding_id]
    proof = min(
        (
            line
            for line in lines
            if line.up_since <= standing.recorded_at and line.confirmed_at >= moment
        ),
        key=lambda line: line.confirmed_at,
        default=None,
    )
    if proof is None:
        latest = max(lines, key=lambda line: line.confirmed_at, default=None)
        still_open = latest is not None and latest.up_since <= standing.recorded_at
        waited = (now.astimezone(timezone.utc) - moment).total_seconds()
        return "pending" if still_open and waited <= _LINE_CONFIRMATION_GRACE_SECONDS else None
    observation = standing.observation
    return CausalExecutionSelection(
        instrument_id=instrument_id,
        binding_id=binding_id,
        provider=observation.provider,
        market_snapshot_as_of=market_snapshot_as_of,
        decision_completed_at=decision_completed_at,
        actionable_at=actionable_at,
        first_post_decision_quote_at=proof.confirmed_at,
        quote_source_at=observation.source_time,
        quote_received_at=observation.received_at,
        capture_lag_seconds=Decimal("0"),
        observation=observation,
        selection_basis="standing",
        priced_at=moment,
        quote_age_seconds=Decimal(
            str((moment - observation.source_time.astimezone(timezone.utc)).total_seconds())
        ),
    )


def default_execution_observation_plane() -> ExecutionObservationPlane:
    return _DEFAULT_PLANE


def clear_default_execution_observation_plane() -> None:
    _DEFAULT_PLANE.clear()


__all__ = [
    "CausalExecutionSelection",
    "LineConfirmation",
    "STANDING_QUOTE_MAX_AGE_SECONDS",
    "clear_default_execution_observation_plane",
    "ExecutionObservationEnvelope",
    "ExecutionObservationPlane",
    "default_execution_observation_plane",
    "first_causal_execution",
]
