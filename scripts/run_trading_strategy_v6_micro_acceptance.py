from __future__ import annotations

"""Research-only V6 micro-acceptance successor.

V6 keeps the frozen V3 recovery watch signal but does not enter immediately.
It waits only 2-3 finalized 1-minute bars and asks whether the initial recovery
is accepted without materially giving back the observed recovery leg. This is
intended to reject immediate failed recoveries without the much later retest /
rebreak timing used by V4.
"""

import argparse
import importlib.util
import json
import math
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

import app.trading.strategy_backtest as strategy_backtest
from app.trading.strategies.gap_pullback import _ET, _regular_bars
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult
from app.trading.strategy_v2_qualification import frozen_v2_config
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
import scripts.run_trading_strategy_v5_recovery_headroom as v5

_SELECTOR_SHA256 = "5c98837cc96ad7c692d45b0bafff6a025f04f52599985cc6e85af734f6917607"
_VARIANTS = (
    ("micro_2bar_ret50_final", 2, Decimal("0.50"), False),
    ("micro_2bar_ret70_final", 2, Decimal("0.70"), False),
    ("micro_3bar_ret50_final", 3, Decimal("0.50"), False),
    ("micro_2bar_ret50_all_closes", 2, Decimal("0.50"), True),
)


def _args():
    p = argparse.ArgumentParser(description="Research V6 micro-acceptance from frozen causal caches.")
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


def _load_selector(path: str):
    spec = importlib.util.spec_from_file_location("recovery_selector_v6", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load frozen recovery selector source")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _variant(variant_id: str):
    for row in _VARIANTS:
        if row[0] == variant_id:
            return row
    raise ValueError(f"unknown V6 variant: {variant_id}")


def _waiting_result(watch_result: GapPullbackResult, regular, reason: str) -> GapPullbackResult:
    transitions = tuple(state for state in watch_result.transitions if state != "entry_ready")
    if not transitions or transitions[-1] != "breakout_hold":
        transitions = transitions + ("breakout_hold",)
    return watch_result.model_copy(
        update={
            "state": "breakout_hold",
            "reason_code": reason,
            "signal": None,
            "transitions": transitions,
            "evaluated_bar_count": len(regular),
        }
    )


def _reject(watch_result: GapPullbackResult, regular, reason: str) -> GapPullbackResult:
    transitions = tuple(state for state in watch_result.transitions if state != "entry_ready") + ("rejected",)
    return watch_result.model_copy(
        update={
            "state": "rejected",
            "reason_code": reason,
            "signal": None,
            "transitions": transitions,
            "evaluated_bar_count": len(regular),
        }
    )


def _micro_evaluator(module, hold_bars: int, retention: Decimal, all_closes: bool) -> Callable:
    base = module._evaluator_for(v5._watch_rule(module))
    watches: dict[tuple[str, str], dict[str, object]] = {}
    terminal: dict[tuple[str, str], GapPullbackResult] = {}

    def evaluate(candidate, bars, config: GapPullbackConfig) -> GapPullbackResult:
        regular = list(_regular_bars(bars))
        if not regular:
            return base(candidate, bars, config)
        key = (regular[0].start_time.astimezone(_ET).date().isoformat(), candidate.instrument_id)
        if key in terminal:
            return terminal[key]

        watch = watches.get(key)
        if watch is None:
            result = base(candidate, bars, config)
            if result.state != "entry_ready" or result.signal is None:
                return result
            trough = v5._opening_trough(regular)
            if trough is None or trough <= 0:
                rejected = _reject(result, regular, "V6_TROUGH_UNAVAILABLE")
                terminal[key] = rejected
                return rejected
            watch_close = regular[-1].close
            leg = watch_close - trough
            if leg <= 0:
                rejected = _reject(result, regular, "V6_NON_POSITIVE_RECOVERY_LEG")
                terminal[key] = rejected
                return rejected
            watch = {
                "result": result,
                "time": regular[-1].end_time,
                "close": watch_close,
                "trough": trough,
                "leg": leg,
            }
            watches[key] = watch
            return _waiting_result(result, regular, "V6_WAITING_MICRO_ACCEPTANCE")

        watch_result = watch["result"]
        assert isinstance(watch_result, GapPullbackResult)
        watch_time = watch["time"]
        watch_close = Decimal(watch["close"])
        trough = Decimal(watch["trough"])
        leg = Decimal(watch["leg"])
        after = [bar for bar in regular if bar.end_time > watch_time]
        if len(after) < hold_bars:
            return _waiting_result(watch_result, regular, "V6_WAITING_MICRO_ACCEPTANCE")

        confirmation = after[:hold_bars]
        final = confirmation[-1]
        if final.end_time.astimezone(_ET).time() > config.last_entry_et:
            rejected = _reject(watch_result, regular, "V6_CONFIRMATION_AFTER_ENTRY_WINDOW")
            terminal[key] = rejected
            return rejected

        retention_floor = trough + leg * retention
        if min(bar.low for bar in confirmation) < retention_floor:
            rejected = _reject(watch_result, regular, "V6_RECOVERY_LEG_NOT_RETAINED")
            terminal[key] = rejected
            return rejected
        if final.close < watch_close:
            rejected = _reject(watch_result, regular, "V6_FINAL_CLOSE_BELOW_WATCH")
            terminal[key] = rejected
            return rejected
        if all_closes and any(bar.close < watch_close for bar in confirmation):
            rejected = _reject(watch_result, regular, "V6_INTERMEDIATE_CLOSE_BELOW_WATCH")
            terminal[key] = rejected
            return rejected

        visible = [bar for bar in regular if bar.end_time <= final.end_time]
        prior5 = visible[-5:]
        stop = min(bar.low for bar in prior5) * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
        risk = final.close - stop
        if risk <= 0:
            rejected = _reject(watch_result, regular, "V6_NON_POSITIVE_RISK_DISTANCE")
            terminal[key] = rejected
            return rejected

        features = watch_result.features.model_copy(
            update={
                "second_pullback_depth_pct": (final.close / watch_close - Decimal("1")) * Decimal("100"),
                "breakout_hold_bars": hold_bars,
            }
        )
        signal = watch_result.signal.model_copy(
            update={
                "entry_price": final.close,
                "stop_price": stop,
                "risk_per_share": risk,
                "target_price": final.close + risk * config.reward_multiple,
                "reason_code": f"RECOVERY_MICRO_ACCEPTANCE_V6_{hold_bars}_{retention}_{int(all_closes)}",
            }
        )
        transitions = tuple(state for state in watch_result.transitions if state != "entry_ready") + ("breakout_hold", "entry_ready")
        return watch_result.model_copy(
            update={
                "state": "entry_ready",
                "reason_code": signal.reason_code,
                "features": features,
                "signal": signal,
                "transitions": transitions,
                "evaluated_bar_count": len(regular),
            }
        )

    return evaluate


def _metrics(module, datasets, variant_id: str, config, initial_cash: Decimal, spread: Decimal):
    _, hold_bars, retention, all_closes = _variant(variant_id)
    factory = lambda: _micro_evaluator(module, hold_bars, retention, all_closes)
    original_rsi = strategy_backtest.relative_strength_index
    strategy_backtest.relative_strength_index = lambda values, period: [Decimal("0")] * max(0, len(values) - int(period))
    try:
        with module._research_evaluator(factory()):
            run = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
    finally:
        strategy_backtest.relative_strength_index = original_rsi
    return {
        **module._trade_metrics(run),
        "trades": run.get("trades"),
        "recovery_precision": v5._signal_precision(datasets, factory, config),
    }


def _development_gate(row):
    return (
        int(row.get("trade_count") or 0) >= 15
        and float(row.get("win_rate") or 0) >= 0.75
        and float(row.get("expectancy_r") or -999) >= 0.20
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
    module = _load_selector(args.selector_source)
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

    config = frozen_v2_config().model_copy(update={"reward_multiple": Decimal("1.0")})
    common = {
        "purpose": "causal micro-acceptance after frozen V3 recovery watch signal",
        "research_only": True,
        "production_strategy_changed": False,
        "execution_authority": False,
        "selector_source_sha256": _SELECTOR_SHA256,
        "watch_rule": v5._watch_rule(module).key,
        "period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "coverage_policy": {"minimum_ratio": args.minimum_coverage_ratio, "minimum_sessions": args.minimum_covered_sessions, "required_sessions": required},
        "cache_namespace": namespace,
        "cache_basis": cache_basis,
        "reward_multiple": "1.0",
        "rsi_exit": "disabled",
        "profit_protection": "+0.75R arm -> +0.25R protected stop",
        "max_hold_minutes": 60,
        "entry": "next eligible 1m execution bar after micro-acceptance signal",
        "stop": "15 bps below latest five finalized 1m lows at micro-acceptance signal",
    }

    if args.mode == "development":
        rows = []
        for variant_id, hold_bars, retention, all_closes in _VARIANTS:
            row = {
                "variant_id": variant_id,
                "hold_bars": hold_bars,
                "recovery_leg_retention": str(retention),
                "all_confirmation_closes_at_or_above_watch": all_closes,
                **_metrics(module, datasets, variant_id, config, initial_cash, spread),
            }
            row["development_gate_pass"] = _development_gate(row)
            rows.append(row)
        passing = [row for row in rows if row["development_gate_pass"]]
        passing.sort(key=lambda row: (
            float(row.get("expectancy_r") or -999),
            float(row.get("win_rate") or 0),
            float(row["recovery_precision"].get("future_30pct_recovery_precision") or 0),
            -float(row.get("max_drawdown_r") or 999),
        ), reverse=True)
        selected = passing[0] if passing else None
        payload = {
            **common,
            "mode": "development",
            "development_gate": {
                "minimum_trades": 15,
                "minimum_win_rate": 0.75,
                "minimum_expectancy_r": 0.20,
                "one_sided_90_lcb_r": ">0",
                "maximum_drawdown_r": 5,
            },
            "variants": rows,
            "selected_for_forward_holdout": None if selected is None else {
                "variant_id": selected["variant_id"],
                "trade_count": selected["trade_count"],
                "win_rate": selected["win_rate"],
                "expectancy_r": selected["expectancy_r"],
                "one_sided_90_lcb_r": selected["one_sided_90_lcb_r"],
                "max_drawdown_r": selected["max_drawdown_r"],
            },
        }
        if selected is not None and args.selection_file:
            Path(args.selection_file).write_text(json.dumps({"variant_id": selected["variant_id"]}, indent=2) + "\n", encoding="utf-8")
        rows_summary, verdict = rows, f"Selected for forward holdout: **{selected['variant_id'] if selected else 'NONE'}**"
        title = "# V6 micro-acceptance development"
    else:
        if not args.variant_id:
            raise SystemExit("--variant-id required in holdout mode")
        _variant(args.variant_id)
        row = {"variant_id": args.variant_id, **_metrics(module, datasets, args.variant_id, config, initial_cash, spread)}
        verdict_code = _holdout_verdict(row)
        payload = {**common, "mode": "one_shot_holdout", "no_parameter_search": True, "selected_variant_id": args.variant_id, "result": row, "holdout_verdict": verdict_code}
        rows_summary, verdict = [row], f"Holdout verdict: **{verdict_code}**"
        title = "# V6 micro-acceptance one-shot holdout"

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [title, "", f"- Period: **{start} through {end}**", f"- Coverage: **{covered}/{requested}** (required >= {required})", "- Production strategy changed: **no**", "- Execution authority: **false**", "", "| Variant | Trades | Win rate | Exp R | 90% LCB R | Max DD R | >=30% recovery precision |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows_summary:
        precision = row["recovery_precision"].get("future_30pct_recovery_precision")
        lines.append(f"| {row['variant_id']} | {row['trade_count']} | {row['win_rate']} | {row['expectancy_r']} | {row['one_sided_90_lcb_r']} | {row['max_drawdown_r']} | {precision} |")
    lines.extend(["", verdict, ""])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
