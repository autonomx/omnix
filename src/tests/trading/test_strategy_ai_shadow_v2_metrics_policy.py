from __future__ import annotations

from datetime import datetime, timezone

from app.trading.strategy_ai_shadow_v2_metrics_policy import _episode_metrics_policy
from app.trading.strategy_ai_shadow_v2_roadmap_policy import AI_SHADOW_V2_POLICY_VERSION
from app.trading.strategy_repository import StrategyEvent

AT = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)
INSTRUMENT = "equity:NASDAQ:TEST"


def _episode(event_id: str, *, policy_version: str, positive: bool, entered: bool) -> StrategyEvent:
    return StrategyEvent(
        strategy_id="managed_finviz_gap_pullback_v1",
        event_id=event_id,
        instrument_id=INSTRUMENT,
        event_type="ai_v2_opportunity_episode",
        state="positive" if positive else "negative",
        observed_at=AT,
        idempotency_key=event_id,
        payload={
            "arm": "full_session_catalyst",
            "policy_version": policy_version,
            "episode_id": event_id,
            "outcome": {
                "positive_opportunity": positive,
                "entered": entered,
                "peak_r": "2.5" if positive else "0.2",
                "mae_pct": "-1.0",
                "plus_two_r_before_minus_one_r": positive,
            },
        },
    )


def test_metrics_ignore_stale_policy_episodes() -> None:
    metrics = _episode_metrics_policy(
        [
            _episode("current", policy_version=AI_SHADOW_V2_POLICY_VERSION, positive=True, entered=True),
            _episode("stale", policy_version="old-policy", positive=False, entered=True),
        ],
        "full_session_catalyst",
    )

    assert metrics["episode_count"] == 1
    assert metrics["entered_episode_count"] == 1
    assert metrics["false_entry_count"] == 0
    assert metrics["good_entry_recall"] == "1"
    assert metrics["entry_precision"] == "1"
