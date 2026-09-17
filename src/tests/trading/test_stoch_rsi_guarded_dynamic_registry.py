from __future__ import annotations

from types import SimpleNamespace

from app.trading.strategy_dynamic_discovery import (
    INTERDAY_SUBSTRATEGIES,
    strategy_specific_score,
)


def test_guarded_stoch_rsi_is_ranked_with_interday_dynamic_candidates() -> None:
    assert "stoch-rsi-5min-guarded-v1" in INTERDAY_SUBSTRATEGIES

    characterization = SimpleNamespace(
        reversal_prior=72.0,
        market_confirmation=64.0,
        execution_quality=80.0,
    )
    assert strategy_specific_score(
        "stoch-rsi-5min-guarded-v1",
        characterization,
    ) == strategy_specific_score("stoch-rsi-5min", characterization)


def test_guarded_registry_preserves_distinct_frozen_baseline_arm() -> None:
    assert INTERDAY_SUBSTRATEGIES.count("stoch-rsi-5min") == 1
    assert INTERDAY_SUBSTRATEGIES.count("stoch-rsi-5min-guarded-v1") == 1
    assert INTERDAY_SUBSTRATEGIES.index("stoch-rsi-5min") < INTERDAY_SUBSTRATEGIES.index(
        "stoch-rsi-5min-guarded-v1"
    )
