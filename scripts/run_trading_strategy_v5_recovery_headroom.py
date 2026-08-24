from __future__ import annotations

"""Research-only V5 recovery-headroom successor.

The frozen V3 recovery selector remains the causal entry checkpoint. V5 filters
that first checkpoint by the remaining distance to the frozen >=30% recovery
threshold expressed in units of the same structural risk used for the trade.

The purpose is to align the recovery label with actual trade economics without
waiting for a later confirmation bar that consumes the remaining upside.
"""

import argparse
import importlib.util
import json
import sys
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import app.trading.strategy_backtest as strategy_backtest
from app.trading.strategies.gap_pullback import _regular_bars
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult
from app.trading.strategy_v2_qualification import frozen_v2_config
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant

_ET = ZoneInfo("America/New_York")
_HEADROOM_THRESHOLDS = (Decimal("0.75"), Decimal("1.00"), Decimal("1.25"))
_SELECTOR_SHA256 = "5c98837cc96ad7c692d45b0bafff6a025f04f52599985cc6e85af734f6917607"


def _args():
    p = argparse.ArgumentParser(description="Research V5 recovery headroom from frozen causal caches.")
    p.add_argument("--mode", choices=("development", "holdout"), required=True)
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--selector-source", default="/tmp/recovery_selector.py")
    p.add_argument("--minimum-headroom-r", default="")
    p.add_argument("--selection-file", default="")
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _load_selector(path: str):
    spec = importlib.util.spec_from_file_location("recovery_selector_v5", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load frozen recovery selector source")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _watch_rule(module):
    return module.Rule(
        (
            module.Predicate("rebound>=20", "recovery", "recovery_pct", ">=", 20),
            module.Predicate("retrace>=80", "retracement", "retracement_pct", ">=", 80),
            module.Predicate("selloff>=15", "selloff", "selloff_pct", ">=", 15),
            module.Predicate("vol5x>=1.5", "volume_ratio", "volume_ratio5", ">=", 1.5),
        )
    )


def _opening_trough(regular) -> Decimal | None:
    opening_indexes = [
        i for i, bar in enumerate(regular)
        if time(9, 30) <= bar.end_time.astimezone(_ET).time() <= time(9, 45)
    ]
    if not opening_indexes:
        return None
    opening_high = max(regular[i].high for i in opening_indexes)
    high_index = next((i for i in opening_indexes if regular[i].high == opening_high), None)
    if high_index is None or high_index + 1 >= len(regular):
        return None
    lows = [bar.low for bar in regular[high_index + 1:]]
    return min(lows) if lows else None


def _headroom_evaluator(module, minimum_headroom_r: Decimal) -> Callable:
    base = module._evaluator_for(_watch_rule(module))
    terminal: dict[tuple[str, str], GapPullbackResult] = {}

    def evaluate(candidate, bars, config: GapPullbackConfig) -> GapPullbackResult:
        regular = list(_regular_bars(bars))
        if not regular:
            return base(candidate, bars, config)
        key = (regular[0].start_time.astimezone(_ET).date().isoformat(), candidate.instrument_id)
        if key in terminal:
            return terminal[key]

        result = base(candidate, bars, config)
        if result.state != "entry_ready" or result.signal is None:
            return result

        trough = _opening_trough(regular)
        if trough is None or trough <= 0:
            rejected = result.model_copy(update={
                "state": "rejected",
                "reason_code": "V5_TROUGH_UNAVAILABLE",
                "signal": None,
            })
            terminal[key] = rejected
            return rejected

        current = regular[-1]
        prior5 = regular[-5:]
        stop = min(bar.low for bar in prior5) * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
        risk = current.close - stop
        threshold_price = trough * Decimal("1.30")
        if risk <= 0 or threshold_price <= current.close:
            rejected = result.model_copy(update={
                "state": "rejected",
                "reason_code": "V5_NO_POSITIVE_THRESHOLD_HEADROOM",
                "signal": None,
            })
            terminal[key] = rejected
            return rejected

        headroom_r = (threshold_price - current.close) / risk
        features = result.features.model_copy(update={
            "second_pullback_depth_pct": headroom_r,
        })
        if headroom_r < minimum_headroom_r:
            rejected = result.model_copy(update={
                "state": "rejected",
                "reason_code": "V5_30PCT_THRESHOLD_HEADROOM_TOO_SMALL",
                "signal": None,
                "features": features,
            })
            terminal[key] = rejected
            return rejected

        signal = result.signal.model_copy(update={
            "stop_price": stop,
            "risk_per_share": risk,
            "target_price": current.close + risk * config.reward_multiple,
            "reason_code": f"RECOVERY_HEADROOM_V5_{minimum_headroom_r}R",
        })
        return result.model_copy(update={
            "signal": signal,
            "reason_code": signal.reason_code,
            "features": features,
        })

    return evaluate


def _signal_precision(datasets, evaluator_factory: Callable[[], Callable], config) -> dict[str, object]:
    evaluator = evaluator_factory()
    rows = []
    for dataset in datasets:
        for candidate in dataset.universe.candidates:
            bars = tuple(dataset.bars_by_instrument[candidate.instrument_id])
            signal_index = None
            for i in range(1, len(bars) + 1):
                result = evaluator(candidate, bars[:i], config)
                if result.state == "entry_ready" and result.signal is not None:
                    signal_index = i - 1
                    break
            if signal_index is None:
                continue
            regular_prefix = list(_regular_bars(bars[: signal_index + 1]))
            trough = _opening_trough(regular_prefix)
            if trough is None or trough <= 0:
                continue
            signal_time = regular_prefix[-1].end_time
            future = [bar for bar in _regular_bars(bars) if bar.end_time >= signal_time]
            future_high = max(bar.high for bar in future)
            recovery_pct = (future_high / trough - Decimal("1")) * Decimal("100")
            rows.append({
                "session_date": dataset.session_date.isoformat(),
                "instrument_id": candidate.instrument_id,
                "signal_time": signal_time.isoformat(),
                "future_max_recovery_from_trough_pct": str(recovery_pct),
                "future_recovers_30pct": recovery_pct >= Decimal("30"),
            })
    positives = sum(bool(row["future_recovers_30pct"]) for row in rows)
    return {
        "signal_count": len(rows),
        "future_30pct_recovery_count": positives,
        "future_30pct_recovery_precision": positives / len(rows) if rows else None,
        "signals": rows,
    }


def _metrics(module, datasets, threshold: Decimal, config, initial_cash: Decimal, spread: Decimal):
    factory = lambda: _headroom_evaluator(module, threshold)
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
        "recovery_precision": _signal_precision(datasets, factory, config),
    }


def _development_gate(row):
    return (
        int(row.get("trade_count") or 0) >= 12
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
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    basis = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, cache_basis = _cache_namespace(basis, spread)
    datasets, coverage = _load_block(Path(args.dataset_cache_dir) / namespace, start, end)
    if int(coverage["covered_sessions"]) != int(coverage["requested_sessions"]):
        raise SystemExit(f"complete frozen cache required: {coverage['covered_sessions']}/{coverage['requested_sessions']}")

    config = frozen_v2_config().model_copy(update={"reward_multiple": Decimal("1.0")})
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    common = {
        "purpose": "align frozen >=30% recovery label with immediate-entry trade headroom",
        "research_only": True,
        "production_strategy_changed": False,
        "execution_authority": False,
        "selector_source_sha256": _SELECTOR_SHA256,
        "watch_rule": _watch_rule(module).key,
        "period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "cache_namespace": namespace,
        "cache_basis": cache_basis,
        "reward_multiple": "1.0",
        "rsi_exit": "disabled",
        "profit_protection": "+0.75R arm -> +0.25R protected stop",
        "max_hold_minutes": 60,
        "headroom_definition": "(observed_trough*1.30 - signal_close) / (signal_close - latest5_low_minus_15bps)",
        "headroom_axis_r": [str(x) for x in _HEADROOM_THRESHOLDS],
        "entry": "original frozen V3 watch signal; next eligible 1m execution bar",
    }

    if args.mode == "development":
        rows = []
        for threshold in _HEADROOM_THRESHOLDS:
            row = {
                "variant_id": f"recovery_headroom_{threshold}R",
                "minimum_headroom_r": str(threshold),
                **_metrics(module, datasets, threshold, config, initial_cash, spread),
            }
            row["development_gate_pass"] = _development_gate(row)
            rows.append(row)
        passing = [r for r in rows if r["development_gate_pass"]]
        passing.sort(key=lambda r: (
            float(r.get("expectancy_r") or -999),
            float(r.get("win_rate") or 0),
            float(r["recovery_precision"].get("future_30pct_recovery_precision") or 0),
            -float(r.get("max_drawdown_r") or 999),
        ), reverse=True)
        selected = passing[0] if passing else None
        payload = {
            **common,
            "mode": "development",
            "development_block_includes_failed_march_holdout": True,
            "provider_calls": 0,
            "development_gate": {
                "minimum_trades": 12,
                "minimum_win_rate": 0.75,
                "minimum_expectancy_r": 0.20,
                "one_sided_90_lcb_r": ">0",
                "maximum_drawdown_r": 5,
            },
            "variants": rows,
            "selected_for_new_holdout": None if selected is None else {
                "variant_id": selected["variant_id"],
                "minimum_headroom_r": selected["minimum_headroom_r"],
                "trade_count": selected["trade_count"],
                "win_rate": selected["win_rate"],
                "expectancy_r": selected["expectancy_r"],
                "one_sided_90_lcb_r": selected["one_sided_90_lcb_r"],
                "max_drawdown_r": selected["max_drawdown_r"],
            },
        }
        if selected is not None and args.selection_file:
            Path(args.selection_file).write_text(json.dumps({
                "variant_id": selected["variant_id"],
                "minimum_headroom_r": selected["minimum_headroom_r"],
            }, indent=2) + "\n", encoding="utf-8")
        rows_summary = rows
        verdict = f"Selected for new holdout: **{selected['variant_id'] if selected else 'NONE'}**"
        title = "# V5 recovery-headroom development"
    else:
        if not args.minimum_headroom_r:
            raise SystemExit("--minimum-headroom-r is required in holdout mode")
        threshold = Decimal(args.minimum_headroom_r)
        if threshold not in _HEADROOM_THRESHOLDS:
            raise SystemExit("holdout threshold must be one of the predeclared development variants")
        row = {
            "variant_id": f"recovery_headroom_{threshold}R",
            "minimum_headroom_r": str(threshold),
            **_metrics(module, datasets, threshold, config, initial_cash, spread),
        }
        verdict_code = _holdout_verdict(row)
        payload = {
            **common,
            "mode": "one_shot_holdout",
            "no_parameter_search": True,
            "selected_minimum_headroom_r": str(threshold),
            "result": row,
            "holdout_verdict": verdict_code,
        }
        rows_summary = [row]
        verdict = f"Holdout verdict: **{verdict_code}**"
        title = "# V5 recovery-headroom one-shot holdout"

    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [
        title, "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']}**",
        "- Production strategy changed: **no**",
        "- Execution authority: **false**",
        "- Entry timing: **original recovery watch signal**",
        "",
        "| Variant | Trades | Win rate | Exp R | 90% LCB R | Max DD R | >=30% recovery precision |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows_summary:
        precision = row["recovery_precision"].get("future_30pct_recovery_precision")
        lines.append(
            f"| {row['variant_id']} | {row['trade_count']} | {row['win_rate']} | {row['expectancy_r']} | "
            f"{row['one_sided_90_lcb_r']} | {row['max_drawdown_r']} | {precision} |"
        )
    lines.extend(["", verdict, ""])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
