from __future__ import annotations

"""Validate one frozen V4 management rule on the untouched June/July cache block."""

import argparse
import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v2_sweep as _v2
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a frozen failed-selloff V4 management variant without retuning."
    )
    parser.add_argument("--start-date", default="2026-06-26")
    parser.add_argument("--end-date", default="2026-07-23")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v4-unseen")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def _frozen_variant() -> _v4.ManagementVariant:
    # Frozen after V4 development ranking on Jul-24..Aug-21. Do not change these
    # values in response to the June/July validation result.
    return _v4.ManagementVariant(
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
        breakeven_trigger_r=Decimal("0.75"),
        protected_stop_r=Decimal("0.25"),
        max_hold_minutes=60,
    )


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    dates = _trading_dates(start, end)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    if not dates:
        raise ValueError("validation range contains no trading sessions")

    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")),
        spread,
    )
    cache = Path(args.dataset_cache_dir) / namespace
    datasets = []
    for session_date in dates:
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing frozen unseen dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))

    variant = _frozen_variant()

    # Install the identical research-only V2 entry evaluator and V4 causal exit
    # management used during development. Production strategy code/defaults stay
    # untouched. The managed stop may depend only on prior finalized 1m bars.
    _bt.evaluate_gap_pullback = _v2._failed_selloff_v2_evaluate
    _bt._find_trade = _v4._managed_find_trade
    result = _v4._run_variant(
        variant,
        datasets,
        initial_cash=initial_cash,
        spread=spread,
        max_hold_minutes=variant.max_hold_minutes,
    )

    trades = result.get("trades") or []
    r_values = [Decimal(str(trade["r_multiple"])) for trade in trades]
    worst_r = min(r_values) if r_values else None
    best_r = max(r_values) if r_values else None

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "frozen_variant": variant.variant_id,
        "parameters": {
            **result["parameters"],
            "breakeven_trigger_r": str(variant.breakeven_trigger_r),
            "protected_stop_r": str(variant.protected_stop_r),
            "max_hold_minutes": variant.max_hold_minutes,
        },
        "validation_start": start.isoformat(),
        "validation_end": end.isoformat(),
        "session_count": len(datasets),
        "trade_count": result["trade_count"],
        "win_count": result["win_count"],
        "loss_count": result["loss_count"],
        "expectancy_r": result["expectancy_r"],
        "pnl": result["pnl"],
        "return_pct": result["return_pct"],
        "max_drawdown_pct": result["max_drawdown_pct"],
        "worst_trade_r": None if worst_r is None else str(worst_r),
        "best_trade_r": None if best_r is None else str(best_r),
        "candidate_outcomes": result["candidate_outcomes"],
        "trades": trades,
        "days": result["days"],
    }
    (output / "validation.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )

    lines = [
        "# Failed-selloff V4 untouched validation",
        "",
        f"- Frozen variant: `{variant.variant_id}`",
        f"- Validation dates: {start.isoformat()} through {end.isoformat()} ({len(datasets)} sessions)",
        "- This block was frozen before V4 was selected and is not used to change this configuration.",
        "- Entry: V2 gap-as-impulse failed-selloff structure; 1m structure/1m execution.",
        "- Management: after a prior finalized bar reaches +0.75R, next-bar stop ratchets to +0.25R; 60-minute maximum hold.",
        "- Fills remain pessimistic Omnix paper-execution-v2 with stop-before-target and gap-through handling.",
        "- Data fidelity: approximate reconstructed Alpaca IEX/current-listing universe, not SIP/NBBO.",
        f"- Trades: {result['trade_count']}",
        f"- Wins / losses: {result['win_count']} / {result['loss_count']}",
        f"- Expectancy: {result['expectancy_r'] if result['expectancy_r'] is not None else 'N/A'}R",
        f"- P&L: ${result['pnl']}",
        f"- Return: {result['return_pct']}%",
        f"- Max drawdown: {result['max_drawdown_pct']}%",
        f"- Worst trade: {str(worst_r) + 'R' if worst_r is not None else 'N/A'}",
        "",
        "## Exact trades",
        "",
        "| Symbol | Entry | Exit | Reason | R | MFE R | MAE R |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for trade in trades:
        lines.append(
            f"| {trade['instrument_id']} | {trade['entry_time']} | {trade['exit_time']} | "
            f"{trade['exit_reason']} | {trade['r_multiple']} | {trade['mfe_r']} | {trade['mae_r']} |"
        )
    lines.extend(
        [
            "",
            "## Decision rule",
            "",
            "A positive untouched result is evidence to continue with prospective AUTO PAPER/shadow validation, not a live-profitability guarantee. A negative result rejects this frozen V4 rule; do not tune against this June/July block.",
        ]
    )
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
