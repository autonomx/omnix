from __future__ import annotations

"""Diagnose the causal July/August funnel for the least-restrictive V8/V9 setup.

Revealed-data diagnostic only.  The 2026-04-29..2026-05-22 external holdout is
never loaded.  We wrap every finalized-prefix evaluation so the terminal
ENTRY_WINDOW_CLOSED result cannot hide the furthest structure reached earlier in
the session.
"""

import argparse
import csv
import json
from collections import Counter
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

_STAGE_ORDER = (
    "discovered",
    "qualified_gap",
    "first_pullback",
    "first_low_confirmed",
    "bounce_high_confirmed",
    "higher_low_confirmed",
    "vwap_reclaim",
    "lower_high_break",
    "breakout_hold",
    "raw_entry_ready",
    "entry_ready",
)
_STAGE_RANK = {name: index for index, name in enumerate(_STAGE_ORDER)}
_RECORDS: dict[tuple[str, str], dict] = {}


def _session_date(bars) -> str | None:
    bars = list(bars)
    if not bars:
        return None
    return bars[-1].start_time.astimezone(_v7._v2._ET).date().isoformat()


def _capture_evaluate(candidate, bars, config=None):
    result = _v8._orderly_base_evaluate(candidate, bars, config)
    session_date = _session_date(bars)
    if session_date is None:
        return result

    key = (session_date, candidate.instrument_id)
    row = _RECORDS.setdefault(
        key,
        {
            "session_date": session_date,
            "instrument_id": candidate.instrument_id,
            "gap_pct": str(candidate.gap_pct),
            "premarket_dollar_volume": str(candidate.premarket_dollar_volume),
            "tod_rvol": None if candidate.tod_rvol is None else str(candidate.tod_rvol),
            "furthest_stage": "discovered",
            "furthest_stage_rank": 0,
            "reasons_seen": [],
            "transitions_seen": [],
            "raw_entry_ready_seen": False,
            "entry_ready_seen": False,
        },
    )

    transitions = list(result.transitions)
    for transition in transitions:
        if transition not in row["transitions_seen"]:
            row["transitions_seen"].append(transition)
        rank = _STAGE_RANK.get(transition)
        if rank is not None and rank > row["furthest_stage_rank"]:
            row["furthest_stage"] = transition
            row["furthest_stage_rank"] = rank

    reason = result.reason_code
    if reason not in row["reasons_seen"]:
        row["reasons_seen"].append(reason)

    # Any V8 quality rejection can only happen after V7 produced a causal raw
    # entry-ready signal; _reject_signal intentionally removes entry_ready from
    # the transition list before returning the rejection.
    if str(reason).startswith("V8_"):
        row["raw_entry_ready_seen"] = True
        rank = _STAGE_RANK["raw_entry_ready"]
        if rank > row["furthest_stage_rank"]:
            row["furthest_stage"] = "raw_entry_ready"
            row["furthest_stage_rank"] = rank

    if result.signal is not None and result.state == "entry_ready":
        row["raw_entry_ready_seen"] = True
        row["entry_ready_seen"] = True
        row["furthest_stage"] = "entry_ready"
        row["furthest_stage_rank"] = _STAGE_RANK["entry_ready"]

    return result


def _load_block(cache: Path):
    result = []
    for session_date in _trading_dates(date(2026, 7, 24), date(2026, 8, 21)):
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing revealed dataset: {path}")
        result.append(_load_cached_dataset(path, session_date))
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Diagnose V9 July/August causal structure funnel.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/v9-regime3-funnel")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")),
        spread,
    )
    cache = Path(args.dataset_cache_dir) / namespace
    datasets = _load_block(cache)
    if len(datasets) != 21:
        raise ValueError(f"expected 21 revealed regime-3 sessions, got {len(datasets)}")

    base, gates = next(
        (base, gates)
        for base, gates in _v8._grid()
        if base.minimum_premarket_dollar_volume == Decimal("100000")
        and gates.minimum_l1_to_b1_minutes == 3
        and gates.maximum_l2_to_signal_minutes == 16
        and gates.maximum_pullback_to_bounce_volume_ratio == Decimal("1.0")
    )
    base = replace(base, last_entry_et=time(11, 30))

    _v7._result = _v8._normalized_result
    _bt.evaluate_gap_pullback = _capture_evaluate
    _bt._find_trade = _v4._managed_find_trade

    result = _v8._run_variant(base, gates, datasets, initial_cash=initial_cash, spread=spread)

    records = sorted(_RECORDS.values(), key=lambda row: (row["session_date"], row["instrument_id"]))
    qualified = [row for row in records if "qualified_gap" in row["transitions_seen"]]
    stage_counts = Counter(row["furthest_stage"] for row in qualified)
    raw_reasons = Counter()
    for row in qualified:
        for reason in row["reasons_seen"]:
            if str(reason).startswith("V8_"):
                raw_reasons[str(reason)] += 1

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "configuration": {
            "minimum_premarket_dollar_volume": str(base.minimum_premarket_dollar_volume),
            "minimum_tod_rvol": str(base.minimum_tod_rvol),
            "higher_low_buffer_pct": str(base.higher_low_buffer_pct),
            "minimum_breakout_volume_ratio": str(base.minimum_breakout_volume_ratio),
            "require_breakout_hold": base.require_breakout_hold,
            "last_entry_et": base.last_entry_et.isoformat(),
            "minimum_l1_to_b1_minutes": gates.minimum_l1_to_b1_minutes,
            "maximum_l2_to_signal_minutes": gates.maximum_l2_to_signal_minutes,
            "maximum_pullback_to_bounce_volume_ratio": str(gates.maximum_pullback_to_bounce_volume_ratio),
            "minimum_breakout_body_pct_range": str(gates.minimum_breakout_body_pct_range),
        },
        "backtest": result,
        "qualified_candidate_count": len(qualified),
        "furthest_stage_counts": dict(stage_counts),
        "v8_reasons_seen": dict(raw_reasons),
        "candidates": records,
    }
    (output / "diagnostic.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    fields = [
        "session_date", "instrument_id", "gap_pct", "premarket_dollar_volume", "tod_rvol",
        "furthest_stage", "furthest_stage_rank", "raw_entry_ready_seen", "entry_ready_seen",
        "reasons_seen", "transitions_seen",
    ]
    with (output / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in records:
            csv_row = dict(row)
            csv_row["reasons_seen"] = "|".join(row["reasons_seen"])
            csv_row["transitions_seen"] = "|".join(row["transitions_seen"])
            writer.writerow(csv_row)

    lines = [
        "# V9 July/August causal funnel diagnostic",
        "",
        "Revealed 2026-07-24..2026-08-21 sessions only; April/May external holdout excluded.",
        "",
        f"- Total candidates observed: {len(records)}",
        f"- Candidates that passed deterministic pre-structure gates: {len(qualified)}",
        f"- Trades: {result['trade_count']}",
        "- Diagnostic setup: $100k liquidity, 11:30 ET cutoff, least-restrictive V8 timing/volume gates.",
        "",
        "## Furthest causal stage reached",
        "",
        "| Stage | Candidates |",
        "|---|---:|",
    ]
    for stage in _STAGE_ORDER:
        if stage_counts.get(stage):
            lines.append(f"| {stage} | {stage_counts[stage]} |")
    if raw_reasons:
        lines.extend(["", "## V8 quality rejections reached after a raw V7 signal", "", "| Reason | Candidates |", "|---|---:|"])
        for reason, count in raw_reasons.most_common():
            lines.append(f"| {reason} | {count} |")
    lines.extend(["", "## Candidate detail", "", "| Date | Symbol | Furthest stage | Raw signal | Final V8 signal |", "|---|---|---|---:|---:|"])
    for row in qualified:
        lines.append(
            f"| {row['session_date']} | {row['instrument_id']} | {row['furthest_stage']} | "
            f"{int(row['raw_entry_ready_seen'])} | {int(row['entry_ready_seen'])} |"
        )

    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
