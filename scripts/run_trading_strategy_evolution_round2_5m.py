from __future__ import annotations

"""Focused 5-minute neighborhood for round-two strategy evolution.

This wrapper keeps the round-two train/holdout machinery but searches only the
5m/pivot-1 neighborhood, so it can run quickly while the broader 1m/5m sweep is
still evaluating.
"""

import itertools
from datetime import time
from decimal import Decimal

import scripts.run_trading_strategy_evolution_round2 as _r2


def _focused_grid():
    for (
        liquidity,
        rvol,
        impulse,
        pullback_min,
        higher_low,
        last_entry,
        pullback_volume,
        quality,
    ) in itertools.product(
        (250000, 500000),
        (3, 5),
        (2, 3),
        (3, 5),
        (-300, -200, -100, 0),
        (time(11, 30), time(13, 0)),
        (0.70, 1.00),
        (3, 4, 5),
    ):
        yield _r2.Variant(
            structure_interval="5m",
            pivot_bars=1,
            minimum_premarket_dollar_volume=Decimal(str(liquidity)),
            minimum_tod_rvol=Decimal(str(rvol)),
            opening_impulse_min_pct=Decimal(str(impulse)),
            pullback_min_pct=Decimal(str(pullback_min)),
            higher_low_buffer_bps=Decimal(str(higher_low)),
            last_entry_et=last_entry,
            pullback_volume_max_ratio=Decimal(str(pullback_volume)),
            minimum_quality_score=int(quality),
        )


def main() -> int:
    _r2._grid = _focused_grid
    return _r2.main()


if __name__ == "__main__":
    raise SystemExit(main())
