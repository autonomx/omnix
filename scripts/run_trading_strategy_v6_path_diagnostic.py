from __future__ import annotations

"""Diagnostic-only path analysis for the highest-precision V6 variant.

This script does not search, select, or authorize a strategy. It replays the
predeclared V6 `micro_2bar_ret70_final` signal on already-exposed development
data and asks why a high eventual >=30% recovery label precision does not
translate into positive R expectancy.
"""

import argparse
import json
import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.trading.strategies.gap_pullback import _regular_bars
from app.trading.strategy_v2_qualification import frozen_v2_config
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block
import scripts.run_trading_strategy_v6_micro_acceptance as v6
import scripts.run_trading_strategy_v5_recovery_headroom as v5

_VARIANT_ID = "micro_2bar_ret70_final"
_LEVELS = (Decimal("0.50"), Decimal("0.75"), Decimal("1.00"))


def _args():
    p = argparse.ArgumentParser(description="Diagnostic-only V6 path geometry analysis.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--start-date", default="2025-01-02")
    p.add_argument("--end-date", default="2026-03-27")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--selector-source", default="/tmp/recovery_selector.py")
    p.add_argument("--minimum-coverage-ratio", default="0.98")
    p.add_argument("--minimum-covered-sessions", type=int, default=300)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _first_signal(evaluator, candidate, bars, config):
    for i in range(1, len(bars) + 1):
        result = evaluator(candidate, bars[:i], config)
        if result.state == "entry_ready" and result.signal is not None:
            return i - 1, result
        if result.state in {"rejected", "expired"}:
            return None, result
    return None, None


def _first_passage(future, entry: Decimal, risk: Decimal, level: Decimal):
    target = entry + risk * level
    stop = entry - risk
    for index, bar in enumerate(future):
        # Match pessimistic stop-before-target semantics within a bar.
        if bar.low <= stop:
            return "stop", index
        if bar.high >= target:
            return "target", index
    return "none", None


def _path_row(dataset, candidate, bars, evaluator, config):
    signal_index, result = _first_signal(evaluator, candidate, bars, config)
    if signal_index is None or result is None or result.signal is None:
        return None

    regular_prefix = list(_regular_bars(bars[: signal_index + 1]))
    if not regular_prefix:
        return None
    trough = v5._opening_trough(regular_prefix)
    if trough is None or trough <= 0:
        return None

    signal = result.signal
    entry = Decimal(signal.entry_price)
    stop = Decimal(signal.stop_price)
    risk = Decimal(signal.risk_per_share)
    if risk <= 0:
        return None

    signal_time = regular_prefix[-1].end_time
    hold_end = signal_time + timedelta(minutes=60)
    future = [bar for bar in _regular_bars(bars) if signal_time <= bar.end_time <= hold_end]
    if not future:
        return None

    future_high = max(bar.high for bar in future)
    future_low = min(bar.low for bar in future)
    recovery_pct = (future_high / trough - Decimal("1")) * Decimal("100")
    headroom_30_r = (trough * Decimal("1.30") - entry) / risk

    passages = {}
    for level in _LEVELS:
        event, index = _first_passage(future, entry, risk, level)
        passages[str(level)] = {"event": event, "bar_index": index}

    one_r_target = entry + risk
    first_one_r_index = next((i for i, bar in enumerate(future) if bar.high >= one_r_target), None)
    if first_one_r_index is None:
        mae_before_one_r = None
    else:
        lows = [bar.low for bar in future[: first_one_r_index + 1]]
        mae_before_one_r = (min(lows) - entry) / risk

    eventual_30 = recovery_pct >= Decimal("30")
    one_r_event = passages["1.00"]["event"]
    if not eventual_30:
        category = "false_recovery_label"
    elif headroom_30_r < Decimal("1"):
        category = "true_recovery_insufficient_30pct_headroom"
    elif one_r_event == "target":
        category = "true_recovery_1r_before_stop"
    elif first_one_r_index is not None:
        category = "true_recovery_1r_only_after_stop_violation"
    else:
        category = "true_recovery_never_reaches_1r_within_60m"

    return {
        "session_date": dataset.session_date.isoformat(),
        "instrument_id": candidate.instrument_id,
        "signal_time": signal_time.isoformat(),
        "entry_price": str(entry),
        "stop_price": str(stop),
        "risk_per_share": str(risk),
        "observed_trough": str(trough),
        "headroom_to_30pct_recovery_r": str(headroom_30_r),
        "future_max_recovery_from_trough_pct_60m": str(recovery_pct),
        "future_recovers_30pct_60m": eventual_30,
        "mfe_60m_r": str((future_high - entry) / risk),
        "mae_60m_r": str((future_low - entry) / risk),
        "mae_before_first_1r_r": None if mae_before_one_r is None else str(mae_before_one_r),
        "first_passage": passages,
        "diagnostic_category": category,
    }


def _mean(values):
    return sum(values) / len(values) if values else None


def main():
    args = _args()
    start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
    spread = Decimal(args.assumed_spread_bps)
    namespace, cache_basis = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    datasets, coverage = _load_block(Path(args.dataset_cache_dir) / namespace, start, end)
    requested, covered = int(coverage["requested_sessions"]), int(coverage["covered_sessions"])
    required = max(args.minimum_covered_sessions, math.ceil(requested * float(Decimal(args.minimum_coverage_ratio))))
    if covered < required:
        raise SystemExit(f"coverage {covered}/{requested} below frozen requirement {required}")

    module = v6._load_selector(args.selector_source)
    _, hold_bars, retention, all_closes = v6._variant(_VARIANT_ID)
    evaluator = v6._micro_evaluator(module, hold_bars, retention, all_closes)
    config = frozen_v2_config().model_copy(update={"reward_multiple": Decimal("1.0")})

    rows = []
    for dataset in datasets:
        for candidate in dataset.universe.candidates:
            bars = tuple(dataset.bars_by_instrument[candidate.instrument_id])
            row = _path_row(dataset, candidate, bars, evaluator, config)
            if row is not None:
                rows.append(row)

    categories = {}
    for row in rows:
        categories[row["diagnostic_category"]] = categories.get(row["diagnostic_category"], 0) + 1

    passage_summary = {}
    for level in _LEVELS:
        key = str(level)
        target_first = sum(row["first_passage"][key]["event"] == "target" for row in rows)
        stop_first = sum(row["first_passage"][key]["event"] == "stop" for row in rows)
        none = len(rows) - target_first - stop_first
        passage_summary[key] = {
            "target_before_stop": target_first,
            "stop_before_target": stop_first,
            "neither_within_60m": none,
            "target_before_stop_rate": target_first / len(rows) if rows else None,
        }

    headrooms = [Decimal(row["headroom_to_30pct_recovery_r"]) for row in rows]
    true_rows = [row for row in rows if row["future_recovers_30pct_60m"]]
    true_headrooms = [Decimal(row["headroom_to_30pct_recovery_r"]) for row in true_rows]
    true_with_1r_headroom = [row for row in true_rows if Decimal(row["headroom_to_30pct_recovery_r"]) >= Decimal("1")]

    payload = {
        "purpose": "diagnose why high V6 recovery precision fails to monetize under fixed 1R management",
        "diagnostic_only": True,
        "no_parameter_search": True,
        "production_strategy_changed": False,
        "execution_authority": False,
        "variant_id": _VARIANT_ID,
        "period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "coverage_policy": {"minimum_ratio": args.minimum_coverage_ratio, "minimum_sessions": args.minimum_covered_sessions, "required_sessions": required},
        "cache_namespace": namespace,
        "cache_basis": cache_basis,
        "signal_count": len(rows),
        "future_30pct_recovery_count_60m": len(true_rows),
        "future_30pct_recovery_precision_60m": len(true_rows) / len(rows) if rows else None,
        "mean_headroom_to_30pct_r": None if not headrooms else str(_mean(headrooms)),
        "mean_headroom_to_30pct_r_true_recoveries": None if not true_headrooms else str(_mean(true_headrooms)),
        "true_recoveries_with_at_least_1r_30pct_headroom": len(true_with_1r_headroom),
        "diagnostic_categories": categories,
        "first_passage_summary": passage_summary,
        "signals": rows,
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# V6 micro-acceptance path diagnostic",
        "",
        f"- Variant: **{_VARIANT_ID}**",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{covered}/{requested}**",
        f"- Signals: **{len(rows)}**",
        f"- >=30% recovery within 60m: **{len(true_rows)}/{len(rows)}**",
        "",
        "## First passage before -1R stop",
        "",
        "| Target | Target first | Stop first | Neither | Target-first rate |",
        "|---:|---:|---:|---:|---:|",
    ]
    for level in _LEVELS:
        item = passage_summary[str(level)]
        lines.append(
            f"| +{level}R | {item['target_before_stop']} | {item['stop_before_target']} | {item['neither_within_60m']} | {item['target_before_stop_rate']} |"
        )
    lines.extend(["", "## Diagnostic categories", ""])
    for category, count in sorted(categories.items()):
        lines.append(f"- {category}: **{count}**")
    lines.extend([
        "",
        f"Mean 30%-threshold headroom: **{payload['mean_headroom_to_30pct_r']}R**",
        f"Mean 30%-threshold headroom among true recoveries: **{payload['mean_headroom_to_30pct_r_true_recoveries']}R**",
        f"True recoveries with >=1R headroom to the 30% threshold: **{len(true_with_1r_headroom)}/{len(true_rows)}**",
        "",
    ])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
