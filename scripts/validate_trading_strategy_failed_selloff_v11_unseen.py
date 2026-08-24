from __future__ import annotations

"""Frozen unseen validation for the selected V11 timing-geometry candidate.

Candidate selection was completed using only the revealed 2026-05-26..2026-08-21
blocks.  This validator loads only the previously sealed 2026-04-29..2026-05-22
cache block and evaluates exactly one frozen candidate:

- premarket liquidity >= $100k
- V7 L1 -> B1 -> higher-L2 structure with 0.5% L2 buffer
- direct B1/VWAP break (no one-bar hold)
- no breakout-volume minimum
- entry cutoff 11:30 ET
- L1 -> B1 duration >= 4 finalized 1m bars
- L2 -> signal resolution <= 8 finalized 1m bars
- V4 causal management retained: +0.75R prior-bar trigger, next-bar +0.25R stop

No parameter search, ranking, or fallback is performed here.  Production strategy
behavior remains unchanged.
"""

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v7_higher_low as _v7
import scripts.run_trading_strategy_failed_selloff_v8_orderly_base as _v8
import scripts.run_trading_strategy_failed_selloff_v11_timing_geometry as _v11
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace


FROZEN_GATES = _v11.TimingGates(
    minimum_l1_to_b1_minutes=4,
    maximum_l2_to_signal_minutes=8,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Validate frozen V11 on unseen April/May sessions.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v11-unseen")
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

    datasets = _v11._load_block(cache, date(2026, 4, 29), date(2026, 5, 22))
    if len(datasets) != 18:
        raise ValueError(f"expected 18 sealed unseen sessions, got {len(datasets)}")

    base = _v11._base_variant()
    _v7._result = _v8._normalized_result
    _bt.evaluate_gap_pullback = _v11._timing_evaluate
    _bt._find_trade = _v4._managed_find_trade

    row = _v11._run(base, FROZEN_GATES, datasets, initial_cash=initial_cash, spread=spread)
    worst = _v11._worst_r(row)
    qualifies = (
        int(row["trade_count"]) >= 3
        and _v11._decimal(row.get("expectancy_r")) > 0
        and _v11._decimal(row.get("pnl"), "0") > 0
        and worst > Decimal("-1.75")
        and _v11._decimal(row.get("max_drawdown_pct"), "999") < Decimal("2")
    )

    payload = {
        "candidate_id": _v11._variant_id(FROZEN_GATES),
        "selection_source": "revealed 2026-05-26..2026-08-21 only",
        "validation_window": "2026-04-29..2026-05-22",
        "session_count": len(datasets),
        "parameters": {
            "minimum_premarket_dollar_volume": "100000",
            "higher_low_buffer_pct": "0.5",
            "minimum_breakout_volume_ratio": "0",
            "require_breakout_hold": False,
            "last_entry_et": "11:30:00",
            "minimum_l1_to_b1_minutes": 4,
            "maximum_l2_to_signal_minutes": 8,
            "breakeven_trigger_r": "0.75",
            "protected_stop_r": "0.25",
            "max_hold_minutes": 60,
        },
        "result": row,
        "validation_rule_pass": qualifies,
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "validation.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Frozen V11 unseen validation",
        "",
        "This run uses only the sealed 2026-04-29..2026-05-22 block. No parameter search is performed.",
        "",
        f"- Candidate: `{payload['candidate_id']}`",
        f"- Sessions: {len(datasets)}",
        f"- Trades: {row['trade_count']}",
        f"- Wins / losses: {row['win_count']} / {row['loss_count']}",
        f"- Expectancy: {row['expectancy_r']}R",
        f"- P&L: {row['pnl']}",
        f"- Return: {row['return_pct']}%",
        f"- Max drawdown: {row['max_drawdown_pct']}%",
        f"- Worst realized trade: {worst}R",
        f"- Frozen validation rule: {'PASS' if qualifies else 'FAIL'}",
        "",
        "## Trades",
        "",
        "| Symbol | Entry | Exit | R | MFE R | MAE R | Exit reason |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for trade in row.get("trades") or []:
        lines.append(
            f"| {trade['instrument_id']} | {trade['entry_time']} | {trade['exit_time']} | "
            f"{trade['r_multiple']} | {trade.get('mfe_r')} | {trade.get('mae_r')} | {trade.get('exit_reason')} |"
        )
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
