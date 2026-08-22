from __future__ import annotations

"""Low-fidelity older stress test for the already-frozen V11 candidate.

This script MUST NOT be used for parameter selection. The V11 candidate was
frozen before this 2026-03-31..2026-04-28 block was reconstructed. The older
block has stronger current-active-listing survivorship bias than the primary
May-August development/validation evidence, so this result is a robustness
stress signal only.
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
    parser = argparse.ArgumentParser(description="Stress frozen V11 on older reconstructed sessions.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v11-older-stress")
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

    datasets = _v11._load_block(cache, date(2026, 3, 31), date(2026, 4, 28))
    if not datasets:
        raise ValueError("older stress block contains no cached sessions")

    base = _v11._base_variant()
    _v7._result = _v8._normalized_result
    _bt.evaluate_gap_pullback = _v11._timing_evaluate
    _bt._find_trade = _v4._managed_find_trade

    row = _v11._run(base, FROZEN_GATES, datasets, initial_cash=initial_cash, spread=spread)
    worst = _v11._worst_r(row)
    descriptive_pass = (
        int(row["trade_count"]) >= 3
        and _v11._decimal(row.get("expectancy_r")) > 0
        and _v11._decimal(row.get("pnl"), "0") > 0
        and worst > Decimal("-1.75")
        and _v11._decimal(row.get("max_drawdown_pct"), "999") < Decimal("2")
    )

    payload = {
        "candidate_id": _v11._variant_id(FROZEN_GATES),
        "candidate_frozen_before_block_reconstruction": True,
        "stress_window": "2026-03-31..2026-04-28",
        "session_count": len(datasets),
        "fidelity": "older_reconstructed_iex_stress_only",
        "warning": "Stronger current-active-listing survivorship bias; do not retune V11 from this result.",
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
        "descriptive_stress_rule_pass": descriptive_pass,
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stress.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Frozen V11 older reconstructed stress test",
        "",
        "No parameter search or fallback is performed. This block is lower fidelity and must not be used to retune V11.",
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
        f"- Descriptive stress rule: {'PASS' if descriptive_pass else 'FAIL'}",
        "- Fidelity: older reconstructed Alpaca IEX; stronger survivorship/listing bias than the primary evidence.",
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