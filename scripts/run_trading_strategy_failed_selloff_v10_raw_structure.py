from __future__ import annotations

"""V10 research: test the raw V7 higher-low structure without V8 quality gates.

The V9 July/August funnel showed that candidates stuck after B1 all eventually
undercut L1, so the higher-low requirement remains intact.  The remaining
question is whether V8's post-signal quality filters and V7's breakout-volume /
hold requirements are over-pruning otherwise valid failed-selloff entries.

This script uses revealed data only and never loads the frozen 2026-04-29..
2026-05-22 external holdout.  Production strategy behavior is unchanged.
"""

import argparse
import csv
import itertools
import json
from dataclasses import replace
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v7_higher_low as _v7
import scripts.run_trading_strategy_failed_selloff_v8_orderly_base as _v8
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


def _variant_id(variant):
    hold = "hold" if variant.require_breakout_hold else "direct"
    return (
        f"v10-liq{int(variant.minimum_premarket_dollar_volume)}"
        f"-hl{variant.higher_low_buffer_pct}"
        f"-bvol{variant.minimum_breakout_volume_ratio}"
        f"-{hold}-last1130"
    )


def _grid():
    template = next(
        variant for variant in _v7._grid()
        if variant.minimum_premarket_dollar_volume == Decimal("250000")
        and variant.higher_low_buffer_pct == Decimal("0.5")
        and variant.minimum_breakout_volume_ratio == Decimal("0.8")
        and variant.require_breakout_hold
    )
    for liquidity, breakout_volume, hold in itertools.product(
        (Decimal("100000"), Decimal("250000")),
        (Decimal("0"), Decimal("0.5"), Decimal("0.8")),
        (False, True),
    ):
        yield replace(
            template,
            minimum_premarket_dollar_volume=liquidity,
            minimum_breakout_volume_ratio=breakout_volume,
            require_breakout_hold=hold,
            last_entry_et=time(11, 30),
        )


def _load_block(cache, start, end):
    rows = []
    for session_date in _trading_dates(start, end):
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing revealed dataset: {path}")
        rows.append(_load_cached_dataset(path, session_date))
    return rows


def _decimal(value, fallback="-999"):
    if value is None:
        return Decimal(fallback)
    return Decimal(str(value))


def _worst_r(row):
    trades = row.get("trades") or []
    if not trades:
        return Decimal("-999")
    return min(Decimal(str(trade["r_multiple"])) for trade in trades)


def _positive(row, minimum_trades):
    return (
        int(row["trade_count"]) >= minimum_trades
        and _decimal(row.get("expectancy_r")) > 0
        and _decimal(row.get("pnl"), "0") > 0
    )


def _run(variant, datasets, *, initial_cash, spread):
    row = _v7._run_variant(variant, datasets, initial_cash=initial_cash, spread=spread)
    row["variant_id"] = _variant_id(variant)
    return row


def parse_args():
    parser = argparse.ArgumentParser(description="Run V10 raw higher-low structure research.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v10-raw-structure")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    cache = Path(args.dataset_cache_dir) / namespace

    block1 = _load_block(cache, date(2026, 5, 26), date(2026, 6, 18))
    block2 = _load_block(cache, date(2026, 6, 26), date(2026, 7, 23))
    block3 = _load_block(cache, date(2026, 7, 24), date(2026, 8, 21))
    all_datasets = block1 + block2 + block3
    if len(all_datasets) != 58:
        raise ValueError(f"expected 58 revealed sessions, got {len(all_datasets)}")

    _v7._result = _v8._normalized_result
    _bt.evaluate_gap_pullback = _v7._higher_low_evaluate
    _bt._find_trade = _v4._managed_find_trade

    variants = list(_grid())
    bundles = []
    r3_survivors = []
    print(f"V10 regime3 screen: {len(variants)} variants")
    for index, variant in enumerate(variants, 1):
        r3 = _run(variant, block3, initial_cash=initial_cash, spread=spread)
        bundle = {"variant": variant, "regime3": r3, "regime1": None, "regime2": None, "full": None}
        bundles.append(bundle)
        if _positive(r3, 3):
            r3_survivors.append(bundle)
        print(f"  {index}/{len(variants)} {_variant_id(variant)} trades={r3['trade_count']} exp={r3['expectancy_r']} pnl={r3['pnl']}")
    print(f"V10 regime3 survivors: {len(r3_survivors)}")

    r1_survivors = []
    for bundle in r3_survivors:
        r1 = _run(bundle["variant"], block1, initial_cash=initial_cash, spread=spread)
        bundle["regime1"] = r1
        if _positive(r1, 2):
            r1_survivors.append(bundle)
    print(f"V10 regime1 transfer survivors: {len(r1_survivors)}")

    r2_survivors = []
    for bundle in r1_survivors:
        r2 = _run(bundle["variant"], block2, initial_cash=initial_cash, spread=spread)
        bundle["regime2"] = r2
        if _positive(r2, 1):
            r2_survivors.append(bundle)
    print(f"V10 regime2 transfer survivors: {len(r2_survivors)}")

    final = []
    for bundle in r2_survivors:
        full = _run(bundle["variant"], all_datasets, initial_cash=initial_cash, spread=spread)
        bundle["full"] = full
        if (
            _positive(full, 10)
            and _worst_r(full) > Decimal("-1.75")
            and _decimal(full.get("max_drawdown_pct"), "999") < Decimal("2")
        ):
            final.append(bundle)

    final.sort(
        key=lambda bundle: (
            min(
                _decimal(bundle["regime1"]["expectancy_r"]),
                _decimal(bundle["regime2"]["expectancy_r"]),
                _decimal(bundle["regime3"]["expectancy_r"]),
            ),
            _decimal(bundle["full"]["expectancy_r"]),
            _decimal(bundle["full"]["pnl"], "0"),
        ),
        reverse=True,
    )

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    serial = []
    for bundle in bundles:
        variant = bundle["variant"]
        serial.append(
            {
                "variant_id": _variant_id(variant),
                "parameters": {
                    "minimum_premarket_dollar_volume": str(variant.minimum_premarket_dollar_volume),
                    "higher_low_buffer_pct": str(variant.higher_low_buffer_pct),
                    "minimum_breakout_volume_ratio": str(variant.minimum_breakout_volume_ratio),
                    "require_breakout_hold": variant.require_breakout_hold,
                    "last_entry_et": variant.last_entry_et.isoformat(),
                },
                "regime3": bundle["regime3"],
                "regime1": bundle["regime1"],
                "regime2": bundle["regime2"],
                "full": bundle["full"],
            }
        )
    (output / "results.json").write_text(json.dumps(serial, indent=2, default=str) + "\n", encoding="utf-8")

    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "variant_id", "r3_trades", "r3_exp", "r3_pnl",
            "r1_trades", "r1_exp", "r1_pnl",
            "r2_trades", "r2_exp", "r2_pnl",
            "full_trades", "full_exp", "full_pnl", "full_dd", "worst_r",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in serial:
            row = {"variant_id": item["variant_id"]}
            for prefix, key in (("r3", "regime3"), ("r1", "regime1"), ("r2", "regime2")):
                result = item[key]
                row[f"{prefix}_trades"] = None if result is None else result["trade_count"]
                row[f"{prefix}_exp"] = None if result is None else result["expectancy_r"]
                row[f"{prefix}_pnl"] = None if result is None else result["pnl"]
            full = item["full"]
            row["full_trades"] = None if full is None else full["trade_count"]
            row["full_exp"] = None if full is None else full["expectancy_r"]
            row["full_pnl"] = None if full is None else full["pnl"]
            row["full_dd"] = None if full is None else full["max_drawdown_pct"]
            row["worst_r"] = None if full is None else str(_worst_r(full))
            writer.writerow(row)

    lines = [
        "# Failed-selloff V10 raw higher-low structure research",
        "",
        "Revealed data only; April/May external holdout excluded.",
        "",
        f"- Starting variants: {len(variants)}",
        f"- Regime-3 positive variants (>=3 trades): {len(r3_survivors)}",
        f"- Still positive in regime 1: {len(r1_survivors)}",
        f"- Still positive in regime 2: {len(r2_survivors)}",
        f"- Full 58-session promotion survivors: {len(final)}",
        "- L2 higher-low semantics are unchanged; V10 only varies liquidity, breakout-volume threshold, and hold requirement.",
        "",
        "## Regime-3 screen",
        "",
        "| Variant | Trades | Expectancy R | P&L |",
        "|---|---:|---:|---:|",
    ]
    for bundle in bundles:
        r3 = bundle["regime3"]
        lines.append(f"| {_variant_id(bundle['variant'])} | {r3['trade_count']} | {r3['expectancy_r']} | {r3['pnl']} |")

    if final:
        lines.extend(["", "## Promotable revealed-data candidates", "", "| Variant | Full trades | Full exp R | Full P&L | Max DD | Worst R |", "|---|---:|---:|---:|---:|---:|"])
        for bundle in final:
            full = bundle["full"]
            lines.append(
                f"| {_variant_id(bundle['variant'])} | {full['trade_count']} | {full['expectancy_r']} | "
                f"{full['pnl']} | {full['max_drawdown_pct']} | {_worst_r(full)} |"
            )
    else:
        lines.extend(["", "## Conclusion", "", "No V10 raw-structure variant qualifies for external validation."])

    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
