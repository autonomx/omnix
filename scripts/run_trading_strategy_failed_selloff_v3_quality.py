from __future__ import annotations

"""Cache-only V3 research: entry quality and risk geometry for failed-selloff V2.

The V2 structure finally generated trades, but its first genuinely unseen block
exposed a different failure mode: a nominal selloff-low stop can gap through and
realize much worse than -1R on volatile low-priced names.  This diagnostic keeps
the V2 causal structure fixed and only studies information available at signal
time:

* minimum instrument price,
* minimum stop/risk distance as a percentage of entry,
* minimum VWAP cushion,
* reversal-bar close location, and
* breakout margin above the immediately preceding high.

Production strategy defaults are not changed.  The 21 Jul-24..Aug-21 frozen
sessions are development evidence only; a chosen configuration must still be
frozen and tested on an earlier unseen block.
"""

import itertools
from dataclasses import dataclass
from datetime import time
from decimal import Decimal

import scripts.run_trading_strategy_failed_selloff_v2_sweep as _v2


_BASE_EVALUATE = _v2._failed_selloff_v2_evaluate
_BASE_ACTIVE_CONFIG = _v2._active_config
_ACTIVE_FILTERS = None


@dataclass(frozen=True)
class QualityVariant:
    minimum_premarket_dollar_volume: Decimal
    minimum_tod_rvol: Decimal
    selloff_min_pct: Decimal
    selloff_max_pct: Decimal
    recovery_min_pct: Decimal
    breakout_lookback_bars: int
    bars_after_low: int
    breakout_volume_ratio: Decimal
    last_entry_et: time
    reward_multiple: Decimal
    minimum_price: Decimal
    minimum_risk_pct: Decimal
    minimum_vwap_cushion_pct: Decimal
    minimum_close_location: Decimal
    minimum_breakout_margin_pct: Decimal

    @property
    def variant_id(self) -> str:
        return (
            f"v3-p{self.minimum_price}"
            f"-risk{self.minimum_risk_pct}"
            f"-vw{self.minimum_vwap_cushion_pct}"
            f"-cl{self.minimum_close_location}"
            f"-bm{self.minimum_breakout_margin_pct}"
        )


def _grid():
    # 3 * 2 * 2 * 2 * 2 = 48 deliberately small/causal variants.
    for min_risk, vwap_cushion, close_location, breakout_margin, min_price in itertools.product(
        (Decimal("3"), Decimal("5"), Decimal("7")),
        (Decimal("0"), Decimal("0.5")),
        (Decimal("0.50"), Decimal("0.75")),
        (Decimal("0"), Decimal("0.25")),
        (Decimal("0.50"), Decimal("1.00")),
    ):
        yield QualityVariant(
            minimum_premarket_dollar_volume=Decimal("100000"),
            minimum_tod_rvol=Decimal("3"),
            selloff_min_pct=Decimal("8"),
            selloff_max_pct=Decimal("25"),
            recovery_min_pct=Decimal("3"),
            breakout_lookback_bars=1,
            bars_after_low=1,
            breakout_volume_ratio=Decimal("0"),
            last_entry_et=time(11, 30),
            reward_multiple=Decimal("1.5"),
            minimum_price=min_price,
            minimum_risk_pct=min_risk,
            minimum_vwap_cushion_pct=vwap_cushion,
            minimum_close_location=close_location,
            minimum_breakout_margin_pct=breakout_margin,
        )


def _active_config(variant: QualityVariant):
    global _ACTIVE_FILTERS
    _ACTIVE_FILTERS = variant
    config, risk = _BASE_ACTIVE_CONFIG(variant)
    return config.model_copy(update={"minimum_price": variant.minimum_price}), risk


def _wait(result, reason: str):
    # A failed quality condition is not a permanent rejection: a later finalized
    # minute can satisfy it.  Returning without a signal preserves causal replay.
    return result.model_copy(update={"state": "lower_high_break", "reason_code": reason, "signal": None})


def _quality_evaluate(candidate, bars, config=None):
    result = _BASE_EVALUATE(candidate, bars, config)
    variant = _ACTIVE_FILTERS
    if variant is None or result.state != "entry_ready" or result.signal is None:
        return result

    regular = _v2._regular_bars(list(bars))
    if not regular:
        return result
    current = regular[-1]
    signal = result.signal

    if signal.entry_price <= 0:
        return _wait(result, "INVALID_ENTRY_PRICE")
    risk_pct = signal.risk_per_share / signal.entry_price * Decimal("100")
    if risk_pct < variant.minimum_risk_pct:
        return _wait(result, "RISK_DISTANCE_TOO_TIGHT")

    vwap_distance = result.features.vwap_distance_pct
    if vwap_distance is None or vwap_distance < variant.minimum_vwap_cushion_pct:
        return _wait(result, "VWAP_CUSHION_TOO_SMALL")

    bar_range = current.high - current.low
    close_location = (
        (current.close - current.low) / bar_range if bar_range > 0 else Decimal("0")
    )
    if close_location < variant.minimum_close_location:
        return _wait(result, "REVERSAL_CLOSE_LOCATION_WEAK")

    breakout_level = result.features.b1
    if breakout_level is None or breakout_level <= 0:
        return _wait(result, "BREAKOUT_REFERENCE_UNAVAILABLE")
    breakout_margin = (current.close / breakout_level - Decimal("1")) * Decimal("100")
    if breakout_margin < variant.minimum_breakout_margin_pct:
        return _wait(result, "BREAKOUT_MARGIN_TOO_SMALL")

    return result


def _rank_key(row):
    trades = row.get("trades") or []
    n = int(row["trade_count"])
    expectancy = (
        Decimal(str(row["expectancy_r"]))
        if row.get("expectancy_r") is not None
        else Decimal("-999")
    )
    worst_r = min((Decimal(str(trade["r_multiple"])) for trade in trades), default=Decimal("-999"))
    pnl = Decimal(str(row["pnl"]))
    drawdown = Decimal(str(row["max_drawdown_pct"]))
    # Prefer actual sample size and positive expectancy, while explicitly pushing
    # catastrophic stop-tail variants behind configurations whose worst observed
    # loss stayed within 1.5R on the training block.
    return (
        1 if n >= 6 and expectancy > 0 and worst_r >= Decimal("-1.5") else 0,
        1 if n >= 5 and expectancy > 0 else 0,
        min(n, 15),
        expectancy,
        worst_r,
        pnl,
        -drawdown,
    )


def main() -> int:
    _v2._grid = _grid
    _v2._active_config = _active_config
    _v2._failed_selloff_v2_evaluate = _quality_evaluate
    _v2._rank_key = _rank_key
    return _v2.main()


if __name__ == "__main__":
    raise SystemExit(main())
