from __future__ import annotations

"""Paired development replay for a frozen 50% at +1R / adaptive-runner policy.

A = frozen V2 management.
C = exact same entries/fills/sizes, 50% partial target at +1R, then (or before
the target, if momentum deteriorates) the frozen adaptive indicator exit manages
all remaining quantity. Structural/protected stops remain authoritative.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median

from app.trading.paper import PaperExecutionPolicy
from app.trading.strategies.models import StrategyRiskProfile
from app.trading.strategy_backtest import run_gap_pullback_backtest
from app.trading.strategy_partial_runner_research import replay_partial_profit_runner
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block
from scripts.run_trading_strategy_v3_adaptive_exit_research import (
    _capture_ratio,
    _full_session_mfe_r,
    _lcb90,
    _max_drawdown_r,
    _mean,
    _metrics,
)
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator
from scripts.run_trading_strategy_v3_delayed_base_acceptance_research import (
    evaluate_delayed_base_acceptance,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare frozen V2 exits with a frozen 50%-at-1R adaptive runner on identical entries."
    )
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2025-10-01")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--output-dir", default="artifacts/v3-partial-runner-research")
    return parser.parse_args()


def _robustness(deltas: list[Decimal], rows: list[dict[str, object]]) -> dict[str, object]:
    leave_one_out = [
        _mean(deltas[:index] + deltas[index + 1 :])
        for index in range(len(deltas))
        if len(deltas) > 1
    ]
    defined_loo = [value for value in leave_one_out if value is not None]
    month_values: dict[str, list[Decimal]] = defaultdict(list)
    for row in rows:
        month_values[str(row["session_date"])[:7]].append(Decimal(str(row["paired_delta_r"])))
    month_means = {
        month: _mean(values)
        for month, values in sorted(month_values.items())
    }
    positive_months = [
        month
        for month, value in month_means.items()
        if value is not None and value > 0
    ]
    return {
        "minimum_leave_one_trade_out_mean_delta_r": (
            str(min(defined_loo)) if defined_loo else None
        ),
        "leave_one_trade_out_all_positive": bool(defined_loo)
        and min(defined_loo) > 0,
        "months_with_trades": len(month_means),
        "positive_month_count": len(positive_months),
        "positive_months": positive_months,
        "monthly_mean_delta_r": {
            month: str(value) if value is not None else None
            for month, value in month_means.items()
        },
    }


def main() -> int:
    args = _args()
    start = date.fromisoformat(args.development_start)
    end = date.fromisoformat(args.development_end)
    initial_cash = Decimal(args.initial_cash)
    spread = Decimal(args.assumed_spread_bps)

    cache_basis = strict_v11_strategy(
        minimum_premarket_dollar_volume=Decimal("100000")
    )
    namespace, basis = _cache_namespace(cache_basis, spread)
    datasets, coverage = _load_block(
        Path(args.dataset_cache_dir) / namespace,
        start,
        end,
    )
    if int(coverage["covered_sessions"]) != int(coverage["requested_sessions"]):
        raise SystemExit(
            "development cache must be complete: "
            f"{coverage['covered_sessions']}/{coverage['requested_sessions']}; "
            "provider access is prohibited"
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
                (
                    trade.pnl_per_share * trade.entry_fill_quantity
                    for trade in result.trades
                ),
                Decimal("0"),
            )
            candidates = {
                candidate.instrument_id: candidate
                for candidate in dataset.universe.candidates
            }
            for trade in result.trades:
                candidate = candidates[trade.instrument_id]
                partial_runner = replay_partial_profit_runner(
                    candidate=candidate,
                    bars=dataset.bars_by_instrument[trade.instrument_id],
                    baseline_trade=trade,
                    config=config,
                    policy=policy,
                    assumed_spread_bps=spread,
                )
                full_mfe = _full_session_mfe_r(
                    trade,
                    dataset.bars_by_instrument[trade.instrument_id],
                )
                a_capture = _capture_ratio(trade.r_multiple, full_mfe)
                c_capture = _capture_ratio(partial_runner.r_multiple, full_mfe)
                paired_rows.append(
                    {
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
                        "a_capture": a_capture,
                        "c_final_fill_time": partial_runner.final_fill_time.isoformat(),
                        "c_combined_exit_price": partial_runner.combined_exit_price,
                        "c_r": partial_runner.r_multiple,
                        "c_weighted_hold_minutes": partial_runner.weighted_hold_minutes,
                        "c_final_hold_minutes": partial_runner.final_hold_minutes,
                        "c_capture": c_capture,
                        "c_partial_target_price": partial_runner.partial_target_price,
                        "c_partial_target_quantity": partial_runner.partial_target_quantity,
                        "c_partial_filled_quantity": partial_runner.partial_filled_quantity,
                        "c_partial_fill_vwap": partial_runner.partial_fill_vwap,
                        "c_partial_fill_count": partial_runner.partial_fill_count,
                        "c_runner_exit_reason": partial_runner.runner_exit_reason,
                        "c_runner_indicator_reasons": partial_runner.runner_indicator_reason_codes,
                        "c_exit_fill_count": partial_runner.exit_fill_count,
                        "paired_delta_r": partial_runner.r_multiple - trade.r_multiple,
                        "a_pnl": trade.pnl_per_share * trade.entry_fill_quantity,
                        "c_pnl": partial_runner.pnl_per_share
                        * partial_runner.entry_fill_quantity,
                    }
                )

    paired_rows.sort(
        key=lambda row: (str(row["entry_time"]), str(row["instrument_id"]))
    )
    a_values = [Decimal(str(row["a_r"])) for row in paired_rows]
    c_values = [Decimal(str(row["c_r"])) for row in paired_rows]
    deltas = [Decimal(str(row["paired_delta_r"])) for row in paired_rows]

    a_pnl = sum(
        (Decimal(str(row["a_pnl"])) for row in paired_rows),
        Decimal("0"),
    )
    c_pnl = sum(
        (Decimal(str(row["c_pnl"])) for row in paired_rows),
        Decimal("0"),
    )
    a_holds = [
        Decimal(str(row["a_hold_minutes"]))
        for row in paired_rows
    ]
    c_holds = [
        Decimal(str(row["c_weighted_hold_minutes"]))
        for row in paired_rows
    ]
    a_capture = [
        Decimal(str(row["a_capture"]))
        for row in paired_rows
        if row["a_capture"] is not None
    ]
    c_capture = [
        Decimal(str(row["c_capture"]))
        for row in paired_rows
        if row["c_capture"] is not None
    ]
    a_reasons = Counter(str(row["a_exit_reason"]) for row in paired_rows)
    c_reasons = Counter(str(row["c_runner_exit_reason"]) for row in paired_rows)

    a_metrics = _metrics(
        a_values,
        pnl=a_pnl,
        initial_cash=initial_cash,
        hold_minutes=a_holds,
        capture=a_capture,
        exit_reasons=a_reasons,
    )
    c_metrics = _metrics(
        c_values,
        pnl=c_pnl,
        initial_cash=initial_cash,
        hold_minutes=c_holds,
        capture=c_capture,
        exit_reasons=c_reasons,
    )

    mean_delta = _mean(deltas)
    delta_lcb = _lcb90(deltas)
    c_dd = _max_drawdown_r(c_values)
    robustness = _robustness(deltas, paired_rows)
    robust_loo = bool(robustness["leave_one_trade_out_all_positive"])
    months_with_trades = int(robustness["months_with_trades"])
    positive_month_count = int(robustness["positive_month_count"])

    exit_effect_gate = (
        len(paired_rows) >= 20
        and mean_delta is not None
        and mean_delta > 0
        and delta_lcb is not None
        and delta_lcb > 0
        and c_dd <= Decimal("5")
        and robust_loo
        and months_with_trades >= 4
        and positive_month_count >= 3
    )

    full_partial_count = sum(
        Decimal(str(row["c_partial_filled_quantity"]))
        >= Decimal(str(row["c_partial_target_quantity"]))
        for row in paired_rows
    )
    any_partial_count = sum(
        Decimal(str(row["c_partial_filled_quantity"])) > 0
        for row in paired_rows
    )
    indicator_reason_counts: Counter[str] = Counter()
    for row in paired_rows:
        for reason in row["c_runner_indicator_reasons"]:
            indicator_reason_counts[str(reason)] += 1

    payload = {
        "purpose": "paired_partial_profit_adaptive_runner_development_replay",
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
            "status": (
                "entry hypothesis previously rejected; reused only to provide "
                "a fixed paired exit cohort"
            ),
            "same_entry_fill_quantity_for_a_and_c": True,
            "portfolio_capacity_recomputed_under_c": False,
        },
        "policy_a": (
            "frozen V2 structural/protected stop + 1.5R target + 60m max hold"
        ),
        "policy_c": {
            "partial_target_fraction": "0.50",
            "partial_target_r": "1.0",
            "partial_target_ordering": (
                "pessimistic stop-before-target when both are reachable in one bar"
            ),
            "indicator_before_partial_allowed": True,
            "structural_stop": "same as A",
            "profit_protection": (
                "same causal +0.75R arm -> +0.25R protected stop as A"
            ),
            "fixed_full_profit_target": None,
            "fixed_max_hold_minutes": None,
            "force_flat_et": "15:55",
            "runner_indicator_exit": (
                "same frozen policy-B deterioration rule; finalized 5m below "
                "falling EMA9 AND (>=2 tactical 1m warnings OR strong 5m "
                "confirmation); execute next 1m bar"
            ),
        },
        "exit_effect_gate": {
            "minimum_paired_trades": 20,
            "mean_paired_delta_r_must_be_positive": True,
            "one_sided_90_lcb_of_paired_delta_must_be_positive": True,
            "maximum_policy_c_drawdown_r": "5",
            "minimum_leave_one_trade_out_mean_delta_r_must_be_positive": True,
            "minimum_months_with_trades": 4,
            "minimum_positive_months": 3,
            "passed": exit_effect_gate,
            "note": (
                "Exit-management development gate only. Passing cannot promote "
                "the rejected entry cohort or frozen V2."
            ),
        },
        "paired_effect": {
            "trade_count": len(paired_rows),
            "mean_delta_r": str(mean_delta) if mean_delta is not None else None,
            "one_sided_90_lcb_delta_r": (
                str(delta_lcb) if delta_lcb is not None else None
            ),
            "median_delta_r": (
                str(Decimal(str(median(deltas)))) if deltas else None
            ),
            "c_better_count": sum(delta > 0 for delta in deltas),
            "same_count": sum(delta == 0 for delta in deltas),
            "c_worse_count": sum(delta < 0 for delta in deltas),
            "robustness": robustness,
        },
        "policy_a_metrics": a_metrics,
        "policy_c_metrics": c_metrics,
        "partial_target": {
            "any_partial_fill_trade_count": any_partial_count,
            "full_50pct_partial_trade_count": full_partial_count,
        },
        "indicator_reason_counts": dict(sorted(indicator_reason_counts.items())),
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
        "warning": (
            "Development-only paired exit research on a previously rejected "
            "entry cohort. Same entries/sizes are intentionally fixed, so "
            "policy-C portfolio-capacity/cash feedback is not simulated. "
            "Historical IEX reconstruction remains partial-market and "
            "survivorship/listing biased."
        ),
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with (out / "paired_trades.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "session_date",
                "instrument_id",
                "entry_time",
                "entry_price",
                "stop_price",
                "quantity",
                "full_session_mfe_r",
                "a_exit_reason",
                "a_r",
                "a_hold_minutes",
                "c_partial_filled_quantity",
                "c_partial_fill_vwap",
                "c_runner_exit_reason",
                "c_r",
                "c_weighted_hold_minutes",
                "paired_delta_r",
                "c_runner_indicator_reasons",
            ]
        )
        for row in paired_rows:
            writer.writerow(
                [
                    row["session_date"],
                    row["instrument_id"],
                    row["entry_time"],
                    row["entry_price"],
                    row["stop_price"],
                    row["quantity"],
                    row["full_session_mfe_r"],
                    row["a_exit_reason"],
                    row["a_r"],
                    row["a_hold_minutes"],
                    row["c_partial_filled_quantity"],
                    row["c_partial_fill_vwap"],
                    row["c_runner_exit_reason"],
                    row["c_r"],
                    row["c_weighted_hold_minutes"],
                    row["paired_delta_r"],
                    ";".join(row["c_runner_indicator_reasons"]),
                ]
            )

    summary_lines = [
        "# V3 partial-profit + adaptive runner development replay",
        "",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']} sessions**",
        f"- Paired trades: **{len(paired_rows)}**",
        "- March loaded: **no**",
        "- Provider calls: **0**",
        "- Frozen V2 changed: **no**",
        "",
        "## Policy A",
        "",
        f"- Expectancy: **{a_metrics['expectancy_r']}R**",
        f"- One-sided 90% LCB: **{a_metrics['one_sided_90_lcb_r']}R**",
        f"- Win rate: **{a_metrics['win_rate']}**",
        f"- Profit factor: **{a_metrics['profit_factor_r']}**",
        f"- Max drawdown: **{a_metrics['max_drawdown_r']}R**",
        f"- P&L: **${a_metrics['pnl']}**",
        "",
        "## Policy C — 50% at +1R, adaptive runner",
        "",
        f"- Expectancy: **{c_metrics['expectancy_r']}R**",
        f"- One-sided 90% LCB: **{c_metrics['one_sided_90_lcb_r']}R**",
        f"- Win rate: **{c_metrics['win_rate']}**",
        f"- Profit factor: **{c_metrics['profit_factor_r']}**",
        f"- Max drawdown: **{c_metrics['max_drawdown_r']}R**",
        f"- P&L: **${c_metrics['pnl']}**",
        f"- Trades with any +1R partial fill: **{any_partial_count}**",
        f"- Trades completing the full 50% partial: **{full_partial_count}**",
        "",
        "## Paired effect C - A",
        "",
        f"- Mean delta: **{mean_delta}R**",
        f"- Median delta: **{Decimal(str(median(deltas))) if deltas else None}R**",
        f"- One-sided 90% LCB: **{delta_lcb}R**",
        (
            "- C better / same / worse: "
            f"**{sum(delta > 0 for delta in deltas)} / "
            f"{sum(delta == 0 for delta in deltas)} / "
            f"{sum(delta < 0 for delta in deltas)}**"
        ),
        (
            "- Minimum leave-one-trade-out mean delta: "
            f"**{robustness['minimum_leave_one_trade_out_mean_delta_r']}R**"
        ),
        (
            "- Positive months: "
            f"**{positive_month_count}/{months_with_trades}**"
        ),
        f"- Monthly deltas: **{robustness['monthly_mean_delta_r']}**",
        "",
        "## Predeclared development gate",
        "",
        f"**{'PASS' if exit_effect_gate else 'FAIL'}**",
        "",
        (
            "Passing would justify a separately frozen validation experiment only; "
            "it cannot promote the rejected entry cohort or alter frozen V2."
        ),
    ]
    (out / "summary.md").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
