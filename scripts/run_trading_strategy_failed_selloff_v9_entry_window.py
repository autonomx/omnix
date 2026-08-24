from __future__ import annotations

"""V9 research: restore the original morning entry window for V8 survivors.

V8 continuity showed that all 34 exact regime-1 survivors were positive in
regime 2 but made zero trades in regime 3. Their terminal candidate outcomes
were dominated by ENTRY_WINDOW_CLOSED at the inherited 10:30 ET cutoff. V9
changes only that causal timing boundary: 10:45, 11:00, or the original 11:30.
The V8 higher-low/orderly-base structure, management, and filters are unchanged.

All testing is confined to the 58 already-revealed sessions. The frozen
2026-04-29..2026-05-22 external holdout is not loaded.
"""

import argparse
import csv
import json
from dataclasses import replace
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import scripts.run_trading_strategy_failed_selloff_v8_orderly_base as _v8
import scripts.run_trading_strategy_failed_selloff_v8_continuity as _v8c
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


def _id(base, gates):
    return f"v9-{_v8._variant_id(base, gates)[3:]}-last{base.last_entry_et.strftime('%H%M')}"


def _dec(value, fallback="-999"):
    if value is None:
        return Decimal(fallback)
    return Decimal(str(value))


def _positive(row):
    return int(row["trade_count"]) >= 1 and _dec(row.get("expectancy_r")) > 0 and _dec(row.get("pnl"), "0") > 0


def _worst(row):
    trades = row.get("trades") or []
    return min((Decimal(str(t["r_multiple"])) for t in trades), default=Decimal("-999"))


def _load(cache, start, end):
    datasets = []
    for d in _trading_dates(start, end):
        path = _dataset_cache_path(cache, d)
        if not path.exists():
            raise FileNotFoundError(f"missing revealed dataset: {path}")
        datasets.append(_load_cached_dataset(path, d))
    return datasets


def _run(base, gates, datasets, *, initial_cash, spread):
    row = _v8._run_variant(base, gates, datasets, initial_cash=initial_cash, spread=spread)
    row["variant_id"] = _id(base, gates)
    row["parameters"] = {**dict(row.get("parameters") or {}), "last_entry_et": base.last_entry_et.isoformat()}
    return row


def parse_args():
    p = argparse.ArgumentParser(description="Run V9 entry-window restoration research.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--output-dir", default="artifacts/failed-selloff-v9-entry-window")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="40")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    _v8._v7._result = _v8._normalized_result
    _v8._bt.evaluate_gap_pullback = _v8._orderly_base_evaluate
    _v8._bt._find_trade = _v8._v4._managed_find_trade

    initial_cash = Decimal(args.initial_cash)
    spread = Decimal(args.assumed_spread_bps)
    namespace, _ = _cache_namespace(strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread)
    cache = Path(args.dataset_cache_dir) / namespace
    block1 = _load(cache, date(2026, 5, 26), date(2026, 6, 18))
    block2 = _load(cache, date(2026, 6, 26), date(2026, 7, 23))
    block3 = _load(cache, date(2026, 7, 24), date(2026, 8, 21))
    all_data = block1 + block2 + block3
    if len(all_data) != 58:
        raise ValueError(f"expected 58 revealed sessions, got {len(all_data)}")

    v8_survivors = [item for item in _v8._grid() if _v8._variant_id(*item) in _v8c.SURVIVOR_IDS]
    if len(v8_survivors) != 34:
        raise ValueError(f"expected 34 exact V8 survivors, got {len(v8_survivors)}")

    variants = []
    for base, gates in v8_survivors:
        for cutoff in (time(10, 45), time(11, 0), time(11, 30)):
            variants.append((replace(base, last_entry_et=cutoff), gates))

    state = {_id(base, gates): {"base": base, "gates": gates, "r3": None, "r1": None, "r2": None, "full": None} for base, gates in variants}

    # Regime 3 is the starvation regime that motivates this single-axis change.
    stage3 = []
    print(f"V9 regime 3 timing screen: evaluating {len(variants)} variants")
    for i, (base, gates) in enumerate(variants, 1):
        row = _run(base, gates, block3, initial_cash=initial_cash, spread=spread)
        state[_id(base, gates)]["r3"] = row
        if _positive(row):
            stage3.append((base, gates))
        if i % 12 == 0 or i == len(variants):
            print(f"  regime 3 progress {i}/{len(variants)}")
    print(f"V9 regime 3 positive-with-trade: {len(stage3)}")

    stage1 = []
    print(f"V9 regime 1 transfer: evaluating {len(stage3)} survivor(s)")
    for i, (base, gates) in enumerate(stage3, 1):
        row = _run(base, gates, block1, initial_cash=initial_cash, spread=spread)
        state[_id(base, gates)]["r1"] = row
        if _positive(row):
            stage1.append((base, gates))
        if i % 10 == 0 or i == len(stage3):
            print(f"  regime 1 progress {i}/{len(stage3)}")
    print(f"V9 regime 1 positive-with-trade: {len(stage1)}")

    stage2 = []
    print(f"V9 regime 2 transfer: evaluating {len(stage1)} survivor(s)")
    for i, (base, gates) in enumerate(stage1, 1):
        row = _run(base, gates, block2, initial_cash=initial_cash, spread=spread)
        state[_id(base, gates)]["r2"] = row
        if _positive(row):
            stage2.append((base, gates))
        if i % 10 == 0 or i == len(stage1):
            print(f"  regime 2 progress {i}/{len(stage1)}")
    print(f"V9 regime 2 positive-with-trade: {len(stage2)}")

    final = []
    print(f"V9 full 58-session replay: evaluating {len(stage2)} survivor(s)")
    for i, (base, gates) in enumerate(stage2, 1):
        full = _run(base, gates, all_data, initial_cash=initial_cash, spread=spread)
        state[_id(base, gates)]["full"] = full
        if (
            int(full["trade_count"]) >= 8
            and _dec(full.get("expectancy_r")) > 0
            and _dec(full.get("pnl"), "0") > 0
            and _worst(full) > Decimal("-1.75")
            and _dec(full.get("max_drawdown_pct"), "999") < Decimal("2")
        ):
            final.append((base, gates))
        if i % 8 == 0 or i == len(stage2):
            print(f"  full progress {i}/{len(stage2)}")

    final.sort(key=lambda item: (_dec(state[_id(*item)]["full"].get("expectancy_r")), _dec(state[_id(*item)]["full"].get("pnl"), "0"), _worst(state[_id(*item)]["full"])), reverse=True)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    serial = []
    for base, gates in variants:
        bundle = state[_id(base, gates)]
        serial.append({
            "variant_id": _id(base, gates),
            "parameters": {
                "minimum_premarket_dollar_volume": str(base.minimum_premarket_dollar_volume),
                "minimum_l1_to_b1_minutes": gates.minimum_l1_to_b1_minutes,
                "maximum_l2_to_signal_minutes": gates.maximum_l2_to_signal_minutes,
                "maximum_pullback_to_bounce_volume_ratio": str(gates.maximum_pullback_to_bounce_volume_ratio),
                "last_entry_et": base.last_entry_et.isoformat(),
            },
            "regime3": bundle["r3"], "regime1": bundle["r1"], "regime2": bundle["r2"], "full": bundle["full"],
        })
    (out / "results.json").write_text(json.dumps(serial, indent=2, default=str) + "\n", encoding="utf-8")

    fields = ["variant_id", "r3_trades", "r3_exp", "r3_pnl", "r1_trades", "r1_exp", "r1_pnl", "r2_trades", "r2_exp", "r2_pnl", "full_trades", "full_exp", "full_pnl", "full_dd", "worst_r"]
    with (out / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for item in serial:
            r3, r1, r2, full = item["regime3"], item["regime1"], item["regime2"], item["full"]
            writer.writerow({
                "variant_id": item["variant_id"],
                "r3_trades": r3["trade_count"], "r3_exp": r3["expectancy_r"], "r3_pnl": r3["pnl"],
                "r1_trades": None if r1 is None else r1["trade_count"], "r1_exp": None if r1 is None else r1["expectancy_r"], "r1_pnl": None if r1 is None else r1["pnl"],
                "r2_trades": None if r2 is None else r2["trade_count"], "r2_exp": None if r2 is None else r2["expectancy_r"], "r2_pnl": None if r2 is None else r2["pnl"],
                "full_trades": None if full is None else full["trade_count"], "full_exp": None if full is None else full["expectancy_r"], "full_pnl": None if full is None else full["pnl"], "full_dd": None if full is None else full["max_drawdown_pct"], "worst_r": None if full is None else str(_worst(full)),
            })

    lines = [
        "# V9 entry-window restoration research", "",
        "Revealed-data only. April/May external holdout excluded.", "",
        f"- Starting variants: {len(variants)} (34 exact V8 survivors x 3 later cutoffs)",
        f"- Regime-3 positive-with-trade: {len(stage3)}",
        f"- Still positive in regime 1: {len(stage1)}",
        f"- Still positive in regime 2: {len(stage2)}",
        f"- Full 58-session promotion survivors: {len(final)}",
        "- Only changed axis: last entry cutoff (10:45, 11:00, 11:30 ET).", "",
    ]
    if final:
        lines += ["| Rank | Variant | R3 trades/exp | R1 trades/exp | R2 trades/exp | Full trades | Full expR | Full P&L | DD% | Worst R |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for rank, item in enumerate(final, 1):
            b = state[_id(*item)]; r3, r1, r2, full = b["r3"], b["r1"], b["r2"], b["full"]
            lines.append(f"| {rank} | `{_id(*item)}` | {r3['trade_count']} / {r3['expectancy_r']} | {r1['trade_count']} / {r1['expectancy_r']} | {r2['trade_count']} / {r2['expectancy_r']} | {full['trade_count']} | {full['expectancy_r']} | {full['pnl']} | {full['max_drawdown_pct']} | {_worst(full)} |")
        chosen = final[0]; full = state[_id(*chosen)]["full"]
        lines += ["", "## Conclusion", "", f"Freeze candidate `{_id(*chosen)}` before external validation.", f"Revealed result: {full['trade_count']} trades, {full['expectancy_r']}R expectancy, P&L {full['pnl']}, max DD {full['max_drawdown_pct']}%."]
    else:
        lines += ["## Conclusion", "", "No later-cutoff V9 variant clears all revealed regimes plus the combined promotion rule. Keep the external holdout sealed."]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
