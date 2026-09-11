from __future__ import annotations

"""Replay the discovery layer itself, before strategy replay.

Every observation is processed only at its causal timestamp.  The replay never
starts from a hindsight list of winners; callers provide the complete captured
observable population for the session.
"""

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .strategy_dynamic_discovery import (
    DEFAULT_DYNAMIC_DISCOVERY_CONFIG,
    DiscoveryEvent,
    DynamicCandidate,
    DynamicDiscoveryConfig,
    MarketAnomalyFeatures,
    catalyst_discovery_event,
    market_discovery_event,
    merge_discovery_event,
    tier_candidates,
)


class DiscoveryReplayObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    observed_at: datetime
    source: str
    source_locator: str | None = None
    market: MarketAnomalyFeatures | None = None
    catalyst_payload: dict[str, object] | None = None
    catalyst_known: bool = False

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("replay_observation_requires_timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.market is None and self.catalyst_payload is None:
            raise ValueError("replay_observation_requires_market_or_catalyst_evidence")
        if self.market is not None and self.market.observed_at > self.observed_at:
            raise ValueError("market_evidence_cannot_be_from_future")
        return self


class DiscoveryOpportunityLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    opportunity: bool
    first_actionable_at: datetime | None = None
    close_rank: int | None = Field(default=None, ge=1)

    @field_validator("first_actionable_at")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("opportunity_timestamp_requires_timezone")
        return value.astimezone(timezone.utc)


class DiscoveryReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    observation_count: int
    observable_symbol_count: int
    discovered_symbol_count: int
    first_discovered_at: dict[str, datetime]
    false_positive_symbols: tuple[str, ...] = ()
    missed_opportunity_symbols: tuple[str, ...] = ()
    discovery_recall: float | None = None
    discovery_precision: float | None = None
    median_discovery_latency_minutes: float | None = None
    fingerprint: str
    final_candidates: tuple[DynamicCandidate, ...]
    events: tuple[DiscoveryEvent, ...]


def _catalyst_object(payload: dict[str, object]):
    class _Catalyst:
        pass
    value = _Catalyst()
    for key, item in payload.items():
        setattr(value, key, item)
    return value


def _fingerprint(observations: Sequence[DiscoveryReplayObservation], config: DynamicDiscoveryConfig) -> str:
    payload = {
        "observations": [row.model_dump(mode="json") for row in observations],
        "config": config.model_dump(mode="json"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def replay_dynamic_discovery(
    *,
    session_date: date,
    observations: Sequence[DiscoveryReplayObservation],
    labels: Sequence[DiscoveryOpportunityLabel] = (),
    config: DynamicDiscoveryConfig = DEFAULT_DYNAMIC_DISCOVERY_CONFIG,
) -> DiscoveryReplayResult:
    ordered = sorted(observations, key=lambda row: (row.observed_at, row.instrument_id, row.source))
    state: dict[str, DynamicCandidate] = {}
    events: list[DiscoveryEvent] = []
    for row in ordered:
        if row.observed_at.date() not in {session_date, (row.observed_at.astimezone(timezone.utc)).date()}:
            # Date labels are exchange-local in production; do not reject UTC
            # midnight crossings here. Session-level callers own calendar scope.
            pass
        emitted: list[DiscoveryEvent] = []
        if row.market is not None:
            event = market_discovery_event(
                row.instrument_id,
                row.market,
                session_date=session_date,
                source=row.source,
                source_locator=row.source_locator,
                catalyst_known=row.catalyst_known,
                config=config,
            )
            if event is not None:
                emitted.append(event)
        if row.catalyst_payload is not None:
            event = catalyst_discovery_event(
                row.instrument_id,
                _catalyst_object(row.catalyst_payload),
                session_date=session_date,
                observed_at=row.observed_at,
                source=row.source,
                source_locator=row.source_locator,
                config=config,
            )
            if event is not None:
                emitted.append(event)
        for event in emitted:
            if event.causal_as_of > row.observed_at or event.discovered_at > row.observed_at:
                raise ValueError("replay_discovery_used_future_evidence")
            state[event.instrument_id] = merge_discovery_event(state.get(event.instrument_id), event)
            events.append(event)
        if state:
            ranked = tier_candidates(tuple(state.values()), config=config)
            for candidate in ranked:
                state[candidate.instrument_id] = candidate

    label_by_symbol = {row.instrument_id: row for row in labels}
    discovered = set(state)
    positives = {symbol for symbol, label in label_by_symbol.items() if label.opportunity}
    true_positive = discovered & positives
    false_positive = discovered - positives if labels else set()
    missed = positives - discovered
    recall = len(true_positive) / len(positives) if positives else None
    precision = len(true_positive) / len(discovered) if discovered and labels else None
    latencies: list[float] = []
    for symbol in true_positive:
        actionable = label_by_symbol[symbol].first_actionable_at
        if actionable is None:
            continue
        discovered_at = state[symbol].discovered_at
        latencies.append(max(0.0, (discovered_at - actionable).total_seconds() / 60.0))
    median = None
    if latencies:
        values = sorted(latencies)
        middle = len(values) // 2
        median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2.0

    finals = tuple(sorted(state.values(), key=lambda row: (-row.common_priority, row.instrument_id)))
    return DiscoveryReplayResult(
        session_date=session_date,
        observation_count=len(ordered),
        observable_symbol_count=len({row.instrument_id for row in ordered}),
        discovered_symbol_count=len(discovered),
        first_discovered_at={symbol: candidate.discovered_at for symbol, candidate in sorted(state.items())},
        false_positive_symbols=tuple(sorted(false_positive)),
        missed_opportunity_symbols=tuple(sorted(missed)),
        discovery_recall=recall,
        discovery_precision=precision,
        median_discovery_latency_minutes=median,
        fingerprint=_fingerprint(ordered, config),
        final_candidates=finals,
        events=tuple(events),
    )


__all__ = [
    "DiscoveryOpportunityLabel",
    "DiscoveryReplayObservation",
    "DiscoveryReplayResult",
    "replay_dynamic_discovery",
]
