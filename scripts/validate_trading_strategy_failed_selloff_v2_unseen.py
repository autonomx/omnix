from __future__ import annotations

"""Validate one frozen failed-selloff-v2 candidate on dates unused for model selection.

The configuration in this file is fixed before inspecting July 24-August 7 v2
results. It was selected from the August 10-21 evolution work and is replayed
unchanged through the normal Omnix paper execution/risk engine.
"""

import argparse
import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _backtest_module
from app.trading.strategy_backtest import BacktestSessionDataset
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)
import scripts.run_trading_strategy_failed_selloff_v2_sweep as _v2


FROZEN_VARIANT = _v2.Variant(
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
)


def parse_args():
    parser = argparse.ArgumentParser(description="Validate frozen failed-selloff v2 on unseen dates.")
    parser.add_argument("--start-date", default="2026-07-24")
    parser.add_argument("--end-date", default="2026-08-07")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v2-unseen")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    parser.add_argument("--max-hold-minutes", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _backtest_module.evaluate_gap_pullback = _v2._failed_selloff_v2_evaluate

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    dates = _trading_dates(start, end)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("250000")),
        spread,
    )
    cache = Path(args.dataset_cache_dir) / namespace
    datasets: list[BacktestSessionDataset] = []
    for session_date in dates:
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing unseen frozen dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))

    result = _v2._run_variant(
        FROZEN_VARIANT,
        datasets,
        initial_cash=initial_cash,
        spread=spread,
        max_hold_minutes=args.max_hold_minutes,
    )

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    (output / "frozen-variant.json").write_text(
        json.dumps({"variant_id": FROZEN_VARIANT.variant_id, "parameters": result["parameters"]}, indent=2) + "\n",
        encoding="utf-8",
    )

    expectancy = result["expectancy_r"] if result["expectancy_r"] is not None else "N/A"
    lines = [
        "# Failed-selloff v2 unseen-date validation",
        "",
        f"- Frozen variant: `{FROZEN_VARIANT.variant_id}`",
        f"- Validation dates: {start.isoformat()} through {end.isoformat()} ({len(datasets)} sessions)",
        "- These sessions were frozen after the August 10-21 V2 rule was selected and are not used to alter the configuration in this run.",
        "- Data fidelity: approximate reconstructed Alpaca IEX/current-listing universe; not SIP/NBBO and not a profitability guarantee.",
        f"- Trades: {result['trade_count']}",
        f"- Wins / losses: {result['win_count']} / {result['loss_count']}",
        f"- Expectancy: {expectancy}R",
        f"- P&L: ${result['pnl']}",
        f"- Return: {result['return_pct']}%",
        f"- Max drawdown: {result['max_drawdown_pct']}%",
        "",
        "## Exact trades",
        "",
    ]
    if result["trades"]:
        lines.append("| Symbol | Entry | Exit | Exit reason | R | MFE R | MAE R |")
        lines.append("|---|---|---|---|---:|---:|---:|")
        for trade in result["trades"]:
            lines.append(
                f"| {trade['instrument_id']} | {trade['entry_time']} | {trade['exit_time']} | {trade['exit_reason']} | "
                f"{trade['r_multiple']} | {trade['mfe_r']} | {trade['mae_r']} |"
            )
    else:
        lines.append("No trades on the unseen validation block.")
    lines.extend([
        "",
        "## Interpretation rule",
        "",
        "A positive result is evidence to continue developing V2, not evidence of live profitability. Promotion still requires a larger sample and prospective paper results. A negative result rejects this frozen candidate rather than triggering parameter tuning on the validation block.",
    ])
    summary = "\n".join(lines) + "\n"
    (output / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
