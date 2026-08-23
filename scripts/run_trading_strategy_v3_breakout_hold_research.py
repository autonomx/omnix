from __future__ import annotations

"""Development-only one-bar break-and-hold research using the causal cache.

A signal may occur only when the immediately prior finalized bar was the selected
path's first causal B1+VWAP breakout and the current finalized bar still closes
above both B1 and current VWAP. This is research-only, provider-free and never
loads March. Volume checkpoints remain a deliberately small robustness probe.
"""

import argparse
import json
import math
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.trading.gapper_dataset import GapperCandidate
from app.trading.models import MarketBar
from app.trading.strategies.gap_pullback import _ET, _regular_bars, session_vwap
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult, StrategySignal
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator
from scripts.run_trading_strategy_v3_first_breakout_research import evaluate_canonical_first_breakout


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test canonical one-bar breakout hold from cached development data.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2026-01-02")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--minimum-development-trades", type=int, default=5)
    parser.add_argument("--minimum-coverage-ratio", default="0.80")
    parser.add_argument("--minimum-covered-sessions", type=int, default=20)
    parser.add_argument("--output-dir", default="artifacts/v3-breakout-hold-research")
    return parser.parse_args()


def evaluate_canonical_break_hold(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
) -> GapPullbackResult:
    raw = list(bars)
    regular = _regular_bars(raw)
    if len(regular) < 2:
        result = evaluate_canonical_first_breakout(candidate, raw, config)
        if result.state == "entry_ready":
            return result.model_copy(update={"state": "lower_high_break", "reason_code": "WAITING_FOR_BREAKOUT_HOLD", "signal": None})
        return result

    # The backtest feeds monotonically growing finalized regular-session prefixes.
    # Re-evaluating the immediately prior prefix is causal and requires no state.
    prior = evaluate_canonical_first_breakout(candidate, raw[:-1], config)
    current = regular[-1]
    current_et = current.end_time.astimezone(_ET)
    if prior.state == "entry_ready" and prior.signal is not None and prior.features.b1 is not None:
        current_vwap = session_vwap(regular)
        if current_et.time() > config.last_entry_et:
            return prior.model_copy(update={"state": "expired", "reason_code": "ENTRY_WINDOW_CLOSED", "signal": None})
        if current_vwap is None or current.close <= prior.features.b1 or current.close <= current_vwap:
            return prior.model_copy(
                update={
                    "state": "lower_high_break",
                    "reason_code": "BREAKOUT_HOLD_FAILED",
                    "signal": None,
                    "evaluated_bar_count": len(regular),
                }
            )
        stop = prior.signal.stop_price
        risk = current.close - stop
        if risk <= 0:
            return prior.model_copy(
                update={
                    "state": "rejected",
                    "reason_code": "NON_POSITIVE_RISK_DISTANCE",
                    "signal": None,
                    "evaluated_bar_count": len(regular),
                }
            )
        features = prior.features.model_copy(
            update={
                "session_vwap": current_vwap,
                "vwap_distance_pct": (current.close / current_vwap - Decimal("1")) * Decimal("100"),
            }
        )
        signal = StrategySignal(
            instrument_id=candidate.instrument_id,
            state="entry_ready",
            entry_price=current.close,
            stop_price=stop,
            target_price=current.close + risk * config.reward_multiple,
            risk_per_share=risk,
            reason_code="FAILED_SELLOFF_CANONICAL_BREAK_HOLD_RESEARCH",
            quality_score=features.quality_score,
        )
        transitions = tuple(value for value in prior.transitions if value != "entry_ready") + ("breakout_hold", "entry_ready")
        return prior.model_copy(
            update={
                "state": "entry_ready",
                "reason_code": signal.reason_code,
                "features": features,
                "signal": signal,
                "transitions": transitions,
                "evaluated_bar_count": len(regular),
            }
        )

    current_first = evaluate_canonical_first_breakout(candidate, raw, config)
    if current_first.state == "entry_ready":
        return current_first.model_copy(
            update={
                "state": "lower_high_break",
                "reason_code": "WAITING_FOR_BREAKOUT_HOLD",
                "signal": None,
            }
        )
    return current_first


def main() -> int:
    args = _args()
    start = date.fromisoformat(args.development_start)
    end = date.fromisoformat(args.development_end)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)

    basis_strategy = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(basis_strategy, spread)
    datasets, coverage = _load_block(Path(args.dataset_cache_dir) / namespace, start, end)
    requested = int(coverage["requested_sessions"])
    covered = int(coverage["covered_sessions"])
    required = max(args.minimum_covered_sessions, math.ceil(requested * float(Decimal(args.minimum_coverage_ratio))))
    if covered < required:
        raise SystemExit(f"cache coverage {covered}/{requested} below required {required}; provider access is prohibited")

    frozen = frozen_v2_config()
    variants = [
        ("hold_volume_0", Decimal("0")),
        ("hold_volume_1_0", Decimal("1.0")),
        ("hold_volume_1_5", Decimal("1.5")),
    ]
    rows: list[dict[str, object]] = []
    with _research_evaluator(evaluate_canonical_break_hold):
        for variant_id, threshold in variants:
            config = frozen.model_copy(update={"v2_minimum_breakout_volume_ratio": threshold})
            metrics = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
            rows.append(
                {
                    "variant_id": variant_id,
                    "minimum_breakout_volume_ratio": str(threshold),
                    **metrics,
                }
            )

    eligible: list[str] = []
    for row in rows:
        expectancy = Decimal(str(row["expectancy_r"])) if row["expectancy_r"] is not None else Decimal("-Infinity")
        lcb = Decimal(str(row["one_sided_90_lcb_r"])) if row["one_sided_90_lcb_r"] is not None else None
        if int(row["trade_count"]) >= args.minimum_development_trades and expectancy > 0 and lcb is not None and lcb > 0:
            eligible.append(str(row["variant_id"]))

    output = {
        "purpose": "one-bar breakout-hold research for a future post-V2 successor",
        "production_strategy_changed": False,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "development_period": [start.isoformat(), end.isoformat()],
        "cache_namespace": namespace,
        "cache_basis": basis,
        "coverage": coverage,
        "holdout_loaded": False,
        "hold_rule": "prior finalized bar is first causal B1+VWAP breakout; current finalized bar closes above B1 and current VWAP",
        "holdout_gate": {
            "minimum_development_trades": args.minimum_development_trades,
            "expectancy_r": "> 0",
            "one_sided_90_lcb_r": "> 0",
        },
        "holdout_eligible_variants": eligible,
        "variants": rows,
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V3 canonical one-bar break-and-hold — development only",
        "",
        f"- Period: {start} through {end}",
        f"- Coverage: {covered}/{requested}",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
        "",
        "| Breakout volume | Trades | Triggers | W-L | Expectancy R | 90% LCB R | P&L |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['minimum_breakout_volume_ratio']}x | {row['trade_count']} | {row['trigger_count']} | "
            f"{row['win_count']}-{row['loss_count']} | {row['expectancy_r'] or 'N/A'} | "
            f"{row['one_sided_90_lcb_r'] or 'N/A'} | {row['pnl']} |"
        )
    lines.extend(["", f"Holdout-eligible variants: **{', '.join(eligible) if eligible else 'none'}**", ""])
    if not eligible:
        lines.append("March remains sealed; break-and-hold evidence does not clear the holdout gate.")
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
