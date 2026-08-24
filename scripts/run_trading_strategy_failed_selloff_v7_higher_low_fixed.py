from __future__ import annotations

"""Compatibility wrapper for the V7 research harness.

The first V7 run used the descriptive transition label
``breakout_hold_confirmed``.  GapPullbackResult intentionally restricts
transitions to the canonical strategy-state literals and expects
``breakout_hold``.  Normalize only that research-harness label; strategy logic,
parameters, data, fills, and ranking are unchanged.
"""

import scripts.run_trading_strategy_failed_selloff_v7_higher_low as _v7


_ORIGINAL_RESULT = _v7._result


def _normalized_result(candidate, state, reason, transitions, features, regular, signal=None):
    canonical = ["breakout_hold" if item == "breakout_hold_confirmed" else item for item in transitions]
    return _ORIGINAL_RESULT(candidate, state, reason, canonical, features, regular, signal)


def main() -> int:
    _v7._result = _normalized_result
    return _v7.main()


if __name__ == "__main__":
    raise SystemExit(main())
