from __future__ import annotations

"""Corrected cache-only canonical research with first-breakout semantics.

The earlier canonical research artifact is retained as diagnostic evidence but is
not valid for strategy selection because it could enter after an earlier B1+VWAP
break. This wrapper preserves the frozen canonical path selector and rejects a
current signal whenever that selected path already broke on an earlier finalized
positive bar. It remains development-only and cannot call a provider.
"""

import argparse
import json
import math
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.trading.gapper_dataset import GapperCandidate
from app.trading.models import MarketBar
from app.trading.strategies.gap_pullback import _regular_bars, session_vwap
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
from scripts.run_trading_strategy_v3_canonical_path_research import (
    _research_evaluator,
    evaluate_canonical_failed_selloff,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run corrected first-breakout successor research from cache only.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2026-01-02")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--minimum-development-trades", type=int, default=5)
    parser.add_argument("--minimum-coverage-ratio", default="0.80")
    parser.add_argument("--minimum-covered-sessions", type=int, default=20)
    parser.add_argument("--output-dir", default="artifacts/v3-first-breakout-research")
    return parser.parse_args()


def evaluate_canonical_first_breakout(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
) -> GapPullbackResult:
    result = evaluate_canonical_failed_selloff(candidate, bars, config)
    if result.state != "entry_ready" or result.signal is None:
        return result
    b1 = result.features.b1
    l2_to_signal = result.features.l2_to_signal_minutes
    if b1 is None or l2_to_signal is None:
        return result.model_copy(
            update={
                "state": "rejected",
                "reason_code": "CANONICAL_PATH_METADATA_MISSING",
                "signal": None,
            }
        )

    regular = _regular_bars(list(bars))
    current_index = len(regular) - 1
    l2_index = current_index - int(l2_to_signal)
    # A confirmed local L2 needs its right-side bar finalized before a breakout
    # can count, matching the causal V2 confirmation boundary.
    for index in range(max(0, l2_index + 2), current_index):
        prior = regular[index]
        prior_vwap = session_vwap(regular[: index + 1])
        if (
            prior_vwap is not None
            and prior.close > prior.open
            and prior.close > b1
            and prior.close > prior_vwap
        ):
            transitions = tuple(value for value in result.transitions if value != "entry_ready")
            return result.model_copy(
                update={
                    "state": "lower_high_break",
                    "reason_code": "BREAKOUT_ALREADY_PASSED",
                    "signal": None,
                    "transitions": transitions,
                }
            )
    return result


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
    required = max(
        args.minimum_covered_sessions,
        math.ceil(requested * float(Decimal(args.minimum_coverage_ratio))),
    )
    if covered < required:
        raise SystemExit(f"cache coverage {covered}/{requested} below required {required}; provider access is prohibited")

    frozen = frozen_v2_config()
    variants = [
        ("canonical_first_break_volume_0", Decimal("0")),
        ("canonical_first_break_volume_0_75", Decimal("0.75")),
        ("canonical_first_break_volume_1_0", Decimal("1.0")),
        ("canonical_first_break_volume_1_25", Decimal("1.25")),
        ("canonical_first_break_volume_1_5", Decimal("1.5")),
    ]
    rows: list[dict[str, object]] = []
    with _research_evaluator(evaluate_canonical_first_breakout):
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
        "purpose": "corrected first-breakout canonical successor research",
        "supersedes_for_selection": "initial canonical-path research artifact (delayed-breakout flaw)",
        "production_strategy_changed": False,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "development_period": [start.isoformat(), end.isoformat()],
        "cache_namespace": namespace,
        "cache_basis": basis,
        "coverage": coverage,
        "holdout_loaded": False,
        "first_breakout_rule": "selected path is invalid once an earlier finalized positive bar after confirmed L2 closes above B1 and then-current VWAP",
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
        "# Corrected canonical first-breakout research — development only",
        "",
        f"- Period: {start} through {end}",
        f"- Coverage: {covered}/{requested}",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
        "- Initial canonical artifact: diagnostic only; not valid for strategy selection because delayed breakouts were possible.",
        "",
        "| Min breakout volume | Trades | Triggers | W-L | Expectancy R | 90% LCB R | P&L |",
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
        lines.append("March remains sealed; corrected development evidence does not clear the holdout gate.")
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
