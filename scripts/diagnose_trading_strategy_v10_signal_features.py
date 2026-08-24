from __future__ import annotations

"""Diagnose causal entry features for the best V10 direct higher-low variant.

This is revealed-data research only.  It replays the exact V10 $100k-liquidity,
0.5%-higher-low, zero-breakout-volume, direct-break variant with the 11:30 ET
cutoff across the three revealed development regimes.  It records only values
available at the finalized signal bar, then joins them to the paper-trade
outcome for analysis.  The frozen 2026-04-29..2026-05-22 external holdout is
never loaded.
"""

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import replace
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v7_higher_low as _v7
import scripts.run_trading_strategy_failed_selloff_v8_orderly_base as _v8
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


_RECORDS: dict[tuple[str, str], dict] = {}
_ORIGINAL_EVALUATE = _v7._higher_low_evaluate


def _variant():
    template = next(
        v for v in _v7._grid()
        if v.minimum_premarket_dollar_volume == Decimal("250000")
        and v.higher_low_buffer_pct == Decimal("0.5")
        and v.minimum_breakout_volume_ratio == Decimal("0.8")
        and v.require_breakout_hold
    )
    return replace(
        template,
        minimum_premarket_dollar_volume=Decimal("100000"),
        higher_low_buffer_pct=Decimal("0.5"),
        minimum_breakout_volume_ratio=Decimal("0"),
        require_breakout_hold=False,
        last_entry_et=time(11, 30),
    )


def _find_index(regular, value, *, low=False, start=0):
    for idx in range(start, len(regular)):
        bar_value = regular[idx].low if low else regular[idx].high
        if bar_value == value:
            return idx
    return None


def _pct(numerator, denominator):
    if denominator in (None, Decimal("0")) or numerator is None:
        return None
    return numerator / denominator * Decimal("100")


def _diagnostic_evaluate(candidate, bars, config=None):
    result = _ORIGINAL_EVALUATE(candidate, bars, config)
    if result.signal is None or result.state != "entry_ready":
        return result

    regular = _v7._v2._regular_bars(list(bars))
    if not regular:
        return result
    signal_bar = regular[-1]
    session_date = signal_bar.start_time.astimezone(_v7._v2._ET).date().isoformat()
    key = (candidate.instrument_id, session_date)
    if key in _RECORDS:
        return result

    f = result.features
    l1_idx = _find_index(regular, f.l1, low=True)
    b1_idx = _find_index(regular, f.b1, low=False, start=(l1_idx + 1 if l1_idx is not None else 0))
    l2_idx = _find_index(regular, f.l2, low=True, start=(b1_idx + 1 if b1_idx is not None else 0))
    bar_range = signal_bar.high - signal_bar.low
    risk = result.signal.entry_price - result.signal.stop_price
    minutes_from_open = int(
        (signal_bar.start_time.astimezone(_v7._v2._ET).hour * 60
         + signal_bar.start_time.astimezone(_v7._v2._ET).minute)
        - (9 * 60 + 30)
    )

    _RECORDS[key] = {
        "session_date": session_date,
        "instrument_id": candidate.instrument_id,
        "signal_time": signal_bar.end_time.isoformat(),
        "minutes_from_open": minutes_from_open,
        "gap_pct": str(candidate.gap_pct),
        "premarket_price": str(candidate.premarket_price),
        "premarket_dollar_volume": str(candidate.premarket_dollar_volume),
        "tod_rvol": None if candidate.tod_rvol is None else str(candidate.tod_rvol),
        "spread_bps": None if candidate.spread_bps is None else str(candidate.spread_bps),
        "selloff_depth_pct": None if f.pullback_depth_pct is None else str(f.pullback_depth_pct),
        "l2_above_l1_pct": None if f.l1 in (None, Decimal("0")) or f.l2 is None else str((f.l2 / f.l1 - Decimal("1")) * Decimal("100")),
        "second_pullback_depth_pct": None if f.b1 in (None, Decimal("0")) or f.l2 is None else str((f.b1 - f.l2) / f.b1 * Decimal("100")),
        "l1_to_b1_minutes": None if l1_idx is None or b1_idx is None else b1_idx - l1_idx,
        "b1_to_l2_minutes": None if b1_idx is None or l2_idx is None else l2_idx - b1_idx,
        "l2_to_signal_minutes": None if l2_idx is None else len(regular) - 1 - l2_idx,
        "vwap_distance_pct": None if f.vwap_distance_pct is None else str(f.vwap_distance_pct),
        "breakout_volume_ratio": None if f.breakout_volume_ratio is None else str(f.breakout_volume_ratio),
        "breakout_body_pct_range": None if bar_range <= 0 else str(abs(signal_bar.close - signal_bar.open) / bar_range * Decimal("100")),
        "breakout_close_location_pct": None if bar_range <= 0 else str((signal_bar.close - signal_bar.low) / bar_range * Decimal("100")),
        "risk_distance_pct": None if result.signal.entry_price <= 0 else str(risk / result.signal.entry_price * Decimal("100")),
        "entry_price": str(result.signal.entry_price),
        "stop_price": str(result.signal.stop_price),
    }
    return result


def _load_block(cache, start, end):
    rows = []
    for session_date in _trading_dates(start, end):
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing revealed dataset: {path}")
        rows.append(_load_cached_dataset(path, session_date))
    return rows


def _median(values):
    vals = sorted(Decimal(str(v)) for v in values if v is not None)
    if not vals:
        return None
    middle = len(vals) // 2
    if len(vals) % 2:
        return vals[middle]
    return (vals[middle - 1] + vals[middle]) / Decimal("2")


def _numeric(record, field):
    value = record.get(field)
    if value is None or value == "":
        return None
    return Decimal(str(value))


def parse_args():
    parser = argparse.ArgumentParser(description="Diagnose causal V10 signal features across revealed regimes.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/v10-signal-features")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    cache = Path(args.dataset_cache_dir) / namespace
    specs = [
        ("regime1", date(2026, 5, 26), date(2026, 6, 18)),
        ("regime2", date(2026, 6, 26), date(2026, 7, 23)),
        ("regime3", date(2026, 7, 24), date(2026, 8, 21)),
    ]

    variant = _variant()
    _v7._result = _v8._normalized_result
    _v7._ACTIVE_VARIANT = variant
    _v4._ACTIVE_MANAGEMENT = variant
    _bt.evaluate_gap_pullback = _diagnostic_evaluate
    _bt._find_trade = _v4._managed_find_trade

    records = []
    for regime, start, end in specs:
        _RECORDS.clear()
        datasets = _load_block(cache, start, end)
        result = _v7._run_variant(variant, datasets, initial_cash=initial_cash, spread=spread)
        trade_map = {}
        for trade in result.get("trades") or []:
            entry_date = trade["entry_time"][:10]
            trade_map[(trade["instrument_id"], entry_date)] = trade
        for key, signal in sorted(_RECORDS.items()):
            trade = trade_map.get(key)
            row = {**signal, "regime": regime}
            row["traded"] = trade is not None
            row["r_multiple"] = None if trade is None else trade["r_multiple"]
            row["mfe_r"] = None if trade is None else trade.get("mfe_r")
            row["mae_r"] = None if trade is None else trade.get("mae_r")
            row["pnl_per_share"] = None if trade is None else trade.get("pnl_per_share")
            row["exit_reason"] = None if trade is None else trade.get("exit_reason")
            records.append(row)

    feature_fields = [
        "gap_pct", "premarket_dollar_volume", "tod_rvol", "spread_bps",
        "selloff_depth_pct", "l2_above_l1_pct", "second_pullback_depth_pct",
        "l1_to_b1_minutes", "b1_to_l2_minutes", "l2_to_signal_minutes",
        "vwap_distance_pct", "breakout_volume_ratio", "breakout_body_pct_range",
        "breakout_close_location_pct", "risk_distance_pct", "minutes_from_open",
    ]

    groups = defaultdict(list)
    for row in records:
        if not row["traded"]:
            outcome = "no_trade"
        else:
            r = Decimal(str(row["r_multiple"]))
            outcome = "win" if r > 0 else "loss" if r < 0 else "flat"
        groups[(row["regime"], outcome)].append(row)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "signals.json").write_text(json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8")

    fields = [
        "regime", "session_date", "instrument_id", "signal_time", "traded", "r_multiple", "mfe_r", "mae_r", "exit_reason",
        *feature_fields,
    ]
    with (output / "signals.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    summary = {"groups": {}}
    for (regime, outcome), rows in sorted(groups.items()):
        key = f"{regime}:{outcome}"
        summary["groups"][key] = {
            "count": len(rows),
            "medians": {
                field: None if (m := _median(_numeric(row, field) for row in rows)) is None else str(m)
                for field in feature_fields
            },
        }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# V10 causal signal-feature diagnostic",
        "",
        "Revealed data only; the April/May external holdout is excluded.",
        "",
        f"- Signal rows: {len(records)}",
        f"- Traded rows: {sum(1 for row in records if row['traded'])}",
        "- Exact variant: $100k premarket liquidity, 0.5% L2 buffer, direct B1/VWAP break, no breakout-volume minimum, 11:30 ET cutoff.",
        "",
        "## Median causal features by regime/outcome",
        "",
        "| Group | N | Gap % | PM $vol | TOD RVOL | Selloff % | L2 above L1 % | 2nd pullback % | L1→B1 min | L2→signal min | VWAP dist % | Break vol | Body % | Risk % | Entry min |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, item in summary["groups"].items():
        m = item["medians"]
        lines.append(
            f"| {key} | {item['count']} | {m['gap_pct']} | {m['premarket_dollar_volume']} | {m['tod_rvol']} | "
            f"{m['selloff_depth_pct']} | {m['l2_above_l1_pct']} | {m['second_pullback_depth_pct']} | "
            f"{m['l1_to_b1_minutes']} | {m['l2_to_signal_minutes']} | {m['vwap_distance_pct']} | "
            f"{m['breakout_volume_ratio']} | {m['breakout_body_pct_range']} | {m['risk_distance_pct']} | {m['minutes_from_open']} |"
        )
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
