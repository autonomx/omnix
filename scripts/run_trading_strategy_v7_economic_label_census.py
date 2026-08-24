from __future__ import annotations

"""Diagnostic census for a directly economic causal label.

At the first frozen V3 recovery-watch signal, define the outcome as +1R before
-1R within 60 minutes using the same latest-five-bar structural stop. This
replaces the previously misleading eventual >=30% recovery label for successor
research. No thresholds are selected here.
"""

import argparse
import json
import math
import statistics
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

from app.trading.strategies.gap_pullback import _ET, _regular_bars
from app.trading.strategy_v2_qualification import frozen_v2_config
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block
import scripts.run_trading_strategy_v5_recovery_headroom as v5
import scripts.run_trading_strategy_v6_micro_acceptance as v6

_LEVELS = (Decimal("0.50"), Decimal("0.75"), Decimal("1.00"))
_FEATURES = (
    "gap_pct",
    "selloff_pct",
    "recovery_pct",
    "retracement_pct",
    "volume_ratio5",
    "risk_pct",
    "opening_high_headroom_r",
    "recovery_30_headroom_r",
    "vwap_distance_pct",
    "tod_rvol",
    "minutes_since_open",
    "recent_3bar_return_pct",
)


def _args():
    p = argparse.ArgumentParser(description="V7 direct-economic-label census from frozen causal caches.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--start-date", default="2025-01-02")
    p.add_argument("--end-date", default="2026-03-27")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--selector-source", default="/tmp/recovery_selector.py")
    p.add_argument("--minimum-coverage-ratio", default="0.98")
    p.add_argument("--minimum-covered-sessions", type=int, default=300)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _opening_geometry(regular):
    opening_indexes = [
        i for i, bar in enumerate(regular)
        if time(9, 30) <= bar.end_time.astimezone(_ET).time() <= time(9, 45)
    ]
    if not opening_indexes:
        return None, None
    opening_high = max(regular[i].high for i in opening_indexes)
    high_index = next((i for i in opening_indexes if regular[i].high == opening_high), None)
    if high_index is None or high_index + 1 >= len(regular):
        return opening_high, None
    trough = min(bar.low for bar in regular[high_index + 1:])
    return opening_high, trough


def _first_watch_signal(evaluator, candidate, bars, config):
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
        if bar.low <= stop:
            return "stop", index
        if bar.high >= target:
            return "target", index
    return "none", None


def _decimal_or_none(value):
    if value is None:
        return None
    return Decimal(value)


def _row(dataset, candidate, bars, evaluator, config):
    signal_index, result = _first_watch_signal(evaluator, candidate, bars, config)
    if signal_index is None or result is None or result.signal is None:
        return None
    regular = list(_regular_bars(bars[: signal_index + 1]))
    if len(regular) < 6:
        return None
    opening_high, trough = _opening_geometry(regular)
    if opening_high is None or trough is None or trough <= 0 or opening_high <= trough:
        return None

    current = regular[-1]
    entry = current.close
    prior5 = regular[-5:]
    stop = min(bar.low for bar in prior5) * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
    risk = entry - stop
    if risk <= 0:
        return None

    signal_time = current.end_time
    future = [
        bar for bar in _regular_bars(bars)
        if signal_time <= bar.end_time <= signal_time + timedelta(minutes=60)
    ]
    if not future:
        return None

    selloff_pct = (opening_high - trough) / opening_high * Decimal("100")
    recovery_pct = (entry / trough - Decimal("1")) * Decimal("100")
    retracement_pct = (entry - trough) / (opening_high - trough) * Decimal("100")
    prior_volumes = [bar.volume for bar in regular[-6:-1]]
    volume_ratio5 = current.volume / (sum(prior_volumes) / Decimal(len(prior_volumes))) if prior_volumes and sum(prior_volumes) > 0 else None
    recent_3bar_return_pct = (entry / regular[-4].close - Decimal("1")) * Decimal("100") if regular[-4].close > 0 else None
    opening_high_headroom_r = (opening_high - entry) / risk
    recovery_30_headroom_r = (trough * Decimal("1.30") - entry) / risk

    passages = {str(level): _first_passage(future, entry, risk, level) for level in _LEVELS}
    label = passages["1.00"][0] == "target"
    future_high = max(bar.high for bar in future)
    future_low = min(bar.low for bar in future)

    features = {
        "gap_pct": result.features.gap_pct,
        "selloff_pct": selloff_pct,
        "recovery_pct": recovery_pct,
        "retracement_pct": retracement_pct,
        "volume_ratio5": volume_ratio5,
        "risk_pct": risk / entry * Decimal("100"),
        "opening_high_headroom_r": opening_high_headroom_r,
        "recovery_30_headroom_r": recovery_30_headroom_r,
        "vwap_distance_pct": _decimal_or_none(result.features.vwap_distance_pct),
        "tod_rvol": _decimal_or_none(result.features.tod_rvol),
        "minutes_since_open": None if result.features.minutes_since_open is None else Decimal(result.features.minutes_since_open),
        "recent_3bar_return_pct": recent_3bar_return_pct,
    }

    return {
        "session_date": dataset.session_date.isoformat(),
        "instrument_id": candidate.instrument_id,
        "signal_time": signal_time.isoformat(),
        "entry_price": str(entry),
        "stop_price": str(stop),
        "risk_per_share": str(risk),
        "economic_label_1r_before_stop_60m": label,
        "first_passage": {
            key: {"event": event, "bar_index": index}
            for key, (event, index) in passages.items()
        },
        "mfe_60m_r": str((future_high - entry) / risk),
        "mae_60m_r": str((future_low - entry) / risk),
        "features": {key: None if value is None else str(value) for key, value in features.items()},
    }


def _segment(session_date: str):
    d = date.fromisoformat(session_date)
    if d <= date(2025, 6, 30):
        return "2025_H1"
    if d <= date(2025, 12, 31):
        return "2025_H2"
    return "2026_Q1"


def _feature_stats(rows, label):
    selected = [row for row in rows if row["economic_label_1r_before_stop_60m"] is label]
    result = {}
    for feature in _FEATURES:
        values = [Decimal(row["features"][feature]) for row in selected if row["features"].get(feature) is not None]
        result[feature] = {
            "count": len(values),
            "median": None if not values else str(statistics.median(values)),
            "mean": None if not values else str(sum(values) / len(values)),
            "min": None if not values else str(min(values)),
            "max": None if not values else str(max(values)),
        }
    return result


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
    evaluator = module._evaluator_for(v5._watch_rule(module))
    config = frozen_v2_config().model_copy(update={"reward_multiple": Decimal("1.0")})

    rows = []
    for dataset in datasets:
        for candidate in dataset.universe.candidates:
            bars = tuple(dataset.bars_by_instrument[candidate.instrument_id])
            item = _row(dataset, candidate, bars, evaluator, config)
            if item is not None:
                rows.append(item)

    positives = sum(row["economic_label_1r_before_stop_60m"] for row in rows)
    passage_summary = {}
    for level in _LEVELS:
        key = str(level)
        target = sum(row["first_passage"][key]["event"] == "target" for row in rows)
        stop = sum(row["first_passage"][key]["event"] == "stop" for row in rows)
        passage_summary[key] = {
            "target_before_stop": target,
            "stop_before_target": stop,
            "neither": len(rows) - target - stop,
            "target_before_stop_rate": target / len(rows) if rows else None,
        }

    segments = {}
    for name in ("2025_H1", "2025_H2", "2026_Q1"):
        subset = [row for row in rows if _segment(row["session_date"]) == name]
        wins = sum(row["economic_label_1r_before_stop_60m"] for row in subset)
        segments[name] = {"signals": len(subset), "wins": wins, "win_rate": wins / len(subset) if subset else None}

    payload = {
        "purpose": "replace eventual recovery label with directly economic +1R-before--1R causal label",
        "diagnostic_only": True,
        "no_threshold_search": True,
        "production_strategy_changed": False,
        "execution_authority": False,
        "watch_rule": v5._watch_rule(module).key,
        "period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "coverage_policy": {"minimum_ratio": args.minimum_coverage_ratio, "minimum_sessions": args.minimum_covered_sessions, "required_sessions": required},
        "cache_namespace": namespace,
        "cache_basis": cache_basis,
        "signal_count": len(rows),
        "economic_label_positive_count": positives,
        "economic_label_positive_rate": positives / len(rows) if rows else None,
        "first_passage_summary": passage_summary,
        "temporal_segments": segments,
        "winner_feature_stats": _feature_stats(rows, True),
        "loser_feature_stats": _feature_stats(rows, False),
        "signals": rows,
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# V7 direct economic-label census",
        "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{covered}/{requested}**",
        f"- V3 watch signals: **{len(rows)}**",
        f"- +1R before -1R within 60m: **{positives}/{len(rows)} ({payload['economic_label_positive_rate']})**",
        "",
        "## First passage",
        "",
        "| Target | Target first | Stop first | Neither | Target-first rate |",
        "|---:|---:|---:|---:|---:|",
    ]
    for level in _LEVELS:
        item = passage_summary[str(level)]
        lines.append(f"| +{level}R | {item['target_before_stop']} | {item['stop_before_target']} | {item['neither']} | {item['target_before_stop_rate']} |")
    lines.extend(["", "## Temporal stability", "", "| Block | Signals | +1R first | Rate |", "|---|---:|---:|---:|"])
    for name, item in segments.items():
        lines.append(f"| {name} | {item['signals']} | {item['wins']} | {item['win_rate']} |")
    lines.extend(["", "## Winner vs loser medians", "", "| Feature | Winner median | Loser median |", "|---|---:|---:|"])
    winner_stats, loser_stats = payload["winner_feature_stats"], payload["loser_feature_stats"]
    for feature in _FEATURES:
        lines.append(f"| {feature} | {winner_stats[feature]['median']} | {loser_stats[feature]['median']} |")
    lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
