from __future__ import annotations

"""Focused exact-engine neighborhood for failed-selloff v2 research."""

import itertools
from datetime import time
from decimal import Decimal

import scripts.run_trading_strategy_failed_selloff_v2_sweep as _v2


def _focused_grid():
    for liquidity, selloff_max, recovery, last_entry, reward in itertools.product(
        (100_000, 250_000),
        (18, 20, 25),
        (3, 5),
        (time(10, 30), time(11, 30)),
        (1.5, 2.0),
    ):
        yield _v2.Variant(
            minimum_premarket_dollar_volume=Decimal(str(liquidity)),
            minimum_tod_rvol=Decimal("3"),
            selloff_min_pct=Decimal("8"),
            selloff_max_pct=Decimal(str(selloff_max)),
            recovery_min_pct=Decimal(str(recovery)),
            breakout_lookback_bars=1,
            bars_after_low=1,
            breakout_volume_ratio=Decimal("0"),
            last_entry_et=last_entry,
            reward_multiple=Decimal(str(reward)),
        )


def main() -> int:
    _v2._grid = _focused_grid
    return _v2.main()


if __name__ == "__main__":
    raise SystemExit(main())
