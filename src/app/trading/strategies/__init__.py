from __future__ import annotations

from . import gap_pullback as _gap_pullback
from .failed_selloff_v2 import evaluate_gap_pullback_v2
from .models import (
    GapPullbackConfig,
    GapPullbackFeatures,
    GapPullbackResult,
    GapPullbackState,
    StrategyMode,
    StrategyRiskProfile,
    StrategySignal,
)


_evaluate_gap_pullback_v1 = _gap_pullback.evaluate_gap_pullback


def evaluate_gap_pullback(candidate, bars, config=None):
    """Version dispatcher that leaves all 1.x market-structure code unchanged."""
    active = config or GapPullbackConfig()
    if active.strategy_version == "2.0.0":
        return evaluate_gap_pullback_v2(candidate, bars, active)
    return _evaluate_gap_pullback_v1(candidate, bars, active)


# Existing callers import directly from ``strategies.gap_pullback``. Installing
# the dispatcher on the loaded submodule keeps those imports backward compatible
# without editing the mature 1.x evaluator itself.
_gap_pullback.evaluate_gap_pullback = evaluate_gap_pullback
session_vwap = _gap_pullback.session_vwap


__all__ = [
    "GapPullbackConfig",
    "GapPullbackFeatures",
    "GapPullbackResult",
    "GapPullbackState",
    "StrategyMode",
    "StrategyRiskProfile",
    "StrategySignal",
    "evaluate_gap_pullback",
    "evaluate_gap_pullback_v2",
    "session_vwap",
]
