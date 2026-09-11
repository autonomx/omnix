from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.trading.strategy_discovery_acquisition import CausalMarketObservation
from app.trading.strategy_dynamic_discovery import (
    CandidateLifecycleState,
    DynamicCandidate,
    EvaluationTier,
    MarketAnomalyFeatures,
)
from app.trading.strategy_dynamic_discovery_monitor import (
    _candidate_snapshot_state,
    run_dynamic_discovery_once,
)
from app.trading.strategy_dynamic_discovery_repository import (
    DynamicDiscoveryEventRepository,
)


SESSION = date(2026, 9, 11)
T0 = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)


def _candidate(index: int, *, lifecycle=CandidateLifecycleState.ACTIVE) -> DynamicCandidate:
    at = T0 + timedelta(seconds=index)
    return DynamicCandidate(
        session_date=SESSION,
        instrument_id=f"equity:NASDAQ:T{index:02d}",
        first_seen_at=at,
        discovered_at=at,
        last_observed_at=at,
        lifecycle=lifecycle,
        tier=EvaluationTier.A if lifecycle != CandidateLifecycleState.EXPIRED else EvaluationTier.EXPIRED,
        attention_score=max(0, 100 - index),
        common_priority=max(0, 100 - index),
        expired_at=at if lifecycle == CandidateLifecycleState.EXPIRED else None,
    )


class _Ledger:
    def __init__(self) -> None:
        self.events = []

    def append_event(self, event):
        if any(row.idempotency_key == event.idempotency_key for row in self.events):
            return False
        self.events.append(event)
        return True

    def events_by_types_between(
        self,
        strategy_id,
        *,
        event_types,
        start_time,
        end_time,
        limit=50_000,
    ):
        return [
            row
            for row in self.events
            if row.strategy_id == strategy_id
            and row.event_type in event_types
            and start_time <= row.observed_at < end_time
        ][:limit]


class _ParentOnlyRepository:
    def get_config(self, strategy_id):
        return SimpleNamespace(enabled=True, archived_at=None)


def test_candidates_beyond_evaluation_cap_are_durably_demoted_to_watch() -> None:
    current = {_candidate(index).instrument_id: _candidate(index) for index in range(41)}
    evaluated = tuple(list(current.values())[:40])

    snapshots = _candidate_snapshot_state(current, evaluated)
    by_id = {row.instrument_id: row for row in snapshots}

    assert len(snapshots) == 41
    assert by_id["equity:NASDAQ:T40"].tier == EvaluationTier.WATCH
    assert by_id["equity:NASDAQ:T40"].strategy_ranks == {}


def test_expired_candidate_snapshot_orders_after_last_market_observation() -> None:
    ledger = _Ledger()
    repository = DynamicDiscoveryEventRepository(ledger)
    active = _candidate(1)
    assert repository.persist_candidate(active) is True

    expired_at = active.last_observed_at + timedelta(minutes=61)
    expired = active.model_copy(
        update={
            "lifecycle": CandidateLifecycleState.EXPIRED,
            "tier": EvaluationTier.EXPIRED,
            "common_priority": 0.0,
            "expired_at": expired_at,
        }
    )
    assert repository.persist_candidate(expired, snapshot_at=expired_at) is True

    latest = repository.latest_candidates(SESSION)[active.instrument_id]
    assert latest.lifecycle == CandidateLifecycleState.EXPIRED
    assert latest.tier == EvaluationTier.EXPIRED
    rows = [row for row in ledger.events if row.instrument_id == active.instrument_id]
    assert max(row.observed_at for row in rows) == expired_at


def test_explicit_causal_watermark_rejects_future_discovery_observation() -> None:
    observation_time = T0 + timedelta(seconds=1)
    observation = CausalMarketObservation(
        instrument_id="equity:NASDAQ:FUTR",
        session_date=SESSION,
        observed_at=observation_time,
        source="fixture",
        market=MarketAnomalyFeatures(
            observed_at=observation_time,
            gap_pct=30,
            tod_rvol=50,
            dollar_volume=20_000_000,
        ),
    )

    with pytest.raises(ValueError, match="future_dated"):
        asyncio.run(
            run_dynamic_discovery_once(
                now=T0,
                repository=_ParentOnlyRepository(),
                observations=(observation,),
            )
        )
