from __future__ import annotations

"""Cache-only development replay for the frozen delayed-base V3 hypothesis.

This is a separately formulated successor state machine. It does not reuse the
failed-selloff L1/B1/L2 selector, does not alter frozen V2, does not call a
provider, and never loads March.
"""

import argparse
import json
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

from app.trading.gapper_dataset import GapperCandidate
from app.trading.models import MarketBar
from app.trading.strategies.gap_pullback import _ET, _regular_bars, session_vwap
from app.trading.strategies.models import GapPullbackConfig, GapPullbackFeatures, GapPullbackResult, StrategySignal
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator


_OR_END = time(10, 0)
_POST_BASE_MIN_START = time(10, 0)
_BASE_MINUTES = 15


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay delayed-base acceptance V3 on cached development data only.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--development-start", default="2025-10-01")
    p.add_argument("--development-end", default="2026-02-27")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--output-dir", default="artifacts/v3-delayed-base-acceptance")
    return p.parse_args()


def _base_features(candidate: GapperCandidate) -> GapPullbackFeatures:
    return GapPullbackFeatures(
        gap_pct=candidate.gap_pct,
        spread_bps=candidate.spread_bps,
        tod_rvol=candidate.tod_rvol,
        float_shares=candidate.float_shares,
        catalyst_evidence_count=len(candidate.catalyst_evidence_ids),
        dilution_flags=tuple(candidate.dilution_flags),
    )


def _result(
    candidate: GapperCandidate,
    *,
    state: str,
    reason: str,
    regular: list[MarketBar],
    features: GapPullbackFeatures,
    transitions: tuple[str, ...],
    signal: StrategySignal | None = None,
) -> GapPullbackResult:
    return GapPullbackResult(
        instrument_id=candidate.instrument_id,
        state=state,
        reason_code=reason,
        features=features,
        transitions=transitions,
        signal=signal,
        evaluated_bar_count=len(regular),
    )


def evaluate_delayed_base_acceptance(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
) -> GapPullbackResult:
    regular = _regular_bars(bars)
    features = _base_features(candidate)

    rejection: str | None = None
    if candidate.gap_pct < config.minimum_gap_pct:
        rejection = "GAP_BELOW_MINIMUM"
    elif not config.minimum_price <= candidate.premarket_price <= config.maximum_price:
        rejection = "PRICE_OUT_OF_RANGE"
    elif candidate.premarket_dollar_volume < config.minimum_premarket_dollar_volume:
        rejection = "PREMARKET_DOLLAR_VOLUME_LOW"
    elif candidate.tod_rvol is None:
        rejection = "TOD_RVOL_MISSING"
    elif candidate.tod_rvol < config.minimum_tod_rvol:
        rejection = "TOD_RVOL_LOW"
    elif candidate.spread_bps is None:
        rejection = "SPREAD_MISSING"
    elif candidate.spread_bps > config.maximum_spread_bps:
        rejection = "SPREAD_TOO_WIDE"
    if rejection:
        return _result(
            candidate,
            state="rejected",
            reason=rejection,
            regular=regular,
            features=features,
            transitions=("discovered", "rejected"),
        )

    if not regular:
        return _result(
            candidate,
            state="qualified_gap",
            reason="WAITING_FOR_REGULAR_SESSION",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap"),
        )

    current = regular[-1]
    current_et = current.end_time.astimezone(_ET)
    minutes_since_open = max(0, current_et.hour * 60 + current_et.minute - (9 * 60 + 30))
    features = features.model_copy(update={"minutes_since_open": minutes_since_open})
    if current_et.time() > config.last_entry_et:
        return _result(
            candidate,
            state="expired",
            reason="ENTRY_WINDOW_CLOSED",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "expired"),
        )

    opening = [bar for bar in regular if bar.start_time.astimezone(_ET).time() < _OR_END]
    if current.start_time.astimezone(_ET).time() < time(10, 15) or not opening:
        return _result(
            candidate,
            state="opening_impulse",
            reason="OBSERVING_OPEN_AND_POST_OPEN_BASE",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "opening_impulse"),
        )

    opening_high = max(bar.high for bar in opening)
    opening_low = min(bar.low for bar in opening)
    if opening_low <= 0 or opening_high <= opening_low:
        return _result(
            candidate,
            state="rejected",
            reason="INVALID_OPENING_RANGE",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "rejected"),
        )
    opening_range_pct = (opening_high / opening_low - Decimal("1")) * Decimal("100")

    base_start = current.start_time - timedelta(minutes=_BASE_MINUTES)
    base = [
        bar
        for bar in regular[:-1]
        if bar.start_time >= base_start and bar.end_time <= current.start_time
    ]
    if not base or base[0].start_time.astimezone(_ET).time() < _POST_BASE_MIN_START:
        return _result(
            candidate,
            state="first_pullback",
            reason="WAITING_FOR_POST_OPEN_BASE",
            regular=regular,
            features=features.model_copy(update={"opening_impulse_pct": opening_range_pct}),
            transitions=("discovered", "qualified_gap", "opening_impulse", "first_pullback"),
        )

    base_high = max(bar.high for bar in base)
    base_low = min(bar.low for bar in base)
    if base_low <= 0 or base_high <= base_low:
        return _result(
            candidate,
            state="first_pullback",
            reason="WAITING_FOR_BASE_RANGE",
            regular=regular,
            features=features.model_copy(update={"opening_impulse_pct": opening_range_pct}),
            transitions=("discovered", "qualified_gap", "opening_impulse", "first_pullback"),
        )
    base_range_pct = (base_high / base_low - Decimal("1")) * Decimal("100")
    average_volume = sum((bar.volume for bar in base), Decimal("0")) / Decimal(len(base))
    volume_ratio = current.volume / average_volume if average_volume > 0 else Decimal("0")
    current_vwap = session_vwap(regular)
    vwap_distance = (
        (current.close / current_vwap - Decimal("1")) * Decimal("100")
        if current_vwap is not None and current_vwap > 0
        else None
    )
    features = features.model_copy(
        update={
            "opening_impulse_pct": opening_range_pct,
            "pullback_depth_pct": base_range_pct,
            "session_vwap": current_vwap,
            "vwap_distance_pct": vwap_distance,
            "breakout_volume_ratio": volume_ratio,
        }
    )

    if base_range_pct >= opening_range_pct:
        return _result(
            candidate,
            state="first_pullback",
            reason="BASE_NOT_COMPRESSED_VS_OPENING_RANGE",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "opening_impulse", "first_pullback"),
        )
    if current_vwap is None or current.close <= current_vwap:
        return _result(
            candidate,
            state="vwap_reclaim",
            reason="WAITING_FOR_VWAP_ACCEPTANCE",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "opening_impulse", "first_pullback", "vwap_reclaim"),
        )
    if current.close <= base_high:
        return _result(
            candidate,
            state="lower_high_break",
            reason="WAITING_FOR_BASE_BREAKOUT",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "opening_impulse", "first_pullback", "vwap_reclaim", "lower_high_break"),
        )
    if volume_ratio <= Decimal("1"):
        return _result(
            candidate,
            state="lower_high_break",
            reason="WAITING_FOR_VOLUME_EXPANSION",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "opening_impulse", "first_pullback", "vwap_reclaim", "lower_high_break"),
        )

    stop = base_low * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
    risk = current.close - stop
    if risk <= 0:
        return _result(
            candidate,
            state="rejected",
            reason="NON_POSITIVE_RISK_DISTANCE",
            regular=regular,
            features=features,
            transitions=("discovered", "qualified_gap", "rejected"),
        )
    signal = StrategySignal(
        instrument_id=candidate.instrument_id,
        state="entry_ready",
        entry_price=current.close,
        stop_price=stop,
        target_price=current.close + risk * config.reward_multiple,
        risk_per_share=risk,
        reason_code="DELAYED_BASE_ACCEPTANCE_CONTINUATION_V3_RESEARCH",
        quality_score=0,
    )
    return _result(
        candidate,
        state="entry_ready",
        reason=signal.reason_code,
        regular=regular,
        features=features,
        transitions=("discovered", "qualified_gap", "opening_impulse", "first_pullback", "vwap_reclaim", "lower_high_break", "entry_ready"),
        signal=signal,
    )


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
        raise SystemExit(
            f"development cache must be complete: {coverage['covered_sessions']}/{coverage['requested_sessions']}; provider access is prohibited"
        )

    config = frozen_v2_config()
    with _research_evaluator(evaluate_delayed_base_acceptance):
        metrics = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)

    trade_count = int(metrics["trade_count"])
    expectancy = Decimal(str(metrics["expectancy_r"])) if metrics["expectancy_r"] is not None else None
    lcb = Decimal(str(metrics["one_sided_90_lcb_r"])) if metrics["one_sided_90_lcb_r"] is not None else None
    max_dd = Decimal(str(metrics["max_drawdown_r"]))
    development_gate = {
        "minimum_trades": 15,
        "minimum_expectancy_r": "0.20",
        "minimum_one_sided_90_lcb_r_exclusive": "0",
        "maximum_drawdown_r": "5",
    }
    eligible = (
        trade_count >= 15
        and expectancy is not None
        and expectancy >= Decimal("0.20")
        and lcb is not None
        and lcb > 0
        and max_dd <= Decimal("5")
    )

    payload = {
        "purpose": "separately_formulated_delayed_base_acceptance_v3_development_replay",
        "production_strategy_changed": False,
        "frozen_v2_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "cache_namespace": namespace,
        "cache_basis": basis,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(config),
        "hypothesis": {
            "opening_observation_end_et": "10:00",
            "post_open_base_minutes": 15,
            "base_compression": "prior 15-minute range < 09:30-10:00 opening range",
            "acceptance": "current finalized close > current regular-session VWAP",
            "breakout": "current finalized close > prior 15-minute base high",
            "volume": "current volume > prior 15-minute mean volume",
            "stop": "15 bps below prior 15-minute base low",
            "execution": "next eligible 1-minute bar; existing deterministic paper model",
            "management": "frozen V2 1.5R target / 0.75R protect / +0.25R protected stop / 60m hold",
        },
        "development_gate": development_gate,
        "development_gate_passed": eligible,
        "metrics": metrics,
        "warning": "This block was used to formulate the hypothesis, so a positive development result is not independent validation. March remains sealed unless the predeclared gate passes.",
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Delayed base acceptance V3 — development replay",
        "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']}**",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
        "",
        f"- Candidates: **{metrics['candidate_count']}**",
        f"- Triggers: **{metrics['trigger_count']}**",
        f"- Trades: **{metrics['trade_count']}** ({metrics['win_count']}W/{metrics['loss_count']}L)",
        f"- Expectancy: **{metrics['expectancy_r'] if metrics['expectancy_r'] is not None else 'N/A'}R**",
        f"- One-sided 90% LCB: **{metrics['one_sided_90_lcb_r'] if metrics['one_sided_90_lcb_r'] is not None else 'N/A'}R**",
        f"- Max drawdown: **{metrics['max_drawdown_r']}R**",
        f"- P&L: **${metrics['pnl']}**",
        "",
        "Development gate: >=15 trades, expectancy >=+0.20R, 90% LCB >0R, max DD <=5R.",
        f"Development gate passed: **{'YES' if eligible else 'NO'}**",
        "",
    ]
    if eligible:
        lines.append("The exact frozen hypothesis is eligible for a separate one-shot March holdout. No March data was read by this run.")
    else:
        lines.append("March remains sealed. Reject this hypothesis without threshold rescue.")
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
