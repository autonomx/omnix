from __future__ import annotations

"""Development-only breakout-volume sensitivity around the frozen canonical selector.

No provider access, no March holdout access, and no production strategy mutation.
The selector itself is frozen in run_trading_strategy_v3_canonical_path_research;
this script changes only v2_minimum_breakout_volume_ratio one axis at a time.
"""

import argparse
import json
import math
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
from scripts.run_trading_strategy_v3_canonical_path_research import (
    _research_evaluator,
    evaluate_canonical_failed_selloff,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test canonical breakout-volume thresholds on cached development data.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2026-01-02")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--minimum-development-trades", type=int, default=5)
    parser.add_argument("--minimum-coverage-ratio", default="0.80")
    parser.add_argument("--minimum-covered-sessions", type=int, default=20)
    parser.add_argument("--output-dir", default="artifacts/v3-breakout-volume-research")
    return parser.parse_args()


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
        ("canonical_volume_0", Decimal("0")),
        ("canonical_volume_0_75", Decimal("0.75")),
        ("canonical_volume_1_0", Decimal("1.0")),
        ("canonical_volume_1_25", Decimal("1.25")),
        ("canonical_volume_1_5", Decimal("1.5")),
    ]
    rows: list[dict[str, object]] = []
    with _research_evaluator(evaluate_canonical_failed_selloff):
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
        "purpose": "single-axis breakout-volume research for a future post-V2 successor",
        "production_strategy_changed": False,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "development_period": [start.isoformat(), end.isoformat()],
        "cache_namespace": namespace,
        "cache_basis": basis,
        "coverage": coverage,
        "holdout_loaded": False,
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
        "# V3 canonical breakout-volume research — development only",
        "",
        f"- Period: {start} through {end}",
        f"- Coverage: {covered}/{requested}",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
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
        lines.append("March remains sealed; breakout-volume evidence is not strong enough to justify holdout exposure.")
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
