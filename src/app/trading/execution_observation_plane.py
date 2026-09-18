from __future__ import annotations

"""Continuously refreshed causal execution-observation plane.

AI decisions consume this cache after they become actionable.  A fill is never
backfilled from a quote that existed before the model completed merely because a
later price move makes that counterfactual attractive.
"""

from collections import defaultdict, deque
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .binding_authority import BindingPurpose
from .execution import ExecutionObservation


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
    def __init__(self, *, max_observations_per_instrument: int = 600) -> None:
        if max_observations_per_instrument < 2:
            raise ValueError("execution plane requires at least two observations")
        self.max_observations_per_instrument = max_observations_per_instrument
        self._lock = RLock()
        self._rows: dict[str, deque[ExecutionObservationEnvelope]] = defaultdict(
            lambda: deque(maxlen=self.max_observations_per_instrument)
        )
        self._seen: dict[str, set[tuple[object, ...]]] = defaultdict(set)

    @staticmethod
    def _identity(observation: ExecutionObservation) -> tuple[object, ...]:
        return (
            observation.binding_id,
            observation.provider,
            observation.source_time.astimezone(timezone.utc),
            observation.provider_sequence,
            observation.bid,
            observation.ask,
            observation.last,
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
        with self._lock:
            if key in self._seen[instrument_id]:
                return False
            rows = self._rows[instrument_id]
            if len(rows) == rows.maxlen and rows:
                old = rows[0]
                self._seen[instrument_id].discard(self._identity(old.observation))
            rows.append(envelope)
            self._seen[instrument_id].add(key)
        return True

    def observations(self, instrument_id: str) -> tuple[ExecutionObservationEnvelope, ...]:
        with self._lock:
            return tuple(self._rows.get(instrument_id, ()))

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

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()
            self._seen.clear()


_DEFAULT_PLANE = ExecutionObservationPlane()


def default_execution_observation_plane() -> ExecutionObservationPlane:
    return _DEFAULT_PLANE


__all__ = [
    "CausalExecutionSelection",
    "ExecutionObservationEnvelope",
    "ExecutionObservationPlane",
    "default_execution_observation_plane",
]
