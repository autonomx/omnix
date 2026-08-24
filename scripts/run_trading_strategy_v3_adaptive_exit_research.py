from __future__ import annotations

"""Paired A/B development replay for frozen entries with adaptive exits.

A = current frozen V2 management.
B = exact same entries/fills/sizes, but no fixed target/time exit; retain the
structural/protected stop and exit on causal indicator deterioration or 15:55 ET.

The entry cohort is the already-declared delayed-base development cohort because
it supplies enough fixed trades for an exit-only paired comparison. This does
not revive or promote that rejected entry hypothesis.
"""

import argparse
import csv
import json
import math
from collections import Counter
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from app.trading.paper import PaperExecutionPolicy
from app.trading.strategies.models import StrategyRiskProfile
from app.trading.strategy_adaptive_exit_research import replay_adaptive_indicator_exit
from app.trading.strategy_backtest import GapPullbackBacktestTrade, run_gap_pullback_backtest
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator
from scripts.run_trading_strategy_v3_delayed_base_acceptance_research import evaluate_delayed_base_acceptance


_ET = ZoneInfo("America/New_York")
_FORCE_FLAT_ET = time(15, 55)
_Z90 = Decimal("1.2815515655446004")


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare frozen V2 exits with a causal adaptive indicator exit on identical entries.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--development-start", default="2025-10-01")
    p.add_argument("--development-end", default="2026-02-27")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--output-dir", default="artifacts/v3-adaptive-exit-research")
    return p.parse_args()


def _lcb90(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values) - 1)
    stdev = Decimal(str(math.sqrt(float(variance))))
    stderr = stdev / Decimal(str(math.sqrt(len(values))))
    return mean - _Z90 * stderr


def _max_drawdown_r(values: list[Decimal]) -> Decimal:
    equity = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _profit_factor(values: list[Decimal]) -> Decimal | None:
    gains = sum((value for value in values if value > 0), Decimal("0"))
    losses = -sum((value for value in values if value < 0), Decimal("0"))
    return gains / losses if losses > 0 else None


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _metrics(
    values: list[Decimal],
    *,
    pnl: Decimal,
    initial_cash: Decimal,
    hold_minutes: list[Decimal],
    capture: list[Decimal],
    exit_reasons: Counter[str],
) -> dict[str, object]:
    winners = [value for value in values if value > 0]
    losers = [value for value in values if value < 0]
    expectancy = _mean(values)
    profit_factor = _profit_factor(values)
    return {
        "trade_count": len(values),
        "win_count": len(winners),
        "loss_count": len(losers),
        "win_rate": str(Decimal(len(winners)) / Decimal(len(values))) if values else None,
        "expectancy_r": str(expectancy) if expectancy is not None else None,
        "one_sided_90_lcb_r": str(_lcb90(values)) if len(values) >= 2 else None,
        "median_r": str(Decimal(str(median(values)))) if values else None,
        "average_winner_r": str(_mean(winners)) if winners else None,
        "average_loser_r": str(_mean(losers)) if losers else None,
        "profit_factor_r": str(profit_factor) if profit_factor is not None else None,
        "max_drawdown_r": str(_max_drawdown_r(values)),
        "average_hold_minutes": str(_mean(hold_minutes)) if hold_minutes else None,
        "average_full_session_mfe_capture_pct": str(_mean(capture) * Decimal("100")) if capture else None,
        "pnl": str(pnl),
        "return_pct": str(pnl / initial_cash * Decimal("100")),
        "exit_reasons": dict(sorted(exit_reasons.items())),
    }


def _full_session_mfe_r(trade: GapPullbackBacktestTrade, bars) -> Decimal:
    risk = trade.entry_price - trade.stop_price
    if risk <= 0:
        return Decimal("0")
    highs = [trade.entry_price]
    entry_session = trade.entry_time.astimezone(_ET).date()
    for bar in bars:
        bar_et = bar.start_time.astimezone(_ET)
        if bar.start_time < trade.entry_time:
            continue
        if bar_et.date() != entry_session:
            continue
        if bar_et.time() >= _FORCE_FLAT_ET:
            break
        highs.append(bar.high)
    return (max(highs) - trade.entry_price) / risk


def _capture_ratio(realized_r: Decimal, full_session_mfe_r: Decimal) -> Decimal | None:
    if full_session_mfe_r <= 0:
        return None
    return max(Decimal("0"), realized_r) / full_session_mfe_r


def main() -> int:
    args = _args()
    start = date.fromisoformat(args.development_start)
    end = date.fromisoformat(args.development_end)
    initial_cash = Decimal(args.initial_cash)
    spread = Decimal(args.assumed_spread_bps)

    cache_basis = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(cache_basis, spread)
    datasets, coverage = _load_block(Path(args.dataset_cache_dir) / namespace, start, end)
    if int(coverage["covered_sessions"]) != int(coverage["requested_sessions"]):
        raise SystemExit(
            f"development cache must be complete: {coverage['covered_sessions']}/{coverage['requested_sessions']}; provider access is prohibited"
        )

    config = frozen_v2_config()
    risk = StrategyRiskProfile()
    policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    baseline_cash = initial_cash
    paired_rows: list[dict[str, object]] = []

    with _research_evaluator(evaluate_delayed_base_acceptance):
        for dataset in datasets:
            result = run_gap_pullback_backtest(
                dataset,
                config,
                policy,
                assumed_spread_bps=spread,
                max_hold_minutes=config.v2_max_hold_minutes,
                max_concurrent_positions=risk.max_positions,
                risk_profile=risk,
                initial_cash=baseline_cash,
            )
            baseline_cash += sum(
                (trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades),
                Decimal("0"),
            )
            candidates = {candidate.instrument_id: candidate for candidate in dataset.universe.candidates}
            for trade in result.trades:
                candidate = candidates[trade.instrument_id]
                adaptive = replay_adaptive_indicator_exit(
                    candidate=candidate,
                    bars=dataset.bars_by_instrument[trade.instrument_id],
                    baseline_trade=trade,
                    config=config,
                    policy=policy,
                    assumed_spread_bps=spread,
                )
                full_mfe = _full_session_mfe_r(trade, dataset.bars_by_instrument[trade.instrument_id])
                baseline_capture = _capture_ratio(trade.r_multiple, full_mfe)
                adaptive_capture = _capture_ratio(adaptive.r_multiple, full_mfe)
                paired_rows.append({
                    "session_date": dataset.session_date.isoformat(),
                    "instrument_id": trade.instrument_id,
                    "entry_time": trade.entry_time.isoformat(),
                    "entry_price": trade.entry_price,
                    "stop_price": trade.stop_price,
                    "quantity": trade.entry_fill_quantity,
                    "full_session_mfe_r": full_mfe,
                    "a_exit_time": trade.exit_time.isoformat(),
                    "a_exit_reason": trade.exit_reason,
                    "a_exit_price": trade.exit_price,
                    "a_r": trade.r_multiple,
                    "a_hold_minutes": trade.hold_minutes,
                    "a_capture": baseline_capture,
                    "b_exit_time": adaptive.exit_time.isoformat(),
                    "b_exit_reason": adaptive.exit_reason,
                    "b_exit_price": adaptive.exit_price,
                    "b_r": adaptive.r_multiple,
                    "b_hold_minutes": adaptive.hold_minutes,
                    "b_capture": adaptive_capture,
                    "b_indicator_reasons": adaptive.indicator_reason_codes,
                    "paired_delta_r": adaptive.r_multiple - trade.r_multiple,
                    "a_pnl": trade.pnl_per_share * trade.entry_fill_quantity,
                    "b_pnl": adaptive.pnl_per_share * adaptive.entry_fill_quantity,
                })

    paired_rows.sort(key=lambda row: (str(row["entry_time"]), str(row["instrument_id"])))
    a_values = [Decimal(str(row["a_r"])) for row in paired_rows]
    b_values = [Decimal(str(row["b_r"])) for row in paired_rows]
    deltas = [Decimal(str(row["paired_delta_r"])) for row in paired_rows]
    a_pnl = sum((Decimal(str(row["a_pnl"])) for row in paired_rows), Decimal("0"))
    b_pnl = sum((Decimal(str(row["b_pnl"])) for row in paired_rows), Decimal("0"))
    a_holds = [Decimal(str(row["a_hold_minutes"])) for row in paired_rows]
    b_holds = [Decimal(str(row["b_hold_minutes"])) for row in paired_rows]
    a_capture = [Decimal(str(row["a_capture"])) for row in paired_rows if row["a_capture"] is not None]
    b_capture = [Decimal(str(row["b_capture"])) for row in paired_rows if row["b_capture"] is not None]
    a_reasons = Counter(str(row["a_exit_reason"]) for row in paired_rows)
    b_reasons = Counter(str(row["b_exit_reason"]) for row in paired_rows)

    a_metrics = _metrics(
        a_values,
        pnl=a_pnl,
        initial_cash=initial_cash,
        hold_minutes=a_holds,
        capture=a_capture,
        exit_reasons=a_reasons,
    )
    b_metrics = _metrics(
        b_values,
        pnl=b_pnl,
        initial_cash=initial_cash,
        hold_minutes=b_holds,
        capture=b_capture,
        exit_reasons=b_reasons,
    )
    mean_delta = _mean(deltas)
    delta_lcb = _lcb90(deltas)
    b_dd = _max_drawdown_r(b_values)
    exit_effect_gate = (
        len(paired_rows) >= 20
        and mean_delta is not None
        and mean_delta > 0
        and delta_lcb is not None
        and delta_lcb > 0
        and b_dd <= Decimal("5")
    )

    payload = {
        "purpose": "paired_adaptive_exit_development_replay",
        "production_strategy_changed": False,
        "frozen_v2_changed": False,
        "entry_policy_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "cache_namespace": namespace,
        "cache_basis": basis,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(config),
        "entry_cohort": {
            "name": "delayed_base_acceptance_v3_development_entries",
            "status": "entry hypothesis previously rejected; reused only to provide a fixed paired exit cohort",
            "same_entry_fill_quantity_for_a_and_b": True,
            "portfolio_capacity_recomputed_under_b": False,
        },
        "policy_a": "frozen V2 structural/protected stop + 1.5R target + 60m max hold",
        "policy_b": {
            "structural_stop": "same as A",
            "profit_protection": "same +0.75R arm -> +0.25R protected stop as A",
            "fixed_profit_target": None,
            "fixed_max_hold_minutes": None,
            "force_flat_et": "15:55",
            "indicator_exit": "finalized 5m below falling EMA9 AND (>=2 tactical 1m warnings OR strong 5m confirmation); execute next 1m bar",
            "tactical_1m_warnings": [
                "price below falling EMA9",
                "MACD <= signal with negative histogram",
                "Stoch RSI bearish cross after prior K >=80",
            ],
            "strong_5m_confirmation": [
                "close below EMA20 when available",
                "MACD bearish and Stoch RSI bearish when both available",
            ],
            "stoch_overbought_alone_is_exit": False,
        },
        "exit_effect_gate": {
            "minimum_paired_trades": 20,
            "mean_paired_delta_r_must_be_positive": True,
            "one_sided_90_lcb_of_paired_delta_must_be_positive": True,
            "maximum_policy_b_drawdown_r": "5",
            "passed": exit_effect_gate,
            "note": "This gate tests management effect only. It cannot promote the rejected entry cohort or frozen V2.",
        },
        "paired_effect": {
            "trade_count": len(paired_rows),
            "mean_delta_r": str(mean_delta) if mean_delta is not None else None,
            "one_sided_90_lcb_delta_r": str(delta_lcb) if delta_lcb is not None else None,
            "median_delta_r": str(Decimal(str(median(deltas)))) if deltas else None,
            "b_better_count": sum(delta > 0 for delta in deltas),
            "same_count": sum(delta == 0 for delta in deltas),
            "b_worse_count": sum(delta < 0 for delta in deltas),
        },
        "policy_a_metrics": a_metrics,
        "policy_b_metrics": b_metrics,
        "trades": [
            {
                key: (
                    [str(item) for item in value]
                    if isinstance(value, tuple)
                    else str(value)
                    if isinstance(value, Decimal)
                    else value
                )
                for key, value in row.items()
            }
            for row in paired_rows
        ],
        "warning": "Development-only paired exit research on a previously rejected entry cohort. Same entries/sizes are intentionally held fixed, so policy-B portfolio capacity/cash feedback is not simulated. Historical IEX reconstruction remains partial-market and survivorship/listing biased.",
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out / "paired_trades.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "session_date", "instrument_id", "entry_time", "entry_price", "stop_price", "quantity",
            "full_session_mfe_r", "a_exit_time", "a_exit_reason", "a_r", "a_hold_minutes", "a_capture_pct",
            "b_exit_time", "b_exit_reason", "b_r", "b_hold_minutes", "b_capture_pct", "paired_delta_r",
            "b_indicator_reasons",
        ])
        for row in paired_rows:
            writer.writerow([
                row["session_date"], row["instrument_id"], row["entry_time"], row["entry_price"], row["stop_price"], row["quantity"],
                row["full_session_mfe_r"], row["a_exit_time"], row["a_exit_reason"], row["a_r"], row["a_hold_minutes"],
                (Decimal(str(row["a_capture"])) * Decimal("100")) if row["a_capture"] is not None else "",
                row["b_exit_time"], row["b_exit_reason"], row["b_r"], row["b_hold_minutes"],
                (Decimal(str(row["b_capture"])) * Decimal("100")) if row["b_capture"] is not None else "",
                row["paired_delta_r"], "|".join(row["b_indicator_reasons"]),
            ])

    lines = [
        "# Adaptive indicator exit — paired development replay",
        "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']} sessions**",
        f"- Paired fixed entries: **{len(paired_rows)}**",
        "- Provider calls: **none**",
        "- March loaded: **no**",
        "- Frozen V2 / production authority changed: **no**",
        "",
        "| Metric | A: frozen V2 exits | B: adaptive trend exit |",
        "|---|---:|---:|",
        f"| Expectancy | {a_metrics['expectancy_r']}R | {b_metrics['expectancy_r']}R |",
        f"| 90% LCB | {a_metrics['one_sided_90_lcb_r']}R | {b_metrics['one_sided_90_lcb_r']}R |",
        f"| Win rate | {a_metrics['win_rate']} | {b_metrics['win_rate']} |",
        f"| Avg winner | {a_metrics['average_winner_r']}R | {b_metrics['average_winner_r']}R |",
        f"| Avg loser | {a_metrics['average_loser_r']}R | {b_metrics['average_loser_r']}R |",
        f"| Profit factor (R) | {a_metrics['profit_factor_r']} | {b_metrics['profit_factor_r']} |",
        f"| Max drawdown | {a_metrics['max_drawdown_r']}R | {b_metrics['max_drawdown_r']}R |",
        f"| Avg hold | {a_metrics['average_hold_minutes']} min | {b_metrics['average_hold_minutes']} min |",
        f"| Avg full-session MFE capture | {a_metrics['average_full_session_mfe_capture_pct']}% | {b_metrics['average_full_session_mfe_capture_pct']}% |",
        f"| P&L on same baseline-sized entries | ${a_metrics['pnl']} | ${b_metrics['pnl']} |",
        "",
        f"- Mean paired B-A delta: **{mean_delta if mean_delta is not None else 'N/A'}R**",
        f"- One-sided 90% LCB of paired delta: **{delta_lcb if delta_lcb is not None else 'N/A'}R**",
        f"- B better / same / worse: **{sum(delta > 0 for delta in deltas)} / {sum(delta == 0 for delta in deltas)} / {sum(delta < 0 for delta in deltas)}**",
        f"- Exit-effect development gate passed: **{'YES' if exit_effect_gate else 'NO'}**",
        "",
        "This is an exit-management experiment only. A pass does not revive the rejected delayed-base entry or authorize AUTO PAPER; March remains sealed in this run.",
    ]
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
