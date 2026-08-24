from __future__ import annotations

"""Fast exact cross-check for the two broad V11 timing candidates."""

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v7_higher_low as _v7
import scripts.run_trading_strategy_failed_selloff_v8_orderly_base as _v8
import scripts.run_trading_strategy_failed_selloff_v11_timing_geometry as _v11
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--output-dir", default="artifacts/failed-selloff-v11-fast")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="40")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread)
    cache = Path(args.dataset_cache_dir) / namespace
    blocks = [
        _v11._load_block(cache, date(2026, 5, 26), date(2026, 6, 18)),
        _v11._load_block(cache, date(2026, 6, 26), date(2026, 7, 23)),
        _v11._load_block(cache, date(2026, 7, 24), date(2026, 8, 21)),
    ]
    all_datasets = [d for block in blocks for d in block]
    base = _v11._base_variant()
    _v7._result = _v8._normalized_result
    _bt.evaluate_gap_pullback = _v11._timing_evaluate
    _bt._find_trade = _v4._managed_find_trade

    results = []
    for gates in (_v11.TimingGates(4, 8), _v11.TimingGates(4, 10)):
        block_rows = [_v11._run(base, gates, block, initial_cash=initial_cash, spread=spread) for block in blocks]
        full = _v11._run(base, gates, all_datasets, initial_cash=initial_cash, spread=spread)
        qualifies = (
            _v11._positive(block_rows[0], 2)
            and _v11._positive(block_rows[1], 1)
            and _v11._positive(block_rows[2], 2)
            and _v11._positive(full, 8)
            and _v11._worst_r(full) > Decimal("-1.75")
            and _v11._decimal(full.get("max_drawdown_pct"), "999") < Decimal("2")
        )
        results.append({
            "variant_id": _v11._variant_id(gates),
            "blocks": block_rows,
            "full": full,
            "qualifies": qualifies,
        })

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [
        "# V11 fast exact cross-check", "",
        "Revealed data only; April/May external holdout excluded.", "",
    ]
    for item in results:
        lines.append(f"## `{item['variant_id']}`")
        for idx, row in enumerate(item["blocks"], 1):
            lines.append(f"- Regime {idx}: {row['trade_count']} trades, {row['expectancy_r']}R, P&L {row['pnl']}, DD {row['max_drawdown_pct']}%")
        full = item["full"]
        lines.append(f"- Full: {full['trade_count']} trades, {full['expectancy_r']}R, P&L {full['pnl']}, DD {full['max_drawdown_pct']}%, worst {_v11._worst_r(full)}R")
        lines.append(f"- Promotion rule: {'PASS' if item['qualifies'] else 'FAIL'}")
        lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
