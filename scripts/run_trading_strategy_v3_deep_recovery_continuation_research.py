from __future__ import annotations

"""Same-block feasibility replay for a causal deep-recovery continuation branch.

This hypothesis was derived after the development recovery census, so its metrics
are explicitly in-sample and cannot qualify execution. The purpose is only to
check whether waiting for an observed >=30% recovery, VWAP reclaim and short-term
breakout leaves a mechanically plausible continuation trade under the existing
paper fill/risk/management engine.
"""

import argparse
import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from app.trading.gapper_dataset import GapperCandidate
from app.trading.models import MarketBar
from app.trading.strategies.gap_pullback import _ET, _regular_bars, session_vwap
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult, StrategySignal
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
from scripts.run_trading_strategy_v3_canonical_path_research import (
    _base_features,
    _quality,
    _research_evaluator,
    _result,
)


_OPENING_END = time(9, 45)
_MINIMUM_SELLOFF_PCT = Decimal("5")
_RECOVERY_TRIGGER_PCT = Decimal("30")
_BREAKOUT_LOOKBACK = 3
_STOP_LOOKBACK = 5


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Feasibility replay for the census-derived deep-recovery continuation branch.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--development-start", default="2025-10-01")
    p.add_argument("--development-end", default="2026-02-27")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--output-dir", default="artifacts/v3-deep-recovery-continuation")
    return p.parse_args()


def _context(
    regular: list[MarketBar],
) -> dict[str, Decimal | int | str | None]:
    if not regular:
        return {}
    opening = [bar for bar in regular if bar.start_time.astimezone(_ET).time() < _OPENING_END]
    if not opening or regular[-1].end_time.astimezone(_ET).time() < _OPENING_END:
        return {}
    opening_high = max(bar.high for bar in opening)
    opening_index = next(index for index, bar in enumerate(regular) if bar.high == opening_high)
    post_opening = regular[opening_index + 1 :]
    if not post_opening:
        return {"opening_high": opening_high}
    running_low = min(bar.low for bar in post_opening)
    running_low_index = max(index for index, bar in enumerate(regular) if bar.low == running_low)
    selloff_pct = (opening_high - running_low) / opening_high * Decimal("100")
    current = regular[-1]
    recovery_pct = (current.close / running_low - Decimal("1")) * Decimal("100") if running_low > 0 else Decimal("0")
    prior = regular[max(0, len(regular) - 1 - _BREAKOUT_LOOKBACK) : -1]
    prior_breakout_high = max((bar.high for bar in prior), default=None)
    stop_window = regular[max(0, len(regular) - _STOP_LOOKBACK) :]
    stop_reference = min((bar.low for bar in stop_window), default=None)
    return {
        "opening_high": opening_high,
        "opening_high_index": opening_index,
        "running_low": running_low,
        "running_low_index": running_low_index,
        "selloff_pct": selloff_pct,
        "recovery_pct": recovery_pct,
        "prior_breakout_high": prior_breakout_high,
        "stop_reference": stop_reference,
    }


def evaluate_deep_recovery_continuation(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
) -> GapPullbackResult:
    regular = _regular_bars(list(bars))
    transitions = ["discovered"]
    features, rejection = _base_features(candidate, config)
    if rejection is not None:
        return _result(candidate, "rejected", rejection, transitions + ["rejected"], features, regular)
    transitions.append("qualified_gap")
    if not regular:
        return _result(candidate, "qualified_gap", "WAITING_FOR_REGULAR_SESSION", transitions, features, regular)

    current = regular[-1]
    current_et = current.end_time.astimezone(_ET)
    minutes_since_open = max(0, current_et.hour * 60 + current_et.minute - (9 * 60 + 30))
    features = features.model_copy(update={"minutes_since_open": minutes_since_open})
    if current_et.time() < _OPENING_END:
        return _result(candidate, "opening_impulse", "WAITING_FOR_OPENING_RANGE", transitions + ["opening_impulse"], features, regular)
    if current_et.time() > config.last_entry_et:
        return _result(candidate, "expired", "ENTRY_WINDOW_CLOSED", transitions + ["expired"], features, regular)

    context = _context(regular)
    opening_high = context.get("opening_high")
    running_low = context.get("running_low")
    selloff_pct = context.get("selloff_pct")
    recovery_pct = context.get("recovery_pct")
    if not isinstance(opening_high, Decimal) or not isinstance(running_low, Decimal):
        return _result(candidate, "opening_impulse", "WAITING_FOR_POST_OPENING_LOW", transitions + ["opening_impulse"], features, regular)
    if not isinstance(selloff_pct, Decimal) or selloff_pct < _MINIMUM_SELLOFF_PCT:
        features = features.model_copy(update={"opening_impulse_pct": Decimal("0") - selloff_pct if isinstance(selloff_pct, Decimal) else None})
        return _result(candidate, "first_pullback", "DEEP_RECOVERY_SELLOFF_TOO_SHALLOW", transitions + ["first_pullback"], features, regular)

    vwap = session_vwap(regular)
    features = features.model_copy(update={
        "pullback_depth_pct": selloff_pct,
        "l1": running_low,
        "session_vwap": vwap,
        "vwap_distance_pct": ((current.close / vwap - Decimal("1")) * Decimal("100")) if vwap and vwap > 0 else None,
        "pullback_quality_score": 2,
    })
    transitions.extend(["first_pullback", "first_low_confirmed"])
    if not isinstance(recovery_pct, Decimal) or recovery_pct < _RECOVERY_TRIGGER_PCT:
        return _result(candidate, "first_low_confirmed", "WAITING_FOR_30PCT_RECOVERY", transitions, features, regular)
    if vwap is None or current.close <= vwap:
        return _result(candidate, "vwap_reclaim", "RECOVERY_BELOW_VWAP", transitions + ["vwap_reclaim"], features, regular)

    prior_breakout_high = context.get("prior_breakout_high")
    if not isinstance(prior_breakout_high, Decimal) or current.close <= prior_breakout_high:
        return _result(candidate, "lower_high_break", "WAITING_FOR_3BAR_BREAKOUT", transitions + ["vwap_reclaim", "lower_high_break"], features, regular)

    stop_reference = context.get("stop_reference")
    if not isinstance(stop_reference, Decimal) or stop_reference <= 0:
        return _result(candidate, "rejected", "STOP_REFERENCE_UNAVAILABLE", transitions + ["rejected"], features, regular)
    stop = stop_reference * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
    risk = current.close - stop
    if risk <= 0:
        return _result(candidate, "rejected", "NON_POSITIVE_RISK_DISTANCE", transitions + ["rejected"], features, regular)

    features = features.model_copy(update={
        "reclaim_break_score": 2,
        "opening_structure_score": max(features.opening_structure_score, 1),
    })
    signal = StrategySignal(
        instrument_id=candidate.instrument_id,
        state="entry_ready",
        entry_price=current.close,
        stop_price=stop,
        target_price=current.close + risk * config.reward_multiple,
        risk_per_share=risk,
        reason_code="DEEP_RECOVERY_30PCT_CONTINUATION_RESEARCH",
        quality_score=_quality(features),
    )
    transitions.extend(["vwap_reclaim", "lower_high_break", "entry_ready"])
    return _result(candidate, "entry_ready", signal.reason_code, transitions, features, regular, signal)


def _trade_context(datasets, trade_row: dict[str, object]) -> dict[str, object]:
    instrument = str(trade_row["instrument_id"])
    entry_at = datetime.fromisoformat(str(trade_row["entry_time"]))
    session_date = entry_at.astimezone(_ET).date()
    for dataset in datasets:
        if dataset.session_date != session_date:
            continue
        bars = dataset.bars_by_instrument.get(instrument)
        if not bars:
            continue
        # The signal prefix contains only bars finalized by the next-bar entry.
        prefix = [bar for bar in bars if bar.end_time <= entry_at]
        regular = _regular_bars(prefix)
        context = _context(regular)
        if context and regular:
            current = regular[-1]
            stop_ref = context.get("stop_reference")
            risk_pct = None
            if isinstance(stop_ref, Decimal) and current.close > 0:
                stop = stop_ref * (Decimal("1") - Decimal("15") / Decimal("10000"))
                risk_pct = (current.close - stop) / current.close * Decimal("100")
            return {
                "session_date": dataset.session_date.isoformat(),
                "signal_cutoff": current.end_time.isoformat(),
                "signal_close": str(current.close),
                "selloff_pct": str(context.get("selloff_pct")) if context.get("selloff_pct") is not None else None,
                "signal_recovery_pct": str(context.get("recovery_pct")) if context.get("recovery_pct") is not None else None,
                "signal_risk_pct": str(risk_pct) if risk_pct is not None else None,
            }
    return {}


def main() -> int:
    args = _args()
    start = date.fromisoformat(args.development_start)
    end = date.fromisoformat(args.development_end)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)

    basis_strategy = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(basis_strategy, spread)
    datasets, coverage = _load_block(Path(args.dataset_cache_dir) / namespace, start, end)
    if int(coverage["covered_sessions"]) != int(coverage["requested_sessions"]):
        raise SystemExit(f"complete development cache required: {coverage['covered_sessions']}/{coverage['requested_sessions']}; provider access prohibited")

    frozen = frozen_v2_config()
    baseline = _run_variant(datasets, frozen, initial_cash=initial_cash, spread=spread)
    with _research_evaluator(evaluate_deep_recovery_continuation):
        deep = _run_variant(datasets, frozen, initial_cash=initial_cash, spread=spread)

    for trade in deep["trades"]:
        trade.update(_trade_context(datasets, trade))

    baseline_keys = {(str(row["instrument_id"]), str(row["entry_time"])[:10]) for row in baseline["trades"]}
    deep_keys = {(str(row["instrument_id"]), str(row["entry_time"])[:10]) for row in deep["trades"]}
    overlap = sorted(baseline_keys & deep_keys)

    output = {
        "purpose": "in-sample feasibility only for census-derived deep-recovery continuation",
        "production_strategy_changed": False,
        "execution_authority": False,
        "frozen_v2_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "cache_namespace": namespace,
        "cache_basis": basis,
        "coverage": coverage,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "rule": {
            "opening_window_et": "09:30-09:45",
            "minimum_selloff_pct": "5",
            "observed_close_recovery_pct": "30",
            "require_above_session_vwap": True,
            "prior_breakout_bars": _BREAKOUT_LOOKBACK,
            "stop_lookback_bars": _STOP_LOOKBACK,
            "stop_buffer_bps": str(frozen.stop_buffer_bps),
            "last_entry_et": frozen.last_entry_et.isoformat(),
            "management": {
                "reward_multiple": str(frozen.reward_multiple),
                "profit_protection_trigger_r": str(frozen.v2_profit_protection_trigger_r),
                "protected_stop_r": str(frozen.v2_protected_stop_r),
                "max_hold_minutes": frozen.v2_max_hold_minutes,
            },
        },
        "frozen_v2_reference": baseline,
        "deep_recovery_feasibility": deep,
        "trade_overlap": {
            "count": len(overlap),
            "instrument_session_keys": [f"{instrument}|{session}" for instrument, session in overlap],
        },
        "interpretation": "Derived after development census. Positive metrics can justify prospective SHADOW collection only; negative metrics reject this exact feasibility rule without same-sample tuning.",
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Deep-recovery continuation feasibility — development block only",
        "",
        "**IN-SAMPLE FEASIBILITY ONLY. This rule was formulated after the recovery census and cannot qualify execution.**",
        "",
        f"- Development: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']} sessions**",
        "- Provider calls: **none**",
        "- March loaded: **no**",
        "- Frozen V2 changed: **no**",
        "",
        "| Path | Trades | Triggers | W-L | Expectancy R | 90% LCB R | Max DD R | P&L |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| Frozen V2 | {baseline['trade_count']} | {baseline['trigger_count']} | {baseline['win_count']}-{baseline['loss_count']} | {baseline['expectancy_r']} | {baseline['one_sided_90_lcb_r']} | {baseline['max_drawdown_r']} | {baseline['pnl']} |",
        f"| Deep recovery | {deep['trade_count']} | {deep['trigger_count']} | {deep['win_count']}-{deep['loss_count']} | {deep['expectancy_r']} | {deep['one_sided_90_lcb_r']} | {deep['max_drawdown_r']} | {deep['pnl']} |",
        "",
        f"Trade overlap: **{len(overlap)}** instrument/session rows.",
        "",
        "## Deep-recovery trades",
        "",
        "| Session | Symbol | Entry | Exit | R | MFE R | MAE R | Selloff % | Signal recovery % | Signal risk % | Exit reason |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in deep["trades"]:
        lines.append(
            f"| {row.get('session_date','?')} | {str(row['instrument_id']).split(':')[-1]} | {row['entry_time']} | {row['exit_time']} | "
            f"{row['r_multiple']} | {row['mfe_r']} | {row['mae_r']} | {row.get('selloff_pct','?')} | "
            f"{row.get('signal_recovery_pct','?')} | {row.get('signal_risk_pct','?')} | {row['exit_reason']} |"
        )
    lines.extend([
        "",
        "> Any positive result is hypothesis-generation evidence only. The next admissible step is prospective SHADOW, not AUTO PAPER or a March rescue.",
        "",
    ])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
