from __future__ import annotations

"""Validate the frozen V5 cross-regime candidate on a new untouched block."""

import argparse
import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v5_confirmation as _v5
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate frozen V5 failed-selloff candidate.")
    p.add_argument("--start-date", default="2026-05-26")
    p.add_argument("--end-date", default="2026-06-18")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--output-dir", default="artifacts/failed-selloff-v5-unseen")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="40")
    return p.parse_args()


def _frozen_variant() -> _v5.ConfirmationVariant:
    # Frozen from the Jul-24..Aug-21 three-block V5 development ranking.
    return _v5.ConfirmationVariant(
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
        confirmation_mode="close",
        hold_close_margin_pct=Decimal("0"),
    )


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    dates = _trading_dates(start, end)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    if not dates:
        raise ValueError("validation range contains no sessions")

    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    cache = Path(args.dataset_cache_dir) / namespace
    datasets = []
    for session_date in dates:
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(
                f"missing frozen V5 validation dataset {path}; validation must not call providers"
            )
        datasets.append(_load_cached_dataset(path, session_date))

    variant = _frozen_variant()
    _bt.evaluate_gap_pullback = _v5._confirmation_evaluate
    _bt._find_trade = _v4._managed_find_trade
    result = _v5._run_variant(
        variant,
        datasets,
        initial_cash=initial_cash,
        spread=spread,
    )

    trades = result.get("trades") or []
    r_values = [Decimal(str(t["r_multiple"])) for t in trades]
    worst = min(r_values) if r_values else None
    best = max(r_values) if r_values else None

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "frozen_variant": variant.variant_id,
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
        "worst_trade_r": None if worst is None else str(worst),
        "best_trade_r": None if best is None else str(best),
        "parameters": {
            "premarket_dollar_volume_min": "100000",
            "tod_rvol_min_when_numeric": "3",
            "selloff_pct": "8-25",
            "recovery_min_pct": "3",
            "confirmation": "one later finalized 1m close remains above broken high and VWAP",
            "reward_multiple": "1.5",
            "profit_protection_trigger_r": "0.75",
            "protected_stop_r": "0.25",
            "max_hold_minutes": 60,
        },
        "candidate_outcomes": result["candidate_outcomes"],
        "trades": trades,
        "days": result["days"],
    }
    (output / "validation.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )

    lines = [
        "# Failed-selloff V5 untouched validation",
        "",
        f"- Frozen variant: `{variant.variant_id}`",
        f"- Validation dates: {start.isoformat()} through {end.isoformat()} ({len(datasets)} sessions)",
        "- These dates are not used in V5 selection or tuning.",
        "- Entry requires the failed-selloff breakout plus one later finalized 1m close holding above the broken high and VWAP.",
        "- After a prior finalized bar reaches +0.75R, the next-bar stop ratchets to +0.25R; maximum hold is 60 minutes.",
        "- Omnix pessimistic stop-before-target and gap-through fill semantics remain active.",
        "- Fidelity is approximate reconstructed Alpaca IEX/current-listing history, not SIP/NBBO.",
        f"- Trades: {result['trade_count']}",
        f"- Wins / losses: {result['win_count']} / {result['loss_count']}",
        f"- Expectancy: {result['expectancy_r'] if result['expectancy_r'] is not None else 'N/A'}R",
        f"- P&L: ${result['pnl']}",
        f"- Return: {result['return_pct']}%",
        f"- Max drawdown: {result['max_drawdown_pct']}%",
        f"- Worst trade: {str(worst) + 'R' if worst is not None else 'N/A'}",
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
    lines.extend([
        "",
        "## Decision rule",
        "",
        "Positive expectancy with a meaningful trade sample supports prospective AUTO PAPER/shadow validation only. A negative result rejects this frozen candidate; do not tune against this block.",
    ])
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
