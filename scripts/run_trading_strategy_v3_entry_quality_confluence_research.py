from __future__ import annotations

"""Replay the predeclared delayed-base entry-quality confluence hypothesis.

The Oct-Feb cache was used to formulate the quality thresholds, so this script
is deliberately an in-sample causal implementation check. It never opens March,
never calls a provider, and cannot modify production or AUTO PAPER authority.
"""

import argparse
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median

from app.trading.gapper_dataset import GapperCandidate
from app.trading.indicator_signals import multi_timeframe_indicator_context
from app.trading.models import MarketBar
from app.trading.strategies.gap_pullback import _regular_bars
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult
from app.trading.strategy_entry_quality import evaluate_entry_quality
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator
from scripts.run_trading_strategy_v3_delayed_base_acceptance_research import evaluate_delayed_base_acceptance


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay delayed-base quality confluence on cached development data.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2025-10-01")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--output-dir", default="artifacts/v3-entry-quality-confluence")
    return parser.parse_args()


def _signal_body_pct(bar: MarketBar) -> Decimal | None:
    if bar.open <= 0:
        return None
    return (bar.close / bar.open - Decimal("1")) * Decimal("100")


def _quality_evaluation(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
    tracker: Counter[str] | None = None,
) -> GapPullbackResult:
    baseline = evaluate_delayed_base_acceptance(candidate, bars, config)
    if baseline.state != "entry_ready" or baseline.signal is None:
        return baseline

    regular = list(_regular_bars(bars))
    if not regular:
        return baseline
    current = regular[-1]
    context = multi_timeframe_indicator_context(bars)
    decision = evaluate_entry_quality(
        gap_pct=candidate.gap_pct,
        base_range_pct=baseline.features.pullback_depth_pct,
        breakout_volume_ratio=baseline.features.breakout_volume_ratio,
        signal_body_pct=_signal_body_pct(current),
        vwap_extension_pct=baseline.features.vwap_distance_pct,
        five_minute=context.five_minute,
    )

    if tracker is not None:
        tracker["structural_signal_evaluations"] += 1
        tracker[f"quality_score_{decision.passed_count}_of_5"] += 1
        if decision.passed:
            tracker["quality_pass"] += 1
        else:
            tracker["quality_fail"] += 1
            for reason in decision.reasons:
                tracker[reason] += 1
            for check in decision.checks:
                if not check.passed:
                    tracker[f"CHECK_FAIL_{check.name}"] += 1

    if not decision.passed:
        reasons = decision.reasons or ("ENTRY_QUALITY_RESEARCH_REJECTED",)
        transitions = baseline.transitions[:-1] + ("rejected",)
        return baseline.model_copy(
            update={
                "state": "rejected",
                "reason_code": "+".join(reasons),
                "transitions": transitions,
                "signal": None,
            }
        )

    features = baseline.features.model_copy(update={"quality_score": decision.quality_score})
    signal = baseline.signal.model_copy(
        update={
            "reason_code": "DELAYED_BASE_QUALITY_CONFLUENCE_V3_RESEARCH",
            "quality_score": decision.quality_score,
        }
    )
    return baseline.model_copy(
        update={
            "reason_code": signal.reason_code,
            "features": features,
            "signal": signal,
        }
    )


def evaluate_delayed_base_quality_confluence(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
) -> GapPullbackResult:
    return _quality_evaluation(candidate, bars, config)


def _decimal(value: object | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _win_rate(metrics: dict[str, object]) -> Decimal | None:
    trades = int(metrics["trade_count"])
    if trades <= 0:
        return None
    return Decimal(int(metrics["win_count"])) / Decimal(trades)


def _trade_distribution(metrics: dict[str, object]) -> dict[str, object]:
    trades = list(metrics.get("trades", []))
    exit_mix = Counter(str(row["exit_reason"]) for row in trades)
    mfe = [Decimal(str(row["mfe_r"])) for row in trades]
    mae = [Decimal(str(row["mae_r"])) for row in trades]
    return {
        "exit_mix": dict(sorted(exit_mix.items())),
        "mean_mfe_r": str(sum(mfe, Decimal("0")) / Decimal(len(mfe))) if mfe else None,
        "median_mfe_r": str(median(mfe)) if mfe else None,
        "mean_mae_r": str(sum(mae, Decimal("0")) / Decimal(len(mae))) if mae else None,
        "median_mae_r": str(median(mae)) if mae else None,
    }


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
        baseline = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)

    tracker: Counter[str] = Counter()

    def tracked_evaluator(candidate, bars, evaluator_config):
        return _quality_evaluation(candidate, bars, evaluator_config, tracker)

    with _research_evaluator(tracked_evaluator):
        quality = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)

    baseline_rate = _win_rate(baseline)
    quality_rate = _win_rate(quality)
    baseline_expectancy = _decimal(baseline.get("expectancy_r"))
    quality_expectancy = _decimal(quality.get("expectancy_r"))
    baseline_dd = _decimal(baseline.get("max_drawdown_r"))
    quality_dd = _decimal(quality.get("max_drawdown_r"))

    delta = {
        "trade_count": int(quality["trade_count"]) - int(baseline["trade_count"]),
        "win_rate_percentage_points": (
            str((quality_rate - baseline_rate) * Decimal("100"))
            if quality_rate is not None and baseline_rate is not None
            else None
        ),
        "expectancy_r": (
            str(quality_expectancy - baseline_expectancy)
            if quality_expectancy is not None and baseline_expectancy is not None
            else None
        ),
        "max_drawdown_r": (
            str(quality_dd - baseline_dd)
            if quality_dd is not None and baseline_dd is not None
            else None
        ),
        "pnl": str(Decimal(str(quality["pnl"])) - Decimal(str(baseline["pnl"]))),
    }

    payload = {
        "purpose": "in_sample_causal_check_of_predeclared_delayed_base_entry_quality_confluence",
        "production_strategy_changed": False,
        "frozen_v2_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "cache_namespace": namespace,
        "cache_basis": basis,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(config),
        "policy": {
            "structural_prerequisite": "rejected delayed-base acceptance evaluator",
            "quality_checks": [
                "gap_pct >= 30",
                "base_range_pct <= 8",
                "breakout_volume_ratio >= 2",
                "signal_body_pct <= 3",
                "vwap_extension_pct <= 5",
            ],
            "minimum_quality_checks": 4,
            "five_minute_trend": "finalized close > EMA9 and EMA9 rising; EMA9 must be warmed",
            "management": "unchanged frozen V2 1.5R target / 0.75R protect / +0.25R protected stop / 60m hold",
        },
        "baseline": {**baseline, **_trade_distribution(baseline), "win_rate": str(baseline_rate) if baseline_rate is not None else None},
        "quality_confluence": {**quality, **_trade_distribution(quality), "win_rate": str(quality_rate) if quality_rate is not None else None},
        "delta_quality_minus_baseline": delta,
        "quality_signal_diagnostics": dict(sorted(tracker.items())),
        "interpretation": "The thresholds were formulated from this same development cohort. This replay is in-sample hypothesis checking only and cannot validate or promote the policy. March remains sealed regardless of outcome.",
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def pct(rate: Decimal | None) -> str:
        return f"{float(rate * Decimal('100')):.2f}%" if rate is not None else "N/A"

    lines = [
        "# Delayed-base entry quality confluence — in-sample causal replay",
        "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']}**",
        "- Provider calls: **none**",
        "- March loaded: **no**",
        "- Frozen V2 / production authority changed: **no**",
        "",
        "## Baseline delayed-base",
        f"- Trades: **{baseline['trade_count']}** ({baseline['win_count']}W/{baseline['loss_count']}L)",
        f"- Win rate: **{pct(baseline_rate)}**",
        f"- Expectancy: **{baseline['expectancy_r']}R**",
        f"- One-sided 90% LCB: **{baseline['one_sided_90_lcb_r']}R**",
        f"- Max drawdown: **{baseline['max_drawdown_r']}R**",
        f"- P&L: **${baseline['pnl']}**",
        "",
        "## Policy D — 4-of-5 quality + finalized 5m EMA9 trend",
        f"- Trades: **{quality['trade_count']}** ({quality['win_count']}W/{quality['loss_count']}L)",
        f"- Win rate: **{pct(quality_rate)}**",
        f"- Expectancy: **{quality['expectancy_r']}R**",
        f"- One-sided 90% LCB: **{quality['one_sided_90_lcb_r']}R**",
        f"- Max drawdown: **{quality['max_drawdown_r']}R**",
        f"- P&L: **${quality['pnl']}**",
        "",
        "## Delta (Policy D - baseline)",
        f"- Trades: **{delta['trade_count']:+d}**",
        f"- Win rate: **{delta['win_rate_percentage_points']} percentage points**",
        f"- Expectancy: **{delta['expectancy_r']}R/trade**",
        f"- Max drawdown: **{delta['max_drawdown_r']}R**",
        f"- P&L: **${delta['pnl']}**",
        "",
        "This is an in-sample implementation check because the quality thresholds were derived from the same Oct-Feb cohort. It is not independent validation; March remains sealed regardless of the result.",
    ]
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["evaluate_delayed_base_quality_confluence"]
