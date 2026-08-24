from __future__ import annotations

"""Bounded V8 test of earlier causal recovery geometry.

V6/V7 showed that the frozen V3 watch signal often arrives after most of the
old >=30% recovery objective has already been consumed. V8 therefore changes
only *when* the recovery watch can fire: a small predeclared grid of rebound and
retracement thresholds. The outcome is directly economic (+1R before -1R in
60m), and all risk/execution semantics remain fixed.
"""

import argparse
import json
import math
from datetime import date
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as strategy_backtest
from app.trading.strategies.gap_pullback import _regular_bars
from app.trading.strategy_v2_qualification import frozen_v2_config
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
import scripts.run_trading_strategy_v6_micro_acceptance as v6
import scripts.run_trading_strategy_v7_economic_label_census as census

_REBOUNDS = (Decimal("10"), Decimal("15"), Decimal("20"))
_RETRACES = (Decimal("50"), Decimal("65"), Decimal("80"))
_VARIANTS = tuple((f"r{r}_t{t}", r, t) for r in _REBOUNDS for t in _RETRACES)


def _args():
    p = argparse.ArgumentParser(description="V8 earlier economic recovery geometry.")
    p.add_argument("--mode", choices=("development", "holdout"), required=True)
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--selector-source", default="/tmp/recovery_selector.py")
    p.add_argument("--variant-id", default="")
    p.add_argument("--selection-file", default="")
    p.add_argument("--minimum-coverage-ratio", default="0.98")
    p.add_argument("--minimum-covered-sessions", type=int, default=300)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _variant(variant_id):
    for row in _VARIANTS:
        if row[0] == variant_id:
            return row
    raise ValueError(f"unknown V8 variant: {variant_id}")


def _watch_rule(module, rebound: Decimal, retrace: Decimal):
    return module.Rule((
        module.Predicate(f"rebound>={rebound}", "recovery", "recovery_pct", ">=", float(rebound)),
        module.Predicate(f"retrace>={retrace}", "retracement", "retracement_pct", ">=", float(retrace)),
        module.Predicate("selloff>=15", "selloff", "selloff_pct", ">=", 15),
        module.Predicate("vol5x>=1.5", "volume_ratio", "volume_ratio5", ">=", 1.5),
    ))


def _segment(row):
    d = date.fromisoformat(row["session_date"])
    if d <= date(2025, 6, 30):
        return "2025_H1"
    if d <= date(2025, 12, 31):
        return "2025_H2"
    return "2026_Q1"


def _binary_stats(rows, segment=None):
    selected = [row for row in rows if segment is None or _segment(row) == segment]
    wins = sum(bool(row["economic_label_1r_before_stop_60m"]) for row in selected)
    return {"signals": len(selected), "wins": wins, "win_rate": wins / len(selected) if selected else None}


def _temporal_gate(stats):
    h1, h2, q1, full = stats["2025_H1"], stats["2025_H2"], stats["2026_Q1"], stats["full"]
    return (
        h1["signals"] >= 10 and (h1["win_rate"] or 0) >= 0.70
        and h2["signals"] >= 10 and (h2["win_rate"] or 0) >= 0.65
        and q1["signals"] >= 5 and (q1["win_rate"] or 0) >= 0.60
        and full["signals"] >= 30 and (full["win_rate"] or 0) >= 0.67
    )


def _trade_evaluator(module, rebound: Decimal, retrace: Decimal):
    base = module._evaluator_for(_watch_rule(module, rebound, retrace))

    def evaluate(candidate, bars, config):
        result = base(candidate, bars, config)
        if result.state != "entry_ready" or result.signal is None:
            return result
        regular = list(_regular_bars(bars))
        if len(regular) < 5:
            return result
        entry = regular[-1].close
        stop = min(bar.low for bar in regular[-5:]) * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
        risk = entry - stop
        if risk <= 0:
            return v6._reject(result, regular, "V8_NON_POSITIVE_RISK_DISTANCE")
        signal = result.signal.model_copy(update={
            "entry_price": entry,
            "stop_price": stop,
            "risk_per_share": risk,
            "target_price": entry + risk,
            "reason_code": f"EARLIER_ECONOMIC_V8_R{rebound}_T{retrace}",
        })
        return result.model_copy(update={"signal": signal, "reason_code": signal.reason_code})

    return evaluate


def _trade_metrics(module, datasets, rebound, retrace, config, initial_cash, spread):
    original_rsi = strategy_backtest.relative_strength_index
    strategy_backtest.relative_strength_index = lambda values, period: [Decimal("0")] * max(0, len(values) - int(period))
    try:
        with module._research_evaluator(_trade_evaluator(module, rebound, retrace)):
            run = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
    finally:
        strategy_backtest.relative_strength_index = original_rsi
    return {**module._trade_metrics(run), "trades": run.get("trades")}


def _trade_gate(row):
    return (
        int(row.get("trade_count") or 0) >= 25
        and float(row.get("win_rate") or 0) >= 0.70
        and float(row.get("expectancy_r") or -999) >= 0.15
        and float(row.get("one_sided_90_lcb_r") or -999) > 0
        and float(row.get("max_drawdown_r") or 999) <= 5
    )


def _holdout_verdict(row):
    count = int(row.get("trade_count") or 0)
    win = float(row.get("win_rate") or 0)
    exp = float(row.get("expectancy_r") or -999)
    dd = float(row.get("max_drawdown_r") or 999)
    if count < 5:
        return "UNDERPOWERED"
    if win >= 0.75 and exp >= 0.20 and dd <= 3:
        return "GOLD"
    if win >= 0.60 and exp > 0 and dd <= 5:
        return "ROBUST"
    return "FAIL"


def main():
    args = _args()
    start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
    spread, initial_cash = Decimal(args.assumed_spread_bps), Decimal(args.initial_cash)
    namespace, cache_basis = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    datasets, coverage = _load_block(Path(args.dataset_cache_dir) / namespace, start, end)
    requested, covered = int(coverage["requested_sessions"]), int(coverage["covered_sessions"])
    required = max(args.minimum_covered_sessions, math.ceil(requested * float(Decimal(args.minimum_coverage_ratio))))
    if covered < required:
        raise SystemExit(f"coverage {covered}/{requested} below frozen requirement {required}")

    module = v6._load_selector(args.selector_source)
    config = frozen_v2_config().model_copy(update={"reward_multiple": Decimal("1.0")})
    common = {
        "purpose": "test earlier causal recovery geometry against direct +1R-before--1R outcome",
        "research_only": True,
        "production_strategy_changed": False,
        "execution_authority": False,
        "period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "coverage_policy": {"minimum_ratio": args.minimum_coverage_ratio, "minimum_sessions": args.minimum_covered_sessions, "required_sessions": required},
        "cache_namespace": namespace,
        "cache_basis": cache_basis,
        "selloff_min_pct": "15",
        "volume_ratio5_min": "1.5",
        "reward_multiple": "1.0",
        "rsi_exit": "disabled",
        "profit_protection": "+0.75R arm -> +0.25R protected stop",
        "max_hold_minutes": 60,
    }

    if args.mode == "development":
        variants = []
        for variant_id, rebound, retrace in _VARIANTS:
            evaluator = module._evaluator_for(_watch_rule(module, rebound, retrace))
            rows = []
            for dataset in datasets:
                for candidate in dataset.universe.candidates:
                    bars = tuple(dataset.bars_by_instrument[candidate.instrument_id])
                    item = census._row(dataset, candidate, bars, evaluator, config)
                    if item is not None:
                        rows.append(item)
            stats = {
                "2025_H1": _binary_stats(rows, "2025_H1"),
                "2025_H2": _binary_stats(rows, "2025_H2"),
                "2026_Q1": _binary_stats(rows, "2026_Q1"),
                "full": _binary_stats(rows, None),
            }
            variants.append({
                "variant_id": variant_id,
                "rebound_min_pct": str(rebound),
                "retracement_min_pct": str(retrace),
                "economic_label_stats": stats,
                "temporal_gate_pass": _temporal_gate(stats),
            })

        temporal = [row for row in variants if row["temporal_gate_pass"]]
        realistic = []
        for row in temporal:
            _, rebound, retrace = _variant(row["variant_id"])
            trade = _trade_metrics(module, datasets, rebound, retrace, config, initial_cash, spread)
            realistic.append({**row, "trade_metrics": trade, "trade_gate_pass": _trade_gate(trade)})
        passing = [row for row in realistic if row["trade_gate_pass"]]
        passing.sort(key=lambda row: (
            float(row["trade_metrics"].get("expectancy_r") or -999),
            float(row["trade_metrics"].get("win_rate") or 0),
            -float(row["trade_metrics"].get("max_drawdown_r") or 999),
        ), reverse=True)
        selected = passing[0] if passing else None
        if selected is not None and args.selection_file:
            Path(args.selection_file).write_text(json.dumps({
                "variant_id": selected["variant_id"],
                "rebound_min_pct": selected["rebound_min_pct"],
                "retracement_min_pct": selected["retracement_min_pct"],
            }, indent=2) + "\n", encoding="utf-8")
        payload = {
            **common,
            "mode": "development",
            "search_contract": {
                "rebound_axis_pct": [str(x) for x in _REBOUNDS],
                "retracement_axis_pct": [str(x) for x in _RETRACES],
                "all_other_watch_and_management_rules_fixed": True,
                "temporal_gate": {
                    "2025_H1": ">=10 signals and >=70% wins",
                    "2025_H2": ">=10 signals and >=65% wins",
                    "2026_Q1": ">=5 signals and >=60% wins",
                    "full": ">=30 signals and >=67% wins",
                },
                "realistic_trade_gate": ">=25 trades, >=70% wins, >=+0.15R expectancy, positive 90% LCB, <=5R DD",
            },
            "variants": variants,
            "temporal_gate_pass_count": len(temporal),
            "realistic_replays": realistic,
            "selected_for_forward_holdout": None if selected is None else {
                "variant_id": selected["variant_id"],
                "rebound_min_pct": selected["rebound_min_pct"],
                "retracement_min_pct": selected["retracement_min_pct"],
                "trade_metrics": {k: selected["trade_metrics"].get(k) for k in ("trade_count", "win_rate", "expectancy_r", "one_sided_90_lcb_r", "max_drawdown_r")},
            },
        }
        title = "# V8 earlier economic geometry development"
        verdict = f"Selected for forward holdout: **{selected['variant_id'] if selected else 'NONE'}**"
    else:
        if not args.variant_id:
            raise SystemExit("--variant-id required in holdout mode")
        _, rebound, retrace = _variant(args.variant_id)
        trade = _trade_metrics(module, datasets, rebound, retrace, config, initial_cash, spread)
        verdict_code = _holdout_verdict(trade)
        payload = {**common, "mode": "one_shot_holdout", "no_parameter_search": True, "variant_id": args.variant_id, "rebound_min_pct": str(rebound), "retracement_min_pct": str(retrace), "trade_metrics": trade, "holdout_verdict": verdict_code}
        title = "# V8 earlier economic geometry one-shot holdout"
        verdict = f"Holdout verdict: **{verdict_code}**"

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [title, "", f"- Period: **{start} through {end}**", f"- Coverage: **{covered}/{requested}**", "- Production strategy changed: **no**", "- Execution authority: **false**", ""]
    if args.mode == "development":
        lines.extend(["| Variant | H1 | H2 | Q1 | Full | Temporal gate |", "|---|---:|---:|---:|---:|---:|"])
        for row in payload["variants"]:
            s = row["economic_label_stats"]
            fmt = lambda x: f"{x['wins']}/{x['signals']} ({x['win_rate']})"
            lines.append(f"| {row['variant_id']} | {fmt(s['2025_H1'])} | {fmt(s['2025_H2'])} | {fmt(s['2026_Q1'])} | {fmt(s['full'])} | {row['temporal_gate_pass']} |")
        lines.extend(["", f"Temporal gate passes: **{len(payload['realistic_replays'])}**", ""])
        if payload["realistic_replays"]:
            lines.extend(["| Variant | Trades | Win rate | Exp R | 90% LCB R | Max DD R | Trade gate |", "|---|---:|---:|---:|---:|---:|---:|"])
            for row in payload["realistic_replays"]:
                t = row["trade_metrics"]
                lines.append(f"| {row['variant_id']} | {t.get('trade_count')} | {t.get('win_rate')} | {t.get('expectancy_r')} | {t.get('one_sided_90_lcb_r')} | {t.get('max_drawdown_r')} | {row['trade_gate_pass']} |")
            lines.append("")
    else:
        t = payload["trade_metrics"]
        lines.extend([f"- Variant: **{payload['variant_id']}**", f"- Trades: **{t.get('trade_count')}**", f"- Win rate: **{t.get('win_rate')}**", f"- Expectancy: **{t.get('expectancy_r')}R**", f"- 90% LCB: **{t.get('one_sided_90_lcb_r')}R**", f"- Max drawdown: **{t.get('max_drawdown_r')}R**", ""])
    lines.extend([verdict, ""])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
