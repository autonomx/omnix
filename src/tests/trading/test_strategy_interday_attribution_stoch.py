from __future__ import annotations

from datetime import datetime, timezone

from app.trading.strategy_dynamic_discovery import AttributionStage
from app.trading.strategy_interday_attribution import (
    _arm_for_event,
    attribution_stage_for_strategy_event,
)
from app.trading.strategy_repository import StrategyEvent


NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)


def _event(*, strategy_id: str, state: str) -> StrategyEvent:
    return StrategyEvent(
        strategy_id=strategy_id,
        event_id=f"event-{strategy_id}-{state}",
        instrument_id="equity:NASDAQ:TEST",
        event_type="stoch_rsi_5m",
        state=state,
        reason_code="fixture",
        observed_at=NOW,
        idempotency_key=f"idem-{strategy_id}-{state}",
        payload={"research_only": True, "execution_authority": False},
    )


def test_stoch_rsi_actionable_states_bridge_as_signalled() -> None:
    for state in ("entry_armed", "long_active", "exit_armed", "exited", "force_flat"):
        assert attribution_stage_for_strategy_event(
            _event(strategy_id="stoch-rsi-5min", state=state)
        ) == AttributionStage.SIGNALLED


def test_stoch_rsi_waiting_states_do_not_claim_signal() -> None:
    for state in ("waiting_data", "data_gap", "waiting_oversold", "setup_armed"):
        assert attribution_stage_for_strategy_event(
            _event(strategy_id="stoch-rsi-5min", state=state)
        ) is None


def test_guarded_child_has_distinct_parent_arm_identity() -> None:
    event = _event(strategy_id="stoch-rsi-5min-guarded-v1", state="long_active")

    assert _arm_for_event(event, event.strategy_id) == "stoch-rsi-5min-guarded-v1"
    assert attribution_stage_for_strategy_event(event) == AttributionStage.SIGNALLED
