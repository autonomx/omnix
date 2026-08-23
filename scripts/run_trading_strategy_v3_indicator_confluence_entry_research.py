from __future__ import annotations

"""Cache-only entry-selection experiment using causal multi-timeframe indicators.

The frozen V2 structural evaluator remains the source of candidate entry signals.
This research wrapper can only reject a V2 signal when the predeclared indicator
confluence is not present.  It cannot create a signal, change V2, call a provider,
or load March.
"""

import argparse
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.trading.gapper_dataset import GapperCandidate
from app.trading.indicator_signals import (
    indicator_entry_confirmation,
    multi_timeframe_indicator_context,
)
from app.trading.models import MarketBar
from app.trading.strategies.failed_selloff_v2 import evaluate_gap_pullback_v2
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator


_STATS: Counter[str] = Counter()


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay indicator-confirmed V2 entries on cached development data only.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--development-start", default="2025-10-01")
    p.add_argument("--development-end", default="2026-02-27")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--output-dir", default="artifacts/v3-indicator-confluence-entry")
    return p.parse_args()


def evaluate_indicator_confirmed_v2(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig,
) -> GapPullbackResult:
    structural = evaluate_gap_pullback_v2(candidate, bars, config)
    if structural.state != "entry_ready" or structural.signal is None:
        return structural

    _STATS["structural_signals"] += 1
    context = multi_timeframe_indicator_context(bars)
    one = context.one_minute
    five = context.five_minute
    if one.macd is not None:
        _STATS["one_minute_macd_available"] += 1
    if one.stochastic_rsi_k is not None and one.stochastic_rsi_d is not None:
        _STATS["one_minute_stoch_rsi_available"] += 1
    if five.ema9 is not None:
        _STATS["five_minute_ema9_available"] += 1
    if five.ema20 is not None:
        _STATS["five_minute_ema20_available"] += 1
    if five.macd is not None and five.macd_signal is not None:
        _STATS["five_minute_macd_available"] += 1
    if five.stochastic_rsi_k is not None and five.stochastic_rsi_d is not None:
        _STATS["five_minute_stoch_rsi_available"] += 1

    allowed, reasons = indicator_entry_confirmation(context)
    if not allowed:
        _STATS["indicator_rejected_signals"] += 1
        for reason in reasons:
            _STATS[f"rejection:{reason}"] += 1
        return structural.model_copy(
            update={
                "state": "lower_high_break",
                "reason_code": "V3_INDICATOR_CONFLUENCE_NOT_CONFIRMED",
                "signal": None,
            }
        )

    _STATS["indicator_confirmed_signals"] += 1
    signal = structural.signal.model_copy(
        update={"reason_code": "V3_INDICATOR_CONFLUENCE_CONFIRMED"}
    )
    return structural.model_copy(
        update={
            "reason_code": signal.reason_code,
            "signal": signal,
        }
    )


def _decimal_metric(row: dict[str, object], key: str) -> Decimal | None:
    value = row.get(key)
    return Decimal(str(value)) if value is not None else None


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
    baseline = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
    _STATS.clear()
    with _research_evaluator(evaluate_indicator_confirmed_v2):
        confirmed = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)

    trade_count = int(confirmed["trade_count"])
    expectancy = _decimal_metric(confirmed, "expectancy_r")
    baseline_expectancy = _decimal_metric(baseline, "expectancy_r")
    lcb = _decimal_metric(confirmed, "one_sided_90_lcb_r")
    max_dd = Decimal(str(confirmed["max_drawdown_r"]))

    if trade_count < 10:
        status = "inconclusive_low_trade_count"
        eligible = False
    else:
        eligible = (
            expectancy is not None
            and expectancy >= Decimal("0.20")
            and lcb is not None
            and lcb > 0
            and max_dd <= Decimal("5")
            and baseline_expectancy is not None
            and expectancy > baseline_expectancy
        )
        status = "eligible_for_holdout" if eligible else "rejected"

    structural_signals = _STATS["structural_signals"]
    coverage_stats = {
        "structural_signals": structural_signals,
        "indicator_confirmed_signals": _STATS["indicator_confirmed_signals"],
        "indicator_rejected_signals": _STATS["indicator_rejected_signals"],
        "one_minute_macd_available": _STATS["one_minute_macd_available"],
        "one_minute_stoch_rsi_available": _STATS["one_minute_stoch_rsi_available"],
        "five_minute_ema9_available": _STATS["five_minute_ema9_available"],
        "five_minute_ema20_available": _STATS["five_minute_ema20_available"],
        "five_minute_macd_available": _STATS["five_minute_macd_available"],
        "five_minute_stoch_rsi_available": _STATS["five_minute_stoch_rsi_available"],
    }
    rejection_reasons = {
        key.removeprefix("rejection:"): count
        for key, count in sorted(_STATS.items())
        if key.startswith("rejection:")
    }

    payload = {
        "purpose": "indicator_confluence_entry_selection_development_only",
        "production_strategy_changed": False,
        "frozen_v2_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "cache_namespace": namespace,
        "cache_basis": basis,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(config),
        "entry_hypothesis": {
            "structural_signal": "exact frozen V2 entry_ready",
            "one_minute": "price>EMA9>EMA20; EMA9 rising; MACD>signal with histogram>=0; Stoch RSI K>=D",
            "five_minute_required": "EMA9 available, price>EMA9, EMA9 rising",
            "five_minute_veto_when_available": "EMA9<=EMA20 or MACD<=signal or Stoch RSI K<D",
            "indicator_periods": "EMA 9/20; MACD 12/26/9; Stoch RSI 14/14/3/3",
            "overbought_rule": "Stoch RSI >80 alone is not bearish and is not an entry veto",
            "exit_policy": "unchanged frozen V2 management for isolation",
        },
        "development_gate": {
            "minimum_trades": 10,
            "minimum_expectancy_r": "0.20",
            "minimum_one_sided_90_lcb_r_exclusive": "0",
            "maximum_drawdown_r": "5",
            "must_beat_same_block_frozen_v2_expectancy": True,
        },
        "status": status,
        "development_gate_passed": eligible,
        "indicator_coverage": coverage_stats,
        "indicator_rejection_reasons": rejection_reasons,
        "baseline_frozen_v2": baseline,
        "indicator_confirmed": confirmed,
        "warning": "Historical cache has incomplete 5m oscillator warm-up before the morning entry cutoff. Missing higher-timeframe values are explicit and neutral; this is not full multi-timeframe validation.",
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V3 indicator-confluence entry confirmation — development only",
        "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']}**",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
        "",
        "| Entry policy | Trades | W-L | Expectancy R | 90% LCB R | Max DD R | P&L |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| frozen V2 structural baseline | {baseline['trade_count']} | {baseline['win_count']}-{baseline['loss_count']} | {baseline['expectancy_r'] or 'N/A'} | {baseline['one_sided_90_lcb_r'] or 'N/A'} | {baseline['max_drawdown_r']} | ${baseline['pnl']} |",
        f"| indicator-confirmed V2 signals | {confirmed['trade_count']} | {confirmed['win_count']}-{confirmed['loss_count']} | {confirmed['expectancy_r'] or 'N/A'} | {confirmed['one_sided_90_lcb_r'] or 'N/A'} | {confirmed['max_drawdown_r']} | ${confirmed['pnl']} |",
        "",
        "## Causal indicator coverage at structural signal time",
        "",
        f"- Structural signals inspected: **{structural_signals}**",
        f"- Indicator-confirmed: **{_STATS['indicator_confirmed_signals']}**",
        f"- Indicator-rejected: **{_STATS['indicator_rejected_signals']}**",
        f"- 1m MACD available: **{_STATS['one_minute_macd_available']}/{structural_signals}**",
        f"- 1m Stoch RSI available: **{_STATS['one_minute_stoch_rsi_available']}/{structural_signals}**",
        f"- 5m EMA9 available: **{_STATS['five_minute_ema9_available']}/{structural_signals}**",
        f"- 5m EMA20 available: **{_STATS['five_minute_ema20_available']}/{structural_signals}**",
        f"- 5m MACD available: **{_STATS['five_minute_macd_available']}/{structural_signals}**",
        f"- 5m Stoch RSI available: **{_STATS['five_minute_stoch_rsi_available']}/{structural_signals}**",
        "",
        f"Development status: **{status}**",
        "Gate: >=10 trades, expectancy >=+0.20R, one-sided 90% LCB >0R, max DD <=5R, and expectancy above frozen V2 baseline.",
        "",
    ]
    if rejection_reasons:
        lines.extend(["Top indicator rejection reasons:", ""])
        for reason, count in sorted(rejection_reasons.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {reason}: {count}")
        lines.append("")
    if eligible:
        lines.append("The exact frozen entry overlay is eligible for a separate one-shot March holdout. This run did not read March.")
    elif status == "inconclusive_low_trade_count":
        lines.append("March remains sealed because the confirmed sample is too small; do not loosen the indicator rule on this block.")
    else:
        lines.append("March remains sealed. Reject this exact entry overlay without indicator-period or threshold rescue.")
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
