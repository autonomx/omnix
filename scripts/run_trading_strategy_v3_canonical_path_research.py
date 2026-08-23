from __future__ import annotations

"""Research-only canonical-path successor experiment using immutable cached data.

This does NOT add a production strategy version and does NOT change frozen V2.
It replaces only the backtest evaluator inside this process so the mature paper
fill/risk/management engine can be reused. March is never loaded here.

Hypothesis frozen before holdout inspection:
- enumerate every causal L1 -> B1 -> higher-L2 path that can break on the current bar;
- keep V2's ordinary hard gates and geometry unless a named single-axis variant says otherwise;
- choose the freshest L2; tie-break by stronger B1 recovery, then deeper second pullback;
- require >=5 development trades, positive expectancy and one-sided 90% LCB > 0
  before any selector is eligible for a separate March validation run.
"""

import argparse
import json
import math
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

import app.trading.strategy_backtest as strategy_backtest
from app.trading.gapper_dataset import GapperCandidate
from app.trading.models import MarketBar
from app.trading.strategies.failed_selloff_v2 import evaluate_gap_pullback_v2
from app.trading.strategies.gap_pullback import _ET, _regular_bars, session_vwap
from app.trading.strategies.models import (
    GapPullbackConfig,
    GapPullbackFeatures,
    GapPullbackResult,
    StrategySignal,
)
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research canonical V3 paths from cached development data only.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2026-01-02")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--minimum-development-trades", type=int, default=5)
    parser.add_argument("--minimum-coverage-ratio", default="0.80")
    parser.add_argument("--minimum-covered-sessions", type=int, default=20)
    parser.add_argument("--output-dir", default="artifacts/v3-canonical-path-research")
    return parser.parse_args()


def _quality(features: GapPullbackFeatures) -> int:
    return (
        features.catalyst_score
        + features.supply_score
        + features.opening_structure_score
        + features.pullback_quality_score
        + features.reclaim_break_score
    )


def _result(
    candidate: GapperCandidate,
    state: str,
    reason: str,
    transitions: list[str],
    features: GapPullbackFeatures,
    regular: list[MarketBar],
    signal: StrategySignal | None = None,
) -> GapPullbackResult:
    scored = features.model_copy(update={"quality_score": _quality(features)})
    return GapPullbackResult(
        instrument_id=candidate.instrument_id,
        state=state,
        reason_code=reason,
        features=scored,
        transitions=tuple(transitions),
        signal=signal,
        evaluated_bar_count=len(regular),
    )


def _local_low(regular: list[MarketBar], index: int) -> bool:
    if index < 0 or index + 1 >= len(regular):
        return False
    left = regular[index - 1].low if index > 0 else regular[index].low
    return regular[index].low <= left and regular[index].low < regular[index + 1].low


def _local_high(regular: list[MarketBar], index: int) -> bool:
    if index <= 0 or index + 1 >= len(regular):
        return False
    return regular[index].high >= regular[index - 1].high and regular[index].high > regular[index + 1].high


def _volume_ratio(regular: list[MarketBar], index: int, lookback: int) -> Decimal | None:
    prior = regular[max(0, index - lookback) : index]
    if not prior:
        return None
    average = sum((bar.volume for bar in prior), Decimal("0")) / Decimal(len(prior))
    if average <= 0:
        return None
    return regular[index].volume / average


def _base_features(candidate: GapperCandidate, config: GapPullbackConfig) -> tuple[GapPullbackFeatures, str | None]:
    severe = tuple(flag for flag in candidate.dilution_flags if flag in set(config.reject_dilution_flags))
    float_ok = (
        candidate.float_shares is not None
        and config.preferred_float_min_shares <= candidate.float_shares <= config.preferred_float_max_shares
    )
    features = GapPullbackFeatures(
        gap_pct=candidate.gap_pct,
        spread_bps=candidate.spread_bps,
        tod_rvol=candidate.tod_rvol,
        float_shares=candidate.float_shares,
        catalyst_evidence_count=len(candidate.catalyst_evidence_ids),
        dilution_flags=tuple(candidate.dilution_flags),
        catalyst_score=2 if candidate.catalyst_evidence_ids else 0,
        supply_score=0 if severe else (2 if float_ok else 1),
        opening_structure_score=2 if candidate.gap_pct >= Decimal("40") else 1,
    )
    rejection = None
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
    elif config.require_catalyst_evidence and not candidate.catalyst_evidence_ids:
        rejection = "CATALYST_EVIDENCE_REQUIRED"
    elif severe:
        rejection = "DILUTION_SUPPLY_RISK"
    elif config.float_preference_mode == "require" and not float_ok:
        rejection = "FLOAT_OUTSIDE_REQUIRED_RANGE"
    return features, rejection


def evaluate_canonical_failed_selloff(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
) -> GapPullbackResult:
    """Causal research evaluator whose path choice is independent of first-match ownership."""

    regular = _regular_bars(list(bars))
    transitions = ["discovered"]
    features, rejection = _base_features(candidate, config)
    if rejection is not None:
        return _result(candidate, "rejected", rejection, transitions + ["rejected"], features, regular)

    transitions.append("qualified_gap")
    if not regular:
        return _result(candidate, "qualified_gap", "WAITING_FOR_REGULAR_SESSION", transitions, features, regular)

    current_et = regular[-1].end_time.astimezone(_ET)
    minutes_since_open = max(0, current_et.hour * 60 + current_et.minute - (9 * 60 + 30))
    features = features.model_copy(update={"minutes_since_open": minutes_since_open})
    if current_et.time() < config.entry_start_et:
        return _result(candidate, "qualified_gap", "ENTRY_WINDOW_NOT_OPEN", transitions, features, regular)
    if current_et.time() > config.last_entry_et:
        return _result(candidate, "expired", "ENTRY_WINDOW_CLOSED", transitions + ["expired"], features, regular)

    current_index = len(regular) - 1
    current = regular[current_index]
    prefix_vwap = session_vwap(regular)
    if prefix_vwap is None or current.close <= prefix_vwap or current.close <= current.open:
        return _result(candidate, "qualified_gap", "WAITING_FOR_CANONICAL_BREAKOUT", transitions, features, regular)
    breakout_ratio = _volume_ratio(regular, current_index, config.volume_lookback_bars)
    if breakout_ratio is None or breakout_ratio < config.v2_minimum_breakout_volume_ratio:
        return _result(candidate, "qualified_gap", "WAITING_FOR_CANONICAL_BREAKOUT_VOLUME", transitions, features, regular)

    reference = max(candidate.premarket_price, regular[0].open)
    opportunities: list[tuple[int, Decimal, Decimal, int, int, int]] = []
    # tuple: l2_idx, recovery_pct, second_pullback_pct, l1_idx, b1_idx, l2_to_signal

    for l1_idx in range(0, len(regular) - 1):
        if not _local_low(regular, l1_idx):
            continue
        l1 = regular[l1_idx].low
        depth = (reference - l1) / reference * Decimal("100")
        if not config.pullback_min_pct <= depth <= config.pullback_max_pct:
            continue

        required_l2 = l1 * (Decimal("1") + config.higher_low_buffer_bps / Decimal("10000"))
        for b1_idx in range(l1_idx + 1, len(regular) - 1):
            if not _local_high(regular, b1_idx):
                continue
            if b1_idx - l1_idx < config.v2_minimum_l1_to_b1_minutes:
                continue
            b1 = regular[b1_idx].high
            recovery = (b1 / l1 - Decimal("1")) * Decimal("100")
            if recovery < config.v2_recovery_min_pct or current.close <= b1:
                continue

            invalidated = False
            for l2_idx in range(b1_idx + 1, current_index - 1):
                if not _local_low(regular, l2_idx):
                    continue
                l2 = regular[l2_idx].low
                if l2 <= l1:
                    invalidated = True
                    break
                if invalidated or l2 < required_l2:
                    continue
                second_pullback = (b1 - l2) / b1 * Decimal("100")
                if second_pullback < config.v2_second_pullback_min_pct:
                    continue
                l2_to_signal = current_index - l2_idx
                if l2_to_signal < 2 or l2_to_signal > config.v2_maximum_l2_to_signal_minutes:
                    continue
                opportunities.append((l2_idx, recovery, second_pullback, l1_idx, b1_idx, l2_to_signal))

    if not opportunities:
        return _result(candidate, "qualified_gap", "WAITING_FOR_CANONICAL_PATTERN", transitions, features, regular)

    # Frozen research selector: freshest L2 first, then stronger B1 recovery,
    # then deeper second pullback. Final indexes make ties deterministic.
    l2_idx, recovery, second_pullback, l1_idx, b1_idx, l2_to_signal = max(
        opportunities,
        key=lambda row: (row[0], row[1], row[2], -row[3], -row[4]),
    )
    l1 = regular[l1_idx].low
    b1 = regular[b1_idx].high
    l2 = regular[l2_idx].low
    pullback_depth = (reference - l1) / reference * Decimal("100")
    features = features.model_copy(
        update={
            "l1": l1,
            "b1": b1,
            "l2": l2,
            "pullback_depth_pct": pullback_depth,
            "l1_to_b1_minutes": b1_idx - l1_idx,
            "second_pullback_depth_pct": second_pullback,
            "l2_to_signal_minutes": l2_to_signal,
            "pullback_quality_score": 2,
            "session_vwap": prefix_vwap,
            "vwap_distance_pct": (current.close / prefix_vwap - Decimal("1")) * Decimal("100"),
            "breakout_volume_ratio": breakout_ratio,
            "reclaim_break_score": 2,
        }
    )
    transitions.extend(
        [
            "first_pullback",
            "first_low_confirmed",
            "bounce_high_confirmed",
            "second_pullback",
            "higher_low_confirmed",
            "vwap_reclaim",
            "lower_high_break",
        ]
    )

    stop = l2 * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
    risk = current.close - stop
    if risk <= 0:
        return _result(candidate, "rejected", "NON_POSITIVE_RISK_DISTANCE", transitions + ["rejected"], features, regular)
    signal = StrategySignal(
        instrument_id=candidate.instrument_id,
        state="entry_ready",
        entry_price=current.close,
        stop_price=stop,
        target_price=current.close + risk * config.reward_multiple,
        risk_per_share=risk,
        reason_code="FAILED_SELLOFF_CANONICAL_PATH_RESEARCH",
        quality_score=_quality(features),
    )
    transitions.append("entry_ready")
    return _result(candidate, "entry_ready", signal.reason_code, transitions, features, regular, signal)


@contextmanager
def _research_evaluator(evaluator: Callable):
    original = strategy_backtest.evaluate_gap_pullback
    strategy_backtest.evaluate_gap_pullback = evaluator
    try:
        yield
    finally:
        strategy_backtest.evaluate_gap_pullback = original


def _lcb90(metrics: dict[str, object]) -> Decimal | None:
    raw = metrics.get("one_sided_90_lcb_r")
    return Decimal(str(raw)) if raw is not None else None


def _variant_family() -> list[tuple[str, dict[str, object]]]:
    return [
        ("canonical_v2_floors", {}),
        ("canonical_recovery10", {"v2_recovery_min_pct": Decimal("10")}),
        ("canonical_base2", {"v2_minimum_l1_to_b1_minutes": 2}),
        ("canonical_resolution16", {"v2_maximum_l2_to_signal_minutes": 16}),
        ("canonical_l1_depth10", {"pullback_min_pct": Decimal("10")}),
    ]


def main() -> int:
    args = _args()
    start = date.fromisoformat(args.development_start)
    end = date.fromisoformat(args.development_end)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)

    basis_strategy = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(basis_strategy, spread)
    cache = Path(args.dataset_cache_dir) / namespace
    datasets, coverage = _load_block(cache, start, end)
    requested = int(coverage["requested_sessions"])
    covered = int(coverage["covered_sessions"])
    required = max(
        args.minimum_covered_sessions,
        math.ceil(requested * float(Decimal(args.minimum_coverage_ratio))),
    )
    if covered < required:
        raise SystemExit(f"cache coverage {covered}/{requested} below required {required}; provider access is prohibited")

    frozen = frozen_v2_config()
    baseline = _run_variant(datasets, frozen, initial_cash=initial_cash, spread=spread)
    rows: list[dict[str, object]] = [
        {
            "variant_id": "frozen_v2_reference",
            "selector": "production_v2_earliest_path",
            "updates": {},
            **baseline,
        }
    ]
    with _research_evaluator(evaluate_canonical_failed_selloff):
        for variant_id, updates in _variant_family():
            config = frozen.model_copy(update=updates)
            metrics = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
            rows.append(
                {
                    "variant_id": variant_id,
                    "selector": "canonical_freshest_l2_then_recovery_then_second_pullback",
                    "updates": {key: str(value) for key, value in updates.items()},
                    **metrics,
                }
            )

    eligible: list[str] = []
    for row in rows:
        if row["variant_id"] == "frozen_v2_reference":
            continue
        expectancy = Decimal(str(row["expectancy_r"])) if row["expectancy_r"] is not None else Decimal("-Infinity")
        lcb = _lcb90(row)
        if (
            int(row["trade_count"]) >= args.minimum_development_trades
            and expectancy > 0
            and lcb is not None
            and lcb > 0
        ):
            eligible.append(str(row["variant_id"]))

    output = {
        "purpose": "research-only post-V2 canonical path selection",
        "production_strategy_changed": False,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "development_period": [start.isoformat(), end.isoformat()],
        "cache_namespace": namespace,
        "cache_basis": basis,
        "coverage": coverage,
        "holdout_loaded": False,
        "selector_rule": [
            "enumerate all causal paths that can break on the current finalized bar",
            "filter by variant geometry",
            "choose freshest L2",
            "tie-break stronger B1 recovery",
            "tie-break deeper second pullback",
        ],
        "holdout_gate": {
            "minimum_development_trades": args.minimum_development_trades,
            "expectancy_r": "> 0",
            "one_sided_90_lcb_r": "> 0",
        },
        "holdout_eligible_variants": eligible,
        "variants": rows,
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Post-V2 canonical path research — development only",
        "",
        f"- Period: {start} through {end}",
        f"- Coverage: {covered}/{requested} sessions",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
        "- Holdout gate: >=5 development trades, expectancy >0R, one-sided 90% LCB >0R.",
        "",
        "| Variant | Trades | Triggers | W-L | Expectancy R | 90% LCB R | P&L |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['variant_id']} | {row['trade_count']} | {row['trigger_count']} | "
            f"{row['win_count']}-{row['loss_count']} | {row['expectancy_r'] or 'N/A'} | "
            f"{row['one_sided_90_lcb_r'] or 'N/A'} | {row['pnl']} |"
        )
    lines.extend(["", f"Holdout-eligible variants: **{', '.join(eligible) if eligible else 'none'}**", ""])
    if not eligible:
        lines.append("March remains sealed; development evidence is insufficient for holdout exposure.")
    else:
        lines.append("Eligible IDs may be evaluated later by a separate, explicit one-shot holdout workflow.")
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
