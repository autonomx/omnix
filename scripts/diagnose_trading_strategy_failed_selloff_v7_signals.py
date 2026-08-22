from __future__ import annotations

"""Diagnose causal pre-entry features for the least-negative V7 structure.

This is revealed-data analysis only.  It runs one already-tested V7 variant
across the 58 development sessions and records features that were knowable when
the signal fired.  The frozen April/May external holdout is deliberately not
loaded.  No production strategy behavior changes.
"""

import argparse
import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v7_higher_low as _v7
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


_ORIGINAL_RESULT = _v7._result
_ORIGINAL_EVALUATE = _v7._higher_low_evaluate
_SIGNAL_FEATURES: dict[tuple[str, str], dict] = {}


def _normalized_result(candidate, state, reason, transitions, features, regular, signal=None):
    canonical = ["breakout_hold" if item == "breakout_hold_confirmed" else item for item in transitions]
    return _ORIGINAL_RESULT(candidate, state, reason, canonical, features, regular, signal)


def _mean(values):
    values = list(values)
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _pct(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator * Decimal("100")


def _find_index(regular, *, start=0, low=None, high=None):
    for index in range(start, len(regular)):
        if low is not None and regular[index].low == low:
            return index
        if high is not None and regular[index].high == high:
            return index
    return None


def _capture_evaluate(candidate, bars, config=None):
    result = _ORIGINAL_EVALUATE(candidate, bars, config)
    if result.signal is None or result.state != "entry_ready":
        return result

    regular = _v7._v2._regular_bars(list(bars))
    if not regular:
        return result
    current = regular[-1]
    session_date = current.end_time.astimezone(_v7._v2._ET).date().isoformat()
    key = (session_date, candidate.instrument_id)
    if key in _SIGNAL_FEATURES:
        return result

    f = result.features
    l1_idx = _find_index(regular, low=f.l1)
    b1_idx = _find_index(regular, start=(l1_idx or 0) + 1, high=f.b1)
    l2_idx = _find_index(regular, start=(b1_idx or 0) + 1, low=f.l2)

    breakout_idx = len(regular) - 2 if _v7._ACTIVE_VARIANT.require_breakout_hold else len(regular) - 1
    hold_idx = len(regular) - 1 if _v7._ACTIVE_VARIANT.require_breakout_hold else None
    breakout = regular[breakout_idx]
    hold = regular[hold_idx] if hold_idx is not None else None

    bounce_vol = None
    pullback_vol = None
    bounce_red_vol = None
    pullback_red_vol = None
    if l1_idx is not None and b1_idx is not None and b1_idx > l1_idx:
        bounce_bars = regular[l1_idx + 1 : b1_idx + 1]
        bounce_vol = _mean(bar.volume for bar in bounce_bars)
        bounce_red_vol = _mean(bar.volume for bar in bounce_bars if bar.close < bar.open)
    if b1_idx is not None and l2_idx is not None and l2_idx > b1_idx:
        pullback_bars = regular[b1_idx + 1 : l2_idx + 1]
        pullback_vol = _mean(bar.volume for bar in pullback_bars)
        pullback_red_vol = _mean(bar.volume for bar in pullback_bars if bar.close < bar.open)

    breakout_range = breakout.high - breakout.low
    hold_range = None if hold is None else hold.high - hold.low
    entry = result.signal.entry_price
    risk = result.signal.risk_per_share

    record = {
        "session_date": session_date,
        "instrument_id": candidate.instrument_id,
        "signal_time": current.end_time.isoformat(),
        "gap_pct": str(candidate.gap_pct),
        "premarket_price": str(candidate.premarket_price),
        "premarket_dollar_volume": str(candidate.premarket_dollar_volume),
        "tod_rvol": None if candidate.tod_rvol is None else str(candidate.tod_rvol),
        "l1": None if f.l1 is None else str(f.l1),
        "b1": None if f.b1 is None else str(f.b1),
        "l2": None if f.l2 is None else str(f.l2),
        "first_selloff_depth_pct": None if f.pullback_depth_pct is None else str(f.pullback_depth_pct),
        "l1_to_b1_recovery_pct": None if f.l1 is None or f.b1 is None else str((f.b1 / f.l1 - Decimal("1")) * Decimal("100")),
        "b1_to_l2_pullback_pct": None if f.b1 is None or f.l2 is None else str((f.b1 - f.l2) / f.b1 * Decimal("100")),
        "l2_above_l1_pct": None if f.l1 is None or f.l2 is None else str((f.l2 / f.l1 - Decimal("1")) * Decimal("100")),
        "entry_above_b1_pct": None if f.b1 is None else str((entry / f.b1 - Decimal("1")) * Decimal("100")),
        "entry_above_l2_pct": None if f.l2 is None else str((entry / f.l2 - Decimal("1")) * Decimal("100")),
        "vwap_distance_pct": None if f.vwap_distance_pct is None else str(f.vwap_distance_pct),
        "breakout_volume_ratio": None if f.breakout_volume_ratio is None else str(f.breakout_volume_ratio),
        "risk_pct_entry": str(risk / entry * Decimal("100")) if entry > 0 else None,
        "breakout_close_strength": None if breakout_range <= 0 else str((breakout.close - breakout.low) / breakout_range),
        "breakout_body_pct_range": None if breakout_range <= 0 else str(abs(breakout.close - breakout.open) / breakout_range * Decimal("100")),
        "hold_close_strength": None if hold is None or hold_range is None or hold_range <= 0 else str((hold.close - hold.low) / hold_range),
        "hold_return_from_breakout_close_pct": None if hold is None or breakout.close <= 0 else str((hold.close / breakout.close - Decimal("1")) * Decimal("100")),
        "hold_low_above_b1_pct": None if hold is None or f.b1 is None else str((hold.low / f.b1 - Decimal("1")) * Decimal("100")),
        "bounce_to_pullback_volume_ratio": None if bounce_vol in (None, Decimal("0")) or pullback_vol is None else str(pullback_vol / bounce_vol),
        "bounce_red_to_pullback_red_volume_ratio": None if bounce_red_vol in (None, Decimal("0")) or pullback_red_vol is None else str(pullback_red_vol / bounce_red_vol),
        "minutes_l1_to_b1": None if l1_idx is None or b1_idx is None else b1_idx - l1_idx,
        "minutes_b1_to_l2": None if b1_idx is None or l2_idx is None else l2_idx - b1_idx,
        "minutes_l2_to_signal": None if l2_idx is None else len(regular) - 1 - l2_idx,
        "entry_minute_et": current.end_time.astimezone(_v7._v2._ET).hour * 60 + current.end_time.astimezone(_v7._v2._ET).minute,
    }
    _SIGNAL_FEATURES[key] = record
    return result


def _decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _median(values):
    vals = sorted(v for v in (_decimal(x) for x in values) if v is not None)
    if not vals:
        return None
    middle = len(vals) // 2
    if len(vals) % 2:
        return vals[middle]
    return (vals[middle - 1] + vals[middle]) / Decimal("2")


def _load(cache, start, end):
    datasets = []
    for session_date in _trading_dates(start, end):
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing revealed dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))
    return datasets


def parse_args():
    parser = argparse.ArgumentParser(description="Diagnose V7 causal signal features on revealed sessions.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v7-diagnostic")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _v7._result = _normalized_result
    _bt.evaluate_gap_pullback = _capture_evaluate
    _bt._find_trade = _v4._managed_find_trade

    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread)
    cache = Path(args.dataset_cache_dir) / namespace
    blocks = [
        _load(cache, date(2026, 5, 26), date(2026, 6, 18)),
        _load(cache, date(2026, 6, 26), date(2026, 7, 23)),
        _load(cache, date(2026, 7, 24), date(2026, 8, 21)),
    ]
    datasets = [dataset for block in blocks for dataset in block]
    if len(datasets) != 58:
        raise ValueError(f"expected 58 revealed sessions, got {len(datasets)}")

    variant = next(
        variant for variant in _v7._grid()
        if variant.minimum_premarket_dollar_volume == Decimal("250000")
        and variant.higher_low_buffer_pct == Decimal("0.5")
        and variant.minimum_breakout_volume_ratio == Decimal("0.8")
        and variant.require_breakout_hold
    )
    result = _v7._run_variant(variant, datasets, initial_cash=initial_cash, spread=spread)

    trade_by_key = {}
    for trade in result["trades"]:
        entry_time = datetime.fromisoformat(str(trade["entry_time"]).replace("Z", "+00:00"))
        session_date = entry_time.astimezone(_v7._v2._ET).date().isoformat()
        trade_by_key[(session_date, trade["instrument_id"])] = trade

    records = []
    for key, feature in sorted(_SIGNAL_FEATURES.items()):
        trade = trade_by_key.get(key)
        row = dict(feature)
        row.update(
            {
                "traded": trade is not None,
                "r_multiple": None if trade is None else str(trade["r_multiple"]),
                "pnl_per_share": None if trade is None else str(trade["pnl_per_share"]),
                "exit_reason": None if trade is None else trade["exit_reason"],
                "mfe_r": None if trade is None else str(trade.get("mfe_r")),
                "mae_r": None if trade is None else str(trade.get("mae_r")),
            }
        )
        records.append(row)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "diagnostic.json").write_text(json.dumps({"variant_id": variant.variant_id, "backtest": result, "signals": records}, indent=2, default=str) + "\n", encoding="utf-8")
    if records:
        fields = list(records[0].keys())
        with (output / "signals.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)

    traded = [row for row in records if row["traded"]]
    winners = [row for row in traded if _decimal(row["r_multiple"]) is not None and _decimal(row["r_multiple"]) > 0]
    losers = [row for row in traded if _decimal(row["r_multiple"]) is not None and _decimal(row["r_multiple"]) <= 0]
    feature_names = [
        "gap_pct",
        "premarket_dollar_volume",
        "tod_rvol",
        "first_selloff_depth_pct",
        "l1_to_b1_recovery_pct",
        "b1_to_l2_pullback_pct",
        "l2_above_l1_pct",
        "entry_above_b1_pct",
        "entry_above_l2_pct",
        "vwap_distance_pct",
        "breakout_volume_ratio",
        "risk_pct_entry",
        "breakout_close_strength",
        "breakout_body_pct_range",
        "hold_close_strength",
        "hold_return_from_breakout_close_pct",
        "hold_low_above_b1_pct",
        "bounce_to_pullback_volume_ratio",
        "bounce_red_to_pullback_red_volume_ratio",
        "minutes_l1_to_b1",
        "minutes_b1_to_l2",
        "minutes_l2_to_signal",
        "entry_minute_et",
    ]

    lines = [
        "# V7 causal signal diagnostic",
        "",
        f"- Variant: `{variant.variant_id}`",
        "- Data: 58 already-revealed development sessions only; April/May external holdout excluded.",
        f"- Trades: {len(traded)}; winners: {len(winners)}; non-winners: {len(losers)}",
        f"- Expectancy: {result['expectancy_r']}R; P&L: {result['pnl']}",
        "",
        "## Winner vs loser pre-entry medians",
        "",
        "| Feature | Winners | Non-winners |",
        "|---|---:|---:|",
    ]
    for name in feature_names:
        lines.append(f"| {name} | {_median(row.get(name) for row in winners)} | {_median(row.get(name) for row in losers)} |")
    lines.extend(["", "## Exact trades", "", "| Date | Symbol | R | MFE R | MAE R | Exit |", "|---|---|---:|---:|---:|---|"])
    for row in traded:
        lines.append(f"| {row['session_date']} | {row['instrument_id']} | {row['r_multiple']} | {row['mfe_r']} | {row['mae_r']} | {row['exit_reason']} |")
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
