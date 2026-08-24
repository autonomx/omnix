from __future__ import annotations

"""Fast, exact V6 screening by sequential regime elimination.

This runner evaluates the same V6 variants and the same promotion criteria as
run_trading_strategy_failed_selloff_v6_quality_restore.py, but it stops spending
CPU on a variant as soon as that variant cannot satisfy the all-three-regime
rule.  Results for any surviving candidate are exact; there is no approximation
or early acceptance.
"""

import argparse
import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v6_quality_restore as _v6
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


def _load_block(cache: Path, start: date, end: date):
    datasets = []
    for session_date in _trading_dates(start, end):
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing frozen development dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))
    return datasets


def _passes_block(row) -> bool:
    return int(row["trade_count"]) >= 2 and _v6._expectancy(row) > 0


def parse_args():
    parser = argparse.ArgumentParser(description="Run exact sequential V6 regime elimination.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v6-sequential")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _bt.evaluate_gap_pullback = _v6._quality_restore_evaluate
    _bt._find_trade = _v4._managed_find_trade

    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    cache = Path(args.dataset_cache_dir) / namespace

    specs = (
        (date(2026, 5, 26), date(2026, 6, 18)),
        (date(2026, 6, 26), date(2026, 7, 23)),
        (date(2026, 7, 24), date(2026, 8, 21)),
    )
    blocks = [_load_block(cache, start, end) for start, end in specs]
    all_datasets = [dataset for block in blocks for dataset in block]
    if len(all_datasets) != 58:
        raise ValueError(f"V6 expects 58 revealed development sessions, got {len(all_datasets)}")

    variants = list(_v6._grid())
    state = {
        variant.variant_id: {
            "variant": variant,
            "variant_id": variant.variant_id,
            "blocks": [],
            "full": None,
            "eliminated_after": None,
        }
        for variant in variants
    }
    survivors = variants

    for block_index, block in enumerate(blocks, 1):
        next_survivors = []
        print(f"V6 sequential block {block_index}: evaluating {len(survivors)} survivor(s)")
        for index, variant in enumerate(survivors, 1):
            result = _v6._run_variant(variant, block, initial_cash=initial_cash, spread=spread)
            state[variant.variant_id]["blocks"].append(result)
            if _passes_block(result):
                next_survivors.append(variant)
            else:
                state[variant.variant_id]["eliminated_after"] = block_index
            if index % 8 == 0 or index == len(survivors):
                print(f"  block {block_index} progress: {index}/{len(survivors)}")
        survivors = next_survivors
        print(f"V6 sequential block {block_index}: {len(survivors)} survivor(s)")
        if not survivors:
            break

    final_survivors = []
    if survivors and all(len(state[v.variant_id]["blocks"]) == 3 for v in survivors):
        print(f"V6 sequential full replay: evaluating {len(survivors)} survivor(s)")
        for variant in survivors:
            full = _v6._run_variant(variant, all_datasets, initial_cash=initial_cash, spread=spread)
            state[variant.variant_id]["full"] = full
            if int(full["trade_count"]) >= 12 and _v6._expectancy(full) > 0:
                final_survivors.append(variant)
            else:
                state[variant.variant_id]["eliminated_after"] = "full"

    def rank_key(variant):
        bundle = state[variant.variant_id]
        blocks_for_variant = bundle["blocks"]
        full = bundle["full"]
        return (
            min((_v6._expectancy(row) for row in blocks_for_variant), default=Decimal("-999")),
            _v6._expectancy(full) if full is not None else Decimal("-999"),
            _v6._worst_trade(full) if full is not None else Decimal("-999"),
            Decimal(str(full["pnl"])) if full is not None else Decimal("-999999999"),
        )

    ranked_survivors = sorted(final_survivors, key=rank_key, reverse=True)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    serializable = []
    for variant in variants:
        bundle = state[variant.variant_id]
        serializable.append(
            {
                "variant_id": variant.variant_id,
                "parameters": {
                    "minimum_premarket_dollar_volume": str(variant.minimum_premarket_dollar_volume),
                    "minimum_breakout_volume_ratio": str(variant.minimum_breakout_volume_ratio),
                    "minimum_risk_pct": str(variant.minimum_risk_pct),
                    "last_entry_et": variant.last_entry_et.isoformat(),
                },
                "blocks": bundle["blocks"],
                "full": bundle["full"],
                "eliminated_after": bundle["eliminated_after"],
            }
        )
    (output / "results.json").write_text(json.dumps(serializable, indent=2, default=str) + "\n", encoding="utf-8")

    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "variant_id", "eliminated_after",
            "block1_trades", "block1_exp_r",
            "block2_trades", "block2_exp_r",
            "block3_trades", "block3_exp_r",
            "full_trades", "full_exp_r", "full_pnl", "worst_trade_r",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in serializable:
            blocks_for_variant = item["blocks"]
            full = item["full"]
            row = {"variant_id": item["variant_id"], "eliminated_after": item["eliminated_after"]}
            for i in range(3):
                result = blocks_for_variant[i] if i < len(blocks_for_variant) else None
                row[f"block{i+1}_trades"] = None if result is None else result["trade_count"]
                row[f"block{i+1}_exp_r"] = None if result is None else result["expectancy_r"]
            row["full_trades"] = None if full is None else full["trade_count"]
            row["full_exp_r"] = None if full is None else full["expectancy_r"]
            row["full_pnl"] = None if full is None else full["pnl"]
            row["worst_trade_r"] = None if full is None else str(_v6._worst_trade(full))
            writer.writerow(row)

    lines = [
        "# Failed-selloff V6 sequential regime elimination",
        "",
        "Exact V6 promotion screening. Variants are only eliminated early; no variant is accepted without all three regime tests and a full 58-session replay.",
        "",
        f"- Starting variants: {len(variants)}",
        f"- Block 1 survivors: {sum(len(item['blocks']) >= 1 and _passes_block(item['blocks'][0]) for item in state.values())}",
        f"- Block 2 survivors: {sum(len(item['blocks']) >= 2 and _passes_block(item['blocks'][1]) for item in state.values())}",
        f"- Block 3 survivors: {sum(len(item['blocks']) >= 3 and _passes_block(item['blocks'][2]) for item in state.values())}",
        f"- Full-rule survivors: {len(ranked_survivors)}",
        "",
    ]

    if ranked_survivors:
        lines.extend([
            "| Rank | Variant | B1 expR | B2 expR | B3 expR | Full trades | Full expR | Full P&L | Worst R |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for rank, variant in enumerate(ranked_survivors, 1):
            bundle = state[variant.variant_id]
            b1, b2, b3 = bundle["blocks"]
            full = bundle["full"]
            lines.append(
                f"| {rank} | `{variant.variant_id}` | {b1['expectancy_r']} | {b2['expectancy_r']} | {b3['expectancy_r']} | "
                f"{full['trade_count']} | {full['expectancy_r']} | {full['pnl']} | {_v6._worst_trade(full)} |"
            )
        chosen = ranked_survivors[0]
        full = state[chosen.variant_id]["full"]
        lines.extend([
            "",
            "## V6 conclusion",
            "",
            f"Preliminary V6 candidate: `{chosen.variant_id}`.",
            f"Full revealed development: {full['trade_count']} trades, {full['expectancy_r']}R expectancy, P&L {full['pnl']}.",
            "Freeze this exact configuration before external validation.",
        ])
    else:
        lines.extend([
            "## V6 conclusion",
            "",
            "No V6 variant survives the exact all-three-regime promotion rule. Do not consume the reserved external holdout.",
        ])

    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
