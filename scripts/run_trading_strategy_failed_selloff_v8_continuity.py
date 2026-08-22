from __future__ import annotations

"""Continue V8 across revealed regimes without treating one trade as failure.

Run 32600356368 established 34 V8 variants that had >=2 trades, positive
expectancy, and positive dollar P&L in the first revealed regime.  Every one of
those 34 variants then produced exactly one trade in regime 2, and that trade
was +1.5R / positive P&L.  The original V8 harness eliminated them solely
because it required >=2 trades in every regime.

This continuation keeps the exact 34 strategy variants unchanged.  It replays
regimes 2 and 3, then the full 58-session revealed set.  A regime with one
profitable trade is treated as sparse evidence rather than a failure; combined
promotion still requires enough trades, positive expectancy and P&L, bounded
worst realized R, and positive evidence in every regime.  The frozen April/May
external holdout remains excluded.
"""

import argparse
import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import scripts.run_trading_strategy_failed_selloff_v8_orderly_base as _v8
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


SOURCE_RUN_ID = 32600356368
SURVIVOR_IDS = {
    "v8-liq100000-base3-resolve8-pvol0.6",
    "v8-liq100000-base3-resolve8-pvol0.8",
    "v8-liq100000-base3-resolve8-pvol1.0",
    "v8-liq100000-base3-resolve12-pvol0.6",
    "v8-liq100000-base3-resolve12-pvol0.8",
    "v8-liq100000-base3-resolve12-pvol1.0",
    "v8-liq100000-base3-resolve16-pvol0.6",
    "v8-liq100000-base3-resolve16-pvol0.8",
    "v8-liq100000-base3-resolve16-pvol1.0",
    "v8-liq100000-base4-resolve12-pvol0.8",
    "v8-liq100000-base4-resolve12-pvol1.0",
    "v8-liq100000-base4-resolve16-pvol0.8",
    "v8-liq100000-base4-resolve16-pvol1.0",
    "v8-liq100000-base5-resolve12-pvol0.8",
    "v8-liq100000-base5-resolve12-pvol1.0",
    "v8-liq100000-base5-resolve16-pvol0.8",
    "v8-liq100000-base5-resolve16-pvol1.0",
    "v8-liq250000-base3-resolve8-pvol0.6",
    "v8-liq250000-base3-resolve8-pvol0.8",
    "v8-liq250000-base3-resolve8-pvol1.0",
    "v8-liq250000-base3-resolve12-pvol0.6",
    "v8-liq250000-base3-resolve12-pvol0.8",
    "v8-liq250000-base3-resolve12-pvol1.0",
    "v8-liq250000-base3-resolve16-pvol0.6",
    "v8-liq250000-base3-resolve16-pvol0.8",
    "v8-liq250000-base3-resolve16-pvol1.0",
    "v8-liq250000-base4-resolve12-pvol0.8",
    "v8-liq250000-base4-resolve12-pvol1.0",
    "v8-liq250000-base4-resolve16-pvol0.8",
    "v8-liq250000-base4-resolve16-pvol1.0",
    "v8-liq250000-base5-resolve12-pvol0.8",
    "v8-liq250000-base5-resolve12-pvol1.0",
    "v8-liq250000-base5-resolve16-pvol0.8",
    "v8-liq250000-base5-resolve16-pvol1.0",
}


def _decimal(value, fallback="-999"):
    if value is None:
        return Decimal(fallback)
    return Decimal(str(value))


def _positive_sparse(row):
    return (
        int(row["trade_count"]) >= 1
        and _decimal(row.get("expectancy_r")) > 0
        and _decimal(row.get("pnl"), "0") > 0
    )


def _worst_r(row):
    trades = row.get("trades") or []
    if not trades:
        return Decimal("-999")
    return min(Decimal(str(trade["r_multiple"])) for trade in trades)


def _load_block(cache, start, end):
    datasets = []
    for session_date in _trading_dates(start, end):
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing revealed dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))
    return datasets


def parse_args():
    parser = argparse.ArgumentParser(description="Continue exact V8 survivors across revealed regimes.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v8-continuity")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _v8._v7._result = _v8._normalized_result
    _v8._bt.evaluate_gap_pullback = _v8._orderly_base_evaluate
    _v8._bt._find_trade = _v8._v4._managed_find_trade

    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread)
    cache = Path(args.dataset_cache_dir) / namespace

    block1 = _load_block(cache, date(2026, 5, 26), date(2026, 6, 18))
    block2 = _load_block(cache, date(2026, 6, 26), date(2026, 7, 23))
    block3 = _load_block(cache, date(2026, 7, 24), date(2026, 8, 21))
    all_datasets = block1 + block2 + block3
    if len(all_datasets) != 58:
        raise ValueError(f"expected 58 revealed sessions, got {len(all_datasets)}")

    variants = [item for item in _v8._grid() if _v8._variant_id(*item) in SURVIVOR_IDS]
    if len(variants) != len(SURVIVOR_IDS):
        found = {_v8._variant_id(*item) for item in variants}
        missing = sorted(SURVIVOR_IDS - found)
        raise ValueError(f"expected {len(SURVIVOR_IDS)} exact V8 survivors; missing={missing}")

    rows = []
    stage2 = []
    print(f"V8 continuity regime 2: evaluating {len(variants)} exact prior survivors")
    for index, (base, gates) in enumerate(variants, 1):
        key = _v8._variant_id(base, gates)
        r2 = _v8._run_variant(base, gates, block2, initial_cash=initial_cash, spread=spread)
        bundle = {"variant_id": key, "base": base, "gates": gates, "regime2": r2, "regime3": None, "full": None}
        rows.append(bundle)
        if _positive_sparse(r2):
            stage2.append(bundle)
        if index % 8 == 0 or index == len(variants):
            print(f"  regime 2 progress {index}/{len(variants)}")
    print(f"V8 continuity regime 2 positive-with-trade: {len(stage2)}")

    stage3 = []
    print(f"V8 continuity regime 3: evaluating {len(stage2)} survivor(s)")
    for index, bundle in enumerate(stage2, 1):
        r3 = _v8._run_variant(bundle["base"], bundle["gates"], block3, initial_cash=initial_cash, spread=spread)
        bundle["regime3"] = r3
        if _positive_sparse(r3):
            stage3.append(bundle)
        if index % 8 == 0 or index == len(stage2):
            print(f"  regime 3 progress {index}/{len(stage2)}")
    print(f"V8 continuity regime 3 positive-with-trade: {len(stage3)}")

    final = []
    print(f"V8 continuity full 58-session replay: evaluating {len(stage3)} survivor(s)")
    for index, bundle in enumerate(stage3, 1):
        full = _v8._run_variant(bundle["base"], bundle["gates"], all_datasets, initial_cash=initial_cash, spread=spread)
        bundle["full"] = full
        if (
            int(full["trade_count"]) >= 8
            and _decimal(full.get("expectancy_r")) > 0
            and _decimal(full.get("pnl"), "0") > 0
            and _worst_r(full) > Decimal("-1.75")
            and _decimal(full.get("max_drawdown_pct"), "999") < Decimal("2")
        ):
            final.append(bundle)
        if index % 6 == 0 or index == len(stage3):
            print(f"  full progress {index}/{len(stage3)}")

    final.sort(
        key=lambda bundle: (
            _decimal(bundle["full"].get("expectancy_r")),
            _decimal(bundle["full"].get("pnl"), "0"),
            _worst_r(bundle["full"]),
        ),
        reverse=True,
    )

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    serial = []
    for bundle in rows:
        base = bundle["base"]
        gates = bundle["gates"]
        serial.append(
            {
                "variant_id": bundle["variant_id"],
                "parameters": {
                    "minimum_premarket_dollar_volume": str(base.minimum_premarket_dollar_volume),
                    "minimum_l1_to_b1_minutes": gates.minimum_l1_to_b1_minutes,
                    "maximum_l2_to_signal_minutes": gates.maximum_l2_to_signal_minutes,
                    "maximum_pullback_to_bounce_volume_ratio": str(gates.maximum_pullback_to_bounce_volume_ratio),
                    "minimum_breakout_body_pct_range": str(gates.minimum_breakout_body_pct_range),
                },
                "regime2": bundle["regime2"],
                "regime3": bundle["regime3"],
                "full": bundle["full"],
            }
        )
    (output / "results.json").write_text(json.dumps(serial, indent=2, default=str) + "\n", encoding="utf-8")

    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["variant_id", "r2_trades", "r2_exp", "r2_pnl", "r3_trades", "r3_exp", "r3_pnl", "full_trades", "full_exp", "full_pnl", "full_dd", "worst_r"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in serial:
            r2, r3, full = item["regime2"], item["regime3"], item["full"]
            writer.writerow(
                {
                    "variant_id": item["variant_id"],
                    "r2_trades": r2["trade_count"],
                    "r2_exp": r2["expectancy_r"],
                    "r2_pnl": r2["pnl"],
                    "r3_trades": None if r3 is None else r3["trade_count"],
                    "r3_exp": None if r3 is None else r3["expectancy_r"],
                    "r3_pnl": None if r3 is None else r3["pnl"],
                    "full_trades": None if full is None else full["trade_count"],
                    "full_exp": None if full is None else full["expectancy_r"],
                    "full_pnl": None if full is None else full["pnl"],
                    "full_dd": None if full is None else full["max_drawdown_pct"],
                    "worst_r": None if full is None else str(_worst_r(full)),
                }
            )

    lines = [
        "# V8 continuity across revealed regimes",
        "",
        f"- Source V8 run: `{SOURCE_RUN_ID}`",
        f"- Exact regime-1 survivors carried forward: {len(variants)}",
        f"- Regime-2 positive-with-trade variants: {len(stage2)}",
        f"- Regime-3 positive-with-trade variants: {len(stage3)}",
        f"- Full 58-session promotion survivors: {len(final)}",
        "- Sparse regime rule: >=1 trade, positive expectancy R, positive dollar P&L.",
        "- Full rule: >=8 trades, positive expectancy/P&L, worst trade > -1.75R, max drawdown <2%.",
        "- April/May external holdout remains excluded.",
        "",
    ]
    if final:
        lines.extend(["| Rank | Variant | R2 trades/exp | R3 trades/exp | Full trades | Full expR | Full P&L | DD% | Worst R |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|"])
        for rank, bundle in enumerate(final, 1):
            r2, r3, full = bundle["regime2"], bundle["regime3"], bundle["full"]
            lines.append(
                f"| {rank} | `{bundle['variant_id']}` | {r2['trade_count']} / {r2['expectancy_r']} | "
                f"{r3['trade_count']} / {r3['expectancy_r']} | {full['trade_count']} | {full['expectancy_r']} | "
                f"{full['pnl']} | {full['max_drawdown_pct']} | {_worst_r(full)} |"
            )
        chosen = final[0]
        full = chosen["full"]
        lines.extend(["", "## Conclusion", "", f"Freeze candidate `{chosen['variant_id']}` before external validation.", f"Revealed 58-session result: {full['trade_count']} trades, {full['expectancy_r']}R expectancy, P&L {full['pnl']}, max drawdown {full['max_drawdown_pct']}%."])
    else:
        lines.extend(["## Conclusion", "", "No exact V8 regime-1 survivor clears the sparse-regime plus full-sample promotion rule. Keep the external holdout sealed."])
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
