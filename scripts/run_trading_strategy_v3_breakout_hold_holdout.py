from __future__ import annotations

"""One-shot, cache-only March holdout protocol for the post-V2 successor.

This script freezes the selection and validation rules *before* the extended
October-February development result is inspected. It never changes frozen V2,
never enables a production strategy version, and never calls a provider.

Protocol:
- evaluate the already-declared one-bar hold variants on development only;
- require >=5 development trades, positive expectancy, and one-sided 90% LCB > 0;
- if none qualify, stop without loading March;
- if several qualify, choose highest 90% LCB, then more trades, then higher
  expectancy, then the lower breakout-volume threshold as the simpler tie-break;
- load March only after that champion is fixed;
- call the holdout a pass only with >=5 March trades, positive expectancy, and
  one-sided 90% LCB > 0. Fewer trades are explicitly inconclusive.
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
from scripts.run_trading_strategy_v3_breakout_hold_research import evaluate_canonical_break_hold
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator


_VARIANTS = (
    ("hold_volume_0", Decimal("0")),
    ("hold_volume_1_0", Decimal("1.0")),
    ("hold_volume_1_5", Decimal("1.5")),
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the predeclared post-V2 March holdout from immutable cache only.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2025-10-01")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--holdout-start", default="2026-03-02")
    parser.add_argument("--holdout-end", default="2026-03-31")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--minimum-development-trades", type=int, default=5)
    parser.add_argument("--minimum-holdout-trades", type=int, default=5)
    parser.add_argument("--minimum-development-coverage-ratio", default="0.80")
    parser.add_argument("--minimum-development-covered-sessions", type=int, default=50)
    parser.add_argument("--minimum-holdout-coverage-ratio", default="0.80")
    parser.add_argument("--minimum-holdout-covered-sessions", type=int, default=15)
    parser.add_argument("--output-dir", default="artifacts/v3-breakout-hold-holdout")
    return parser.parse_args()


def _decimal_metric(row: dict[str, object], key: str) -> Decimal | None:
    raw = row.get(key)
    return Decimal(str(raw)) if raw is not None else None


def _coverage_ok(coverage: dict[str, object], *, ratio: Decimal, minimum: int) -> bool:
    requested = int(coverage["requested_sessions"])
    covered = int(coverage["covered_sessions"])
    required = max(minimum, math.ceil(requested * float(ratio)))
    return covered >= required


def development_eligible(row: dict[str, object], minimum_trades: int) -> bool:
    expectancy = _decimal_metric(row, "expectancy_r")
    lcb = _decimal_metric(row, "one_sided_90_lcb_r")
    return (
        int(row.get("trade_count") or 0) >= minimum_trades
        and expectancy is not None
        and expectancy > 0
        and lcb is not None
        and lcb > 0
    )


def select_development_champion(rows: list[dict[str, object]], minimum_trades: int) -> dict[str, object] | None:
    eligible = [row for row in rows if development_eligible(row, minimum_trades)]
    if not eligible:
        return None

    def rank(row: dict[str, object]):
        lcb = _decimal_metric(row, "one_sided_90_lcb_r") or Decimal("-Infinity")
        expectancy = _decimal_metric(row, "expectancy_r") or Decimal("-Infinity")
        threshold = Decimal(str(row["minimum_breakout_volume_ratio"]))
        return (lcb, int(row["trade_count"]), expectancy, -threshold)

    return max(eligible, key=rank)


def _status(row: dict[str, object], minimum_trades: int) -> str:
    trades = int(row.get("trade_count") or 0)
    expectancy = _decimal_metric(row, "expectancy_r")
    lcb = _decimal_metric(row, "one_sided_90_lcb_r")
    if trades < minimum_trades:
        return "inconclusive_low_trade_count"
    if expectancy is not None and expectancy > 0 and lcb is not None and lcb > 0:
        return "pass"
    return "fail"


def main() -> int:
    args = _args()
    development_start = date.fromisoformat(args.development_start)
    development_end = date.fromisoformat(args.development_end)
    holdout_start = date.fromisoformat(args.holdout_start)
    holdout_end = date.fromisoformat(args.holdout_end)
    if holdout_start <= development_end:
        raise SystemExit("holdout must begin strictly after development ends")

    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    basis_strategy = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(basis_strategy, spread)
    cache = Path(args.dataset_cache_dir) / namespace

    development, development_coverage = _load_block(cache, development_start, development_end)
    if not _coverage_ok(
        development_coverage,
        ratio=Decimal(args.minimum_development_coverage_ratio),
        minimum=args.minimum_development_covered_sessions,
    ):
        raise SystemExit("development cache coverage is below the frozen holdout protocol requirement")

    frozen = frozen_v2_config()
    development_rows: list[dict[str, object]] = []
    with _research_evaluator(evaluate_canonical_break_hold):
        for variant_id, threshold in _VARIANTS:
            config = frozen.model_copy(update={"v2_minimum_breakout_volume_ratio": threshold})
            metrics = _run_variant(development, config, initial_cash=initial_cash, spread=spread)
            development_rows.append(
                {
                    "variant_id": variant_id,
                    "minimum_breakout_volume_ratio": str(threshold),
                    **metrics,
                }
            )

    champion = select_development_champion(development_rows, args.minimum_development_trades)
    base_output: dict[str, object] = {
        "purpose": "predeclared post-V2 March holdout",
        "production_strategy_changed": False,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "cache_namespace": namespace,
        "cache_basis": basis,
        "development_period": [development_start.isoformat(), development_end.isoformat()],
        "development_coverage": development_coverage,
        "development_variants": development_rows,
        "development_gate": {
            "minimum_trades": args.minimum_development_trades,
            "expectancy_r": "> 0",
            "one_sided_90_lcb_r": "> 0",
        },
        "champion_selection": [
            "highest one-sided 90% LCB",
            "then more trades",
            "then higher expectancy",
            "then lower breakout-volume threshold",
        ],
        "holdout_period": [holdout_start.isoformat(), holdout_end.isoformat()],
        "holdout_gate": {
            "minimum_trades": args.minimum_holdout_trades,
            "expectancy_r": "> 0",
            "one_sided_90_lcb_r": "> 0",
        },
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if champion is None:
        output = {
            **base_output,
            "holdout_loaded": False,
            "selected_variant": None,
            "holdout_status": "not_opened_development_gate_failed",
            "holdout_result": None,
        }
        (out / "results.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary = (
            "# Post-V2 March holdout\n\n"
            "- March holdout loaded: **no**\n"
            "- Reason: no development variant cleared the predeclared gate.\n"
            "- Frozen V2 changed: **no**\n"
        )
        (out / "summary.md").write_text(summary, encoding="utf-8")
        print(summary)
        return 0

    # This is deliberately the first point at which March is touched.
    holdout, holdout_coverage = _load_block(cache, holdout_start, holdout_end)
    if not _coverage_ok(
        holdout_coverage,
        ratio=Decimal(args.minimum_holdout_coverage_ratio),
        minimum=args.minimum_holdout_covered_sessions,
    ):
        raise SystemExit("holdout cache coverage is below the frozen protocol requirement")

    threshold = Decimal(str(champion["minimum_breakout_volume_ratio"]))
    with _research_evaluator(evaluate_canonical_break_hold):
        config = frozen.model_copy(update={"v2_minimum_breakout_volume_ratio": threshold})
        holdout_metrics = _run_variant(holdout, config, initial_cash=initial_cash, spread=spread)
    holdout_row = {
        "variant_id": champion["variant_id"],
        "minimum_breakout_volume_ratio": str(threshold),
        **holdout_metrics,
    }
    status = _status(holdout_row, args.minimum_holdout_trades)
    output = {
        **base_output,
        "holdout_loaded": True,
        "selected_variant": champion,
        "holdout_coverage": holdout_coverage,
        "holdout_status": status,
        "holdout_result": holdout_row,
    }
    (out / "results.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = (
        "# Post-V2 March holdout\n\n"
        f"- Selected variant: **{champion['variant_id']}**\n"
        f"- Breakout-volume threshold: **{threshold}x**\n"
        f"- March trades: **{holdout_row['trade_count']}**\n"
        f"- March expectancy: **{holdout_row['expectancy_r']}R**\n"
        f"- March one-sided 90% LCB: **{holdout_row['one_sided_90_lcb_r']}R**\n"
        f"- Holdout status: **{status}**\n"
        "- Frozen V2 changed: **no**\n"
    )
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
