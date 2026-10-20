"""AI shadow v2/v3 research arms: one model decision per five-minute slot, and a
refused budget recorded once per session instead of an error on every poll."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.apps.trading.strategies.models import GapPullbackConfig
from app.apps.trading.strategy_ai_shadow_v2_monitor import TradingAIShadowV2Monitor
from app.apps.trading.strategy_ai_shadow_v2_roadmap_policy import _due_reasons, _record_budget_refusal
from app.apps.trading.strategy_ai_shadow_v3_monitor import TradingAIShadowV3Monitor, _alpha_decision_due
from app.apps.trading.strategy_repository import StrategyEvent, TradingStrategyConfigDocument

from .test_strategy_ai_shadow_v2_schedule_policy import INSTRUMENT, _decision_event, _structure

SLOT = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)


def _paired(own_at: datetime, pair_at: datetime) -> list[StrategyEvent]:
    return [
        _decision_event(arm="full_session_control", event_id="control", effective_state="armed", observed_at=own_at),
        _decision_event(arm="full_session_catalyst", event_id="catalyst", effective_state="armed", observed_at=pair_at),
    ]


def _reasons(events: list[StrategyEvent], at: datetime) -> tuple[str, ...]:
    return _due_reasons(
        events,
        arm="full_session_control",
        paired_arm="full_session_catalyst",
        instrument_id=INSTRUMENT,
        at=at,
        structure=_structure(),
    )


def test_v2_arm_waits_for_the_next_slot_after_deciding_in_this_one() -> None:
    decided = SLOT + timedelta(minutes=1)
    # A satisfied armed trigger used to ask again at once; now it waits for 14:05.
    assert _reasons(_paired(decided, decided), SLOT + timedelta(minutes=4)) == ()
    assert "paired_armed_trigger_satisfied" in _reasons(_paired(decided, decided), SLOT + timedelta(minutes=5))


def test_v2_slot_heartbeat_is_clock_aligned_not_five_minutes_after_each_name() -> None:
    previous = SLOT - timedelta(minutes=1)  # 13:59, the 13:55 slot
    assert "paired_five_minute_heartbeat" in _reasons(_paired(previous, previous), SLOT)


def test_v2_paired_arm_still_catches_up_within_the_slot() -> None:
    # The catalyst arm decided at 14:01; the control arm (last 13:56) has not.
    events = _paired(SLOT - timedelta(minutes=4), SLOT + timedelta(minutes=1))
    assert _reasons(events, SLOT + timedelta(minutes=2)) != ()


def test_v3_decides_once_per_name_per_slot() -> None:
    assert _alpha_decision_due(None, SLOT + timedelta(minutes=2)) is True
    assert _alpha_decision_due(SLOT, SLOT + timedelta(minutes=4)) is False
    assert _alpha_decision_due(SLOT + timedelta(minutes=4), SLOT + timedelta(minutes=5)) is True


class _Repository:
    def __init__(self) -> None:
        self.events: list[StrategyEvent] = []

    def append_event(self, event: StrategyEvent) -> bool:
        if any(existing.idempotency_key == event.idempotency_key for existing in self.events):
            return False
        self.events.append(event)
        return True


def _config() -> TradingStrategyConfigDocument:
    return TradingStrategyConfigDocument(
        strategy_id="managed-finviz-shadow-test",
        account_id="paper-test",
        strategy_version="2.0.0",
        mode="shadow",
        config=GapPullbackConfig(strategy_version="2.0.0", universe_discovery_source="finviz"),
    )


def test_v2_budget_refusal_is_recorded_once_per_session() -> None:
    monitor = TradingAIShadowV2Monitor()
    repository = _Repository()
    for minute in (0, 5, 10):
        asyncio.run(_record_budget_refusal(
            monitor, _config(), repository, now=SLOT + timedelta(minutes=minute), detail=None,
        ))

    assert monitor.budget_skip_count == 3
    assert monitor.diagnostics()["budget_skip_count"] == 3
    assert [(event.event_type, event.state, event.instrument_id) for event in repository.events] == [
        ("ai_v2_alpha_error", "budget_exhausted", "__universe__"),
    ]


def test_v3_budget_refusal_is_recorded_once_per_session() -> None:
    monitor = TradingAIShadowV3Monitor(execution_plane=object())  # type: ignore[arg-type]
    repository = _Repository()
    for minute in (0, 5):
        asyncio.run(monitor._record_budget_refusal(
            repository, _config(), session_date=SLOT.date(), now=SLOT + timedelta(minutes=minute), detail=None,
        ))

    assert monitor.budget_skip_count == 2
    assert [(event.event_type, event.state, event.instrument_id) for event in repository.events] == [
        ("ai_v3_alpha_error", "budget_exhausted", "__universe__"),
    ]
