from __future__ import annotations

"""Validate one frozen V3 quality/risk configuration on an untouched cache block."""

import argparse
import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _backtest_module
import scripts.run_trading_strategy_failed_selloff_v2_sweep as _v2
import scripts.run_trading_strategy_failed_selloff_v3_quality as _v3
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate one frozen failed-selloff V3 variant.")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--output-dir", default="artifacts/failed-selloff-v3-unseen")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="40")
    p.add_argument("--max-hold-minutes", type=int, default=90)
    p.add_argument("--minimum-price", required=True)
    p.add_argument("--minimum-risk-pct", required=True)
    p.add_argument("--minimum-vwap-cushion-pct", required=True)
    p.add_argument("--minimum-close-location", required=True)
    p.add_argument("--minimum-breakout-margin-pct", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    variant = _v3.QualityVariant(
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
        minimum_price=Decimal(args.minimum_price),
        minimum_risk_pct=Decimal(args.minimum_risk_pct),
        minimum_vwap_cushion_pct=Decimal(args.minimum_vwap_cushion_pct),
        minimum_close_location=Decimal(args.minimum_close_location),
        minimum_breakout_margin_pct=Decimal(args.minimum_breakout_margin_pct),
    )

    # Install the same process-local evaluator/config hooks used during V3
    # development.  No production strategy defaults are mutated.
    _v2._active_config = _v3._active_config
    _v2._failed_selloff_v2_evaluate = _v3._quality_evaluate
    _backtest_module.evaluate_gap_pullback = _v3._quality_evaluate

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    dates = _trading_dates(start, end)
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

    result = _v2._run_variant(
        variant,
        datasets,
        initial_cash=initial_cash,
        spread=spread,
        max_hold_minutes=args.max_hold_minutes,
    )
    trades = result.get("trades") or []
    worst_r = min((Decimal(str(t["r_multiple"])) for t in trades), default=None)
    max_loss_dollars = None
    if trades:
        losses = [
            Decimal(str(t["pnl_per_share"])) * Decimal(str(t["entry_fill_quantity"]))
            for t in trades
            if Decimal(str(t["pnl_per_share"])) < 0
        ]
        max_loss_dollars = min(losses) if losses else Decimal("0")

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "frozen_variant": variant.variant_id,
        "parameters": result["parameters"],
        "validation_start": args.start_date,
        "validation_end": args.end_date,
        "session_count": result["session_count"],
        "trade_count": result["trade_count"],
        "win_count": result["win_count"],
        "loss_count": result["loss_count"],
        "expectancy_r": result["expectancy_r"],
        "pnl": result["pnl"],
        "return_pct": result["return_pct"],
        "max_drawdown_pct": result["max_drawdown_pct"],
        "worst_trade_r": None if worst_r is None else str(worst_r),
        "worst_trade_pnl": None if max_loss_dollars is None else str(max_loss_dollars),
        "candidate_outcomes": result["candidate_outcomes"],
        "trades": trades,
        "days": result["days"],
    }
    (output / "validation.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Failed-selloff V3 unseen validation",
        "",
        f"- Frozen variant: `{variant.variant_id}`",
        f"- Validation dates: {args.start_date} through {args.end_date} ({len(datasets)} sessions)",
        "- Configuration is frozen for this run; this block must not be used to retune it.",
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
        "| Symbol | Entry | Exit | Exit reason | R | MFE R | MAE R |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for trade in trades:
        lines.append(
            f"| {trade['instrument_id']} | {trade['entry_time']} | {trade['exit_time']} | "
            f"{trade['exit_reason']} | {trade['r_multiple']} | {trade['mfe_r']} | {trade['mae_r']} |"
        )
    lines.extend([
        "",
        "## Interpretation rule",
        "",
        "Positive expectancy with controlled loss tails is evidence to continue prospective paper validation, not a live-profitability guarantee. A negative result rejects this frozen candidate; do not tune against this validation block.",
    ])
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
