from __future__ import annotations

"""Research-only V4 confirmed-recovery successor.

The frozen V3 recovery selector becomes a watch-state. Entry is allowed only
after a causal post-watch retest holds a predeclared fraction of the observed
recovery leg and a finalized 1m bar breaks the post-watch high on renewed volume.

This module is cache-only during development and never changes production
strategy configuration or execution authority.
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
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult, StrategySignal
from app.trading.strategy_v2_qualification import frozen_v2_config
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant

_ET = ZoneInfo("America/New_York")
_RETENTIONS = (Decimal("0.40"), Decimal("0.50"), Decimal("0.60"))
_MIN_RETRACE_OF_RECOVERY_LEG = Decimal("0.10")
_MIN_REBREAK_VOLUME_RATIO = Decimal("1.25")
_MAX_CONFIRM_MINUTES = 20
_SELECTOR_SHA256 = "5c98837cc96ad7c692d45b0bafff6a025f04f52599985cc6e85af734f6917607"


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Research V4 confirmed-recovery successor from frozen causal caches.")
    p.add_argument("--mode", choices=("development", "holdout"), required=True)
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--selector-source", default="/tmp/recovery_selector.py")
    p.add_argument("--retention", default="")
    p.add_argument("--selection-file", default="")
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _load_selector(path: str):
    spec = importlib.util.spec_from_file_location("recovery_selector_v4", path)
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
        i
        for i, bar in enumerate(regular)
        if time(9, 30) <= bar.end_time.astimezone(_ET).time() <= time(9, 45)
    ]
    if not opening_indexes:
        return None
    opening_high = max(regular[i].high for i in opening_indexes)
    high_index = next((i for i in opening_indexes if regular[i].high == opening_high), None)
    if high_index is None or high_index + 1 >= len(regular):
        return None
    lows = [bar.low for bar in regular[high_index + 1 :]]
    return min(lows) if lows else None


def _confirmed_recovery_evaluator(module, retention: Decimal) -> Callable:
    if retention <= 0 or retention >= 1:
        raise ValueError("retention must be between zero and one")

    base_evaluator = module._evaluator_for(_watch_rule(module))
    watch_cache: dict[tuple[str, str], dict[str, object]] = {}

    def evaluate(candidate, bars, config: GapPullbackConfig) -> GapPullbackResult:
        regular = list(_regular_bars(bars))
        if not regular:
            return base_evaluator(candidate, bars, config)

        session_key = regular[0].start_time.astimezone(_ET).date().isoformat()
        key = (session_key, candidate.instrument_id)
        watch = watch_cache.get(key)

        if watch is None:
            base_result = base_evaluator(candidate, bars, config)
            if base_result.state != "entry_ready" or base_result.signal is None:
                return base_result

            trough = _opening_trough(regular)
            watch_close = regular[-1].close
            if trough is None or trough <= 0 or watch_close <= trough:
                return base_result.model_copy(
                    update={
                        "state": "rejected",
                        "reason_code": "V4_WATCH_TROUGH_UNAVAILABLE",
                        "signal": None,
                        "transitions": tuple(base_result.transitions) + ("rejected",),
                    }
                )

            watch = {
                "watch_time": regular[-1].end_time,
                "watch_close": watch_close,
                "trough": trough,
                "result": base_result,
            }
            watch_cache[key] = watch
            return base_result.model_copy(
                update={
                    "state": "breakout_hold",
                    "reason_code": "V4_RECOVERY_WATCH_ARMED",
                    "signal": None,
                    "transitions": tuple(t for t in base_result.transitions if t != "entry_ready")
                    + ("breakout_hold",),
                }
            )

        watch_time = watch["watch_time"]
        watch_close = Decimal(str(watch["watch_close"]))
        trough = Decimal(str(watch["trough"]))
        watch_result = watch["result"]
        current = regular[-1]
        current_et = current.end_time.astimezone(_ET)

        if current_et.time() > config.last_entry_et:
            return watch_result.model_copy(
                update={
                    "state": "expired",
                    "reason_code": "V4_CONFIRMATION_ENTRY_WINDOW_CLOSED",
                    "signal": None,
                }
            )

        elapsed_minutes = Decimal(str((current.end_time - watch_time).total_seconds())) / Decimal("60")
        if elapsed_minutes > _MAX_CONFIRM_MINUTES:
            return watch_result.model_copy(
                update={
                    "state": "expired",
                    "reason_code": "V4_CONFIRMATION_TOO_SLOW",
                    "signal": None,
                }
            )

        post = [bar for bar in regular if bar.end_time > watch_time]
        if len(post) < 3:
            return watch_result.model_copy(
                update={
                    "state": "second_pullback",
                    "reason_code": "V4_WAITING_FOR_RETEST",
                    "signal": None,
                }
            )

        retest_bars = post[:-1]
        current = post[-1]
        recovery_leg = watch_close - trough
        if recovery_leg <= 0:
            return watch_result.model_copy(
                update={
                    "state": "rejected",
                    "reason_code": "V4_NON_POSITIVE_RECOVERY_LEG",
                    "signal": None,
                }
            )

        retest_low = min(bar.low for bar in retest_bars)
        retrace = (watch_close - retest_low) / recovery_leg
        max_retrace = Decimal("1") - retention
        if retrace < _MIN_RETRACE_OF_RECOVERY_LEG:
            return watch_result.model_copy(
                update={
                    "state": "second_pullback",
                    "reason_code": "V4_WAITING_FOR_MEANINGFUL_RETEST",
                    "signal": None,
                }
            )
        if retrace > max_retrace:
            return watch_result.model_copy(
                update={
                    "state": "rejected",
                    "reason_code": "V4_RETEST_BROKE_RETENTION_FLOOR",
                    "signal": None,
                }
            )

        rebreak_level = max(watch_close, max(bar.high for bar in retest_bars))
        if current.close <= rebreak_level:
            return watch_result.model_copy(
                update={
                    "state": "lower_high_break",
                    "reason_code": "V4_WAITING_FOR_REBREAK",
                    "signal": None,
                }
            )

        prior_volume = retest_bars[-5:]
        average_volume = sum((bar.volume for bar in prior_volume), Decimal("0")) / Decimal(len(prior_volume))
        volume_ratio = current.volume / average_volume if average_volume > 0 else Decimal("0")
        if volume_ratio < _MIN_REBREAK_VOLUME_RATIO:
            return watch_result.model_copy(
                update={
                    "state": "lower_high_break",
                    "reason_code": "V4_REBREAK_VOLUME_WEAK",
                    "signal": None,
                    "features": watch_result.features.model_copy(
                        update={
                            "second_pullback_depth_pct": retrace * Decimal("100"),
                            "breakout_volume_ratio": volume_ratio,
                        }
                    ),
                }
            )

        stop = retest_low * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
        risk = current.close - stop
        if risk <= 0:
            return watch_result.model_copy(
                update={
                    "state": "rejected",
                    "reason_code": "V4_NON_POSITIVE_RISK_DISTANCE",
                    "signal": None,
                }
            )

        features = watch_result.features.model_copy(
            update={
                "second_pullback_depth_pct": retrace * Decimal("100"),
                "breakout_volume_ratio": volume_ratio,
            }
        )
        signal = StrategySignal(
            instrument_id=candidate.instrument_id,
            state="entry_ready",
            entry_price=current.close,
            stop_price=stop,
            target_price=current.close + risk * config.reward_multiple,
            risk_per_share=risk,
            reason_code=f"CONFIRMED_RECOVERY_V4_RETENTION_{int(retention * 100)}",
            quality_score=watch_result.signal.quality_score,
        )
        transitions = tuple(t for t in watch_result.transitions if t != "entry_ready") + (
            "second_pullback",
            "higher_low_confirmed",
            "lower_high_break",
            "entry_ready",
        )
        return watch_result.model_copy(
            update={
                "state": "entry_ready",
                "reason_code": signal.reason_code,
                "signal": signal,
                "features": features,
                "transitions": transitions,
                "evaluated_bar_count": len(regular),
            }
        )

    return evaluate


def _signal_precision(datasets, evaluator_factory: Callable[[], Callable], config: GapPullbackConfig) -> dict[str, object]:
    evaluator = evaluator_factory()
    rows: list[dict[str, object]] = []
    for dataset in datasets:
        for candidate in dataset.universe.candidates:
            bars = tuple(dataset.bars_by_instrument[candidate.instrument_id])
            signal_index = None
            signal_result = None
            for i in range(1, len(bars) + 1):
                result = evaluator(candidate, bars[:i], config)
                if result.state == "entry_ready" and result.signal is not None:
                    signal_index = i - 1
                    signal_result = result
                    break
            if signal_index is None:
                continue
            prefix = list(_regular_bars(bars[: signal_index + 1]))
            trough = _opening_trough(prefix)
            if trough is None or trough <= 0:
                continue
            signal_time = prefix[-1].end_time
            future = [bar for bar in _regular_bars(bars) if bar.end_time >= signal_time]
            if not future:
                continue
            future_high = max(bar.high for bar in future)
            recovery_pct = (future_high / trough - Decimal("1")) * Decimal("100")
            rows.append(
                {
                    "session_date": dataset.session_date.isoformat(),
                    "instrument_id": candidate.instrument_id,
                    "signal_time": signal_time.isoformat(),
                    "future_max_recovery_from_trough_pct": str(recovery_pct),
                    "future_recovers_30pct": recovery_pct >= Decimal("30"),
                    "reason_code": signal_result.reason_code,
                }
            )
    positives = sum(bool(row["future_recovers_30pct"]) for row in rows)
    return {
        "signal_count": len(rows),
        "future_30pct_recovery_count": positives,
        "future_30pct_recovery_precision": (positives / len(rows)) if rows else None,
        "signals": rows,
    }


def _metrics(module, datasets, retention: Decimal, config, initial_cash: Decimal, spread: Decimal) -> dict[str, object]:
    evaluator_factory = lambda: _confirmed_recovery_evaluator(module, retention)
    original_rsi = strategy_backtest.relative_strength_index
    strategy_backtest.relative_strength_index = (
        lambda values, period: [Decimal("0")] * max(0, len(values) - int(period))
    )
    try:
        with module._research_evaluator(evaluator_factory()):
            run = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
    finally:
        strategy_backtest.relative_strength_index = original_rsi
    trade_metrics = module._trade_metrics(run)
    precision = _signal_precision(datasets, evaluator_factory, config)
    return {
        **trade_metrics,
        "trades": run.get("trades"),
        "recovery_precision": precision,
    }


def _development_gate(row: dict[str, object]) -> bool:
    count = int(row.get("trade_count") or 0)
    win = float(row.get("win_rate") or 0)
    exp = float(row.get("expectancy_r") or -999)
    lcb = float(row.get("one_sided_90_lcb_r") or -999)
    dd = float(row.get("max_drawdown_r") or 999)
    return count >= 12 and win >= 0.75 and exp >= 0.20 and lcb > 0 and dd <= 5


def _holdout_verdict(row: dict[str, object]) -> str:
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


def main() -> int:
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
        raise SystemExit(
            f"complete frozen cache required: {coverage['covered_sessions']}/{coverage['requested_sessions']}"
        )

    config = frozen_v2_config().model_copy(update={"reward_multiple": Decimal("1.0")})
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    common = {
        "purpose": "failed-recovery vs confirmed-recovery discrimination",
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
        "confirmation": {
            "watch": "frozen V3 recovery selector",
            "minimum_retrace_of_observed_recovery_leg": str(_MIN_RETRACE_OF_RECOVERY_LEG),
            "retention_axis": [str(value) for value in _RETENTIONS],
            "rebreak": "finalized close > watch close and every post-watch retest-bar high",
            "minimum_rebreak_volume_ratio_vs_prior_5_bars": str(_MIN_REBREAK_VOLUME_RATIO),
            "maximum_watch_to_confirmation_minutes": _MAX_CONFIRM_MINUTES,
            "stop": "15 bps below observed post-watch retest low",
            "entry": "next eligible 1m execution bar",
        },
    }

    if args.mode == "development":
        rows: list[dict[str, object]] = []
        for retention in _RETENTIONS:
            row = {
                "variant_id": f"confirmed_recovery_retain_{int(retention * 100)}",
                "retention": str(retention),
                **_metrics(module, datasets, retention, config, initial_cash, spread),
            }
            row["development_gate_pass"] = _development_gate(row)
            rows.append(row)

        passing = [row for row in rows if row["development_gate_pass"]]
        passing.sort(
            key=lambda row: (
                float(row.get("expectancy_r") or -999),
                float(row.get("win_rate") or 0),
                float(row["recovery_precision"].get("future_30pct_recovery_precision") or 0),
                -float(row.get("max_drawdown_r") or 999),
            ),
            reverse=True,
        )
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
            "selected_for_new_holdout": None
            if selected is None
            else {k: v for k, v in selected.items() if k not in {"trades", "recovery_precision"}},
        }
        if selected is not None and args.selection_file:
            Path(args.selection_file).write_text(
                json.dumps(
                    {
                        "variant_id": selected["variant_id"],
                        "retention": selected["retention"],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        title = "# V4 confirmed-recovery development"
        rows_for_summary = rows
        verdict = f"Selected for new holdout: **{selected['variant_id'] if selected else 'NONE'}**"
    else:
        if not args.retention:
            raise SystemExit("--retention is required in holdout mode")
        retention = Decimal(args.retention)
        if retention not in _RETENTIONS:
            raise SystemExit("holdout retention must be one of the predeclared development variants")
        row = {
            "variant_id": f"confirmed_recovery_retain_{int(retention * 100)}",
            "retention": str(retention),
            **_metrics(module, datasets, retention, config, initial_cash, spread),
        }
        verdict_code = _holdout_verdict(row)
        payload = {
            **common,
            "mode": "one_shot_holdout",
            "no_parameter_search": True,
            "selected_retention": str(retention),
            "result": row,
            "holdout_verdict": verdict_code,
            "holdout_tiers": {
                "GOLD": ">=5 trades, >=75% wins, >=+0.20R expectancy, <=3R DD",
                "ROBUST": ">=5 trades, >=60% wins, >0R expectancy, <=5R DD",
                "UNDERPOWERED": "<5 trades",
                "FAIL": "otherwise",
            },
        }
        title = "# V4 confirmed-recovery one-shot holdout"
        rows_for_summary = [row]
        verdict = f"Holdout verdict: **{verdict_code}**"

    (output / "results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [
        title,
        "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']}**",
        "- Production strategy changed: **no**",
        "- Execution authority: **false**",
        "- RSI exit: **disabled**",
        "",
        "| Variant | Trades | Win rate | Exp R | 90% LCB R | Max DD R | >=30% recovery precision |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows_for_summary:
        precision = row["recovery_precision"].get("future_30pct_recovery_precision")
        lines.append(
            f"| {row['variant_id']} | {row['trade_count']} | {row['win_rate']} | {row['expectancy_r']} | "
            f"{row['one_sided_90_lcb_r']} | {row['max_drawdown_r']} | {precision} |"
        )
    lines.extend(["", verdict, ""])
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
