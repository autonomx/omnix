from __future__ import annotations

"""Development-only winner/loser attribution for the rejected post-V2 hypothesis.

This script is intentionally descriptive. It restores the immutable causal
October-February dataset cache, replays the already-declared break-and-hold
variants, and measures which *as-of-entry* features differ between profitable
and losing trades. It does not search thresholds, alter frozen V2, call a
provider, or read March.
"""

import argparse
import csv
import json
from collections import Counter
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Iterable

from app.trading.paper import PaperExecutionPolicy
from app.trading.strategies.gap_pullback import _ET, _regular_bars, session_vwap
from app.trading.strategies.models import GapPullbackConfig, StrategyRiskProfile
from app.trading.strategy_backtest import BacktestSessionDataset, run_gap_pullback_backtest
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block
from scripts.run_trading_strategy_v3_breakout_hold_research import evaluate_canonical_break_hold
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Attribute winner/loser differences from cached V3 development trades.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--development-start", default="2025-10-01")
    p.add_argument("--development-end", default="2026-02-27")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--output-dir", default="artifacts/v3-winner-loser-attribution")
    return p.parse_args()


def _d(value: Decimal | int | float | str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _pct(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator <= 0:
        return None
    return float((numerator / denominator - Decimal("1")) * Decimal("100"))


def _vwap(bars) -> Decimal | None:
    usable = [bar for bar in bars if bar.volume > 0]
    if not usable:
        return None
    volume = sum((bar.volume for bar in usable), Decimal("0"))
    if volume <= 0:
        return None
    return sum((bar.close * bar.volume for bar in usable), Decimal("0")) / volume


def _cliffs_delta(winners: list[float], losers: list[float]) -> float | None:
    if not winners or not losers:
        return None
    gt = lt = 0
    for win in winners:
        for loss in losers:
            if win > loss:
                gt += 1
            elif win < loss:
                lt += 1
    return (gt - lt) / (len(winners) * len(losers))


def _median(values: Iterable[float]) -> float | None:
    rows = list(values)
    return median(rows) if rows else None


def _sign(value: float | None, *, epsilon: float = 1e-12) -> int:
    if value is None or abs(value) <= epsilon:
        return 0
    return 1 if value > 0 else -1


def _stability(rows: list[dict[str, object]], feature: str, primary_delta: float | None) -> dict[str, object]:
    direction = _sign(primary_delta)
    if direction == 0:
        return {
            "leave_one_month_out_same_direction": 0,
            "leave_one_month_out_total": 0,
            "leave_one_symbol_out_same_direction": 0,
            "leave_one_symbol_out_total": 0,
        }

    def score(groups: list[str], key: str) -> tuple[int, int]:
        same = total = 0
        for group in groups:
            subset = [row for row in rows if str(row[key]) != group]
            winners = [float(row[feature]) for row in subset if row.get(feature) is not None and bool(row["winner"])]
            losers = [float(row[feature]) for row in subset if row.get(feature) is not None and not bool(row["winner"])]
            delta = _cliffs_delta(winners, losers)
            if delta is None:
                continue
            total += 1
            if _sign(delta) == direction:
                same += 1
        return same, total

    months = sorted({str(row["month"]) for row in rows})
    symbols = sorted({str(row["symbol"]) for row in rows})
    month_same, month_total = score(months, "month")
    symbol_same, symbol_total = score(symbols, "symbol")
    return {
        "leave_one_month_out_same_direction": month_same,
        "leave_one_month_out_total": month_total,
        "leave_one_symbol_out_same_direction": symbol_same,
        "leave_one_symbol_out_total": symbol_total,
    }


def _pre_entry_features(dataset: BacktestSessionDataset, trade, config: GapPullbackConfig) -> dict[str, object]:
    candidate = next(item for item in dataset.universe.candidates if item.instrument_id == trade.instrument_id)
    bars = list(dataset.bars_by_instrument[trade.instrument_id])
    signal_prefix = [bar for bar in bars if bar.end_time <= trade.entry_time]
    regular = list(_regular_bars(signal_prefix))
    premarket = [
        bar
        for bar in signal_prefix
        if bar.start_time.astimezone(_ET).time() < time(9, 30)
    ]
    signal_result = evaluate_canonical_break_hold(candidate, signal_prefix, config)
    f = signal_result.features

    first_5 = regular[:5]
    first_15 = regular[:15]
    signal_bar = regular[-1] if regular else None
    open_price = regular[0].open if regular else None
    pre_entry_high = max((bar.high for bar in regular), default=None)
    pre_entry_low = min((bar.low for bar in regular), default=None)
    pm_high = max((bar.high for bar in premarket), default=None)
    pm_low = min((bar.low for bar in premarket), default=None)
    pm_vwap = _vwap(premarket)
    regular_vwap = session_vwap(regular) if regular else None

    gap_proxy_minutes = []
    for previous, current in zip(regular, regular[1:]):
        gap = (current.start_time - previous.end_time).total_seconds() / 60
        if gap > 0:
            gap_proxy_minutes.append(gap)

    row: dict[str, object] = {
        "session_date": dataset.session_date.isoformat(),
        "month": dataset.session_date.strftime("%Y-%m"),
        "weekday": dataset.session_date.strftime("%A"),
        "instrument_id": trade.instrument_id,
        "symbol": trade.instrument_id.rsplit(":", 1)[-1],
        "entry_time": trade.entry_time.isoformat(),
        "entry_time_et": trade.entry_time.astimezone(_ET).strftime("%H:%M"),
        "entry_minutes_since_open": (trade.entry_time.astimezone(_ET).hour * 60 + trade.entry_time.astimezone(_ET).minute) - (9 * 60 + 30),
        "exit_reason": trade.exit_reason,
        "r_multiple": float(trade.r_multiple),
        "mfe_r": float(trade.mfe_r),
        "mae_r": float(trade.mae_r),
        "winner": trade.r_multiple > 0,
        "gap_pct": _d(candidate.gap_pct),
        "premarket_snapshot_price": _d(candidate.premarket_price),
        "premarket_volume": _d(candidate.premarket_volume),
        "premarket_dollar_volume": _d(candidate.premarket_dollar_volume),
        "tod_rvol": _d(candidate.tod_rvol),
        "spread_bps": _d(candidate.spread_bps),
        "float_shares": _d(candidate.float_shares),
        "discovery_rank": candidate.discovery_rank,
        "catalyst_evidence_count": len(candidate.catalyst_evidence_ids),
        "dilution_flag_count": len(candidate.dilution_flags),
        "premarket_bar_count": len(premarket),
        "premarket_range_pct": _pct(pm_high, pm_low) if pm_high is not None and pm_low is not None else None,
        "signal_vs_premarket_high_pct": _pct(signal_bar.close, pm_high) if signal_bar is not None and pm_high is not None else None,
        "signal_vs_premarket_vwap_pct": _pct(signal_bar.close, pm_vwap) if signal_bar is not None and pm_vwap is not None else None,
        "open_to_signal_pct": _pct(signal_bar.close, open_price) if signal_bar is not None and open_price is not None else None,
        "pre_entry_range_pct": _pct(pre_entry_high, pre_entry_low) if pre_entry_high is not None and pre_entry_low is not None else None,
        "signal_location_in_preentry_range": (
            float((signal_bar.close - pre_entry_low) / (pre_entry_high - pre_entry_low))
            if signal_bar is not None and pre_entry_high is not None and pre_entry_low is not None and pre_entry_high > pre_entry_low
            else None
        ),
        "signal_vs_regular_vwap_pct": _pct(signal_bar.close, regular_vwap) if signal_bar is not None and regular_vwap is not None else None,
        "first5_range_pct": (
            _pct(max(bar.high for bar in first_5), min(bar.low for bar in first_5))
            if len(first_5) == 5
            else None
        ),
        "signal_vs_first5_high_pct": (
            _pct(signal_bar.close, max(bar.high for bar in first_5))
            if signal_bar is not None and len(first_5) == 5
            else None
        ),
        "first15_range_pct": (
            _pct(max(bar.high for bar in first_15), min(bar.low for bar in first_15))
            if len(first_15) == 15
            else None
        ),
        "signal_vs_first15_high_pct": (
            _pct(signal_bar.close, max(bar.high for bar in first_15))
            if signal_bar is not None and len(first_15) == 15
            else None
        ),
        "signal_bar_body_pct": _pct(signal_bar.close, signal_bar.open) if signal_bar is not None else None,
        "signal_bar_close_location": (
            float((signal_bar.close - signal_bar.low) / (signal_bar.high - signal_bar.low))
            if signal_bar is not None and signal_bar.high > signal_bar.low
            else None
        ),
        "regular_bar_gap_proxy_count_gt_2m": sum(gap > 2 for gap in gap_proxy_minutes),
        "regular_bar_gap_proxy_max_minutes": max(gap_proxy_minutes, default=0.0),
        "opening_impulse_pct": _d(f.opening_impulse_pct),
        "pullback_depth_pct": _d(f.pullback_depth_pct),
        "pullback_volume_ratio": _d(f.pullback_volume_ratio),
        "second_pullback_depth_pct": _d(f.second_pullback_depth_pct),
        "l1_to_b1_minutes": _d(f.l1_to_b1_minutes),
        "l2_to_signal_minutes": _d(f.l2_to_signal_minutes),
        "vwap_distance_pct": _d(f.vwap_distance_pct),
        "breakout_volume_ratio": _d(f.breakout_volume_ratio),
        "quality_score": f.quality_score,
    }
    return row


CONTINUOUS_FEATURES = [
    "entry_minutes_since_open",
    "gap_pct",
    "premarket_dollar_volume",
    "tod_rvol",
    "spread_bps",
    "discovery_rank",
    "premarket_range_pct",
    "signal_vs_premarket_high_pct",
    "signal_vs_premarket_vwap_pct",
    "open_to_signal_pct",
    "pre_entry_range_pct",
    "signal_location_in_preentry_range",
    "signal_vs_regular_vwap_pct",
    "first5_range_pct",
    "signal_vs_first5_high_pct",
    "first15_range_pct",
    "signal_vs_first15_high_pct",
    "signal_bar_body_pct",
    "signal_bar_close_location",
    "regular_bar_gap_proxy_count_gt_2m",
    "regular_bar_gap_proxy_max_minutes",
    "opening_impulse_pct",
    "pullback_depth_pct",
    "pullback_volume_ratio",
    "second_pullback_depth_pct",
    "l1_to_b1_minutes",
    "l2_to_signal_minutes",
    "vwap_distance_pct",
    "breakout_volume_ratio",
]


def _attribute(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for feature in CONTINUOUS_FEATURES:
        winner_values = [float(row[feature]) for row in rows if bool(row["winner"]) and row.get(feature) is not None]
        loser_values = [float(row[feature]) for row in rows if not bool(row["winner"]) and row.get(feature) is not None]
        winner_median = _median(winner_values)
        loser_median = _median(loser_values)
        delta = _cliffs_delta(winner_values, loser_values)
        stability = _stability(rows, feature, delta)
        output.append(
            {
                "feature": feature,
                "winner_n": len(winner_values),
                "loser_n": len(loser_values),
                "winner_median": winner_median,
                "loser_median": loser_median,
                "median_difference": winner_median - loser_median if winner_median is not None and loser_median is not None else None,
                "cliffs_delta": delta,
                "absolute_cliffs_delta": abs(delta) if delta is not None else None,
                **stability,
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["absolute_cliffs_delta"] is not None,
            row["absolute_cliffs_delta"] or -1,
            min(int(row["winner_n"]), int(row["loser_n"])),
        ),
        reverse=True,
    )


def _run_variant(
    datasets: list[BacktestSessionDataset],
    config: GapPullbackConfig,
    *,
    initial_cash: Decimal,
    spread: Decimal,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    risk = StrategyRiskProfile()
    current_cash = initial_cash
    rows: list[dict[str, object]] = []
    candidate_count = trigger_count = 0
    with _research_evaluator(evaluate_canonical_break_hold):
        for dataset in datasets:
            result = run_gap_pullback_backtest(
                dataset,
                config,
                policy,
                assumed_spread_bps=spread,
                max_hold_minutes=config.v2_max_hold_minutes,
                max_concurrent_positions=risk.max_positions,
                risk_profile=risk,
                initial_cash=current_cash,
            )
            pnl = sum((trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades), Decimal("0"))
            current_cash += pnl
            candidate_count += result.summary.candidate_count
            trigger_count += result.summary.trigger_count
            for trade in result.trades:
                rows.append(_pre_entry_features(dataset, trade, config))
    r_values = [float(row["r_multiple"]) for row in rows]
    return rows, {
        "candidate_count": candidate_count,
        "trigger_count": trigger_count,
        "trade_count": len(rows),
        "win_count": sum(bool(row["winner"]) for row in rows),
        "loss_count": sum(not bool(row["winner"]) for row in rows),
        "expectancy_r": sum(r_values) / len(r_values) if r_values else None,
        "pnl": float(current_cash - initial_cash),
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(rows[0])
    for row in rows[1:]:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _availability(rows: list[dict[str, object]]) -> dict[str, object]:
    total = len(rows)
    return {
        "trade_count": total,
        "premarket_structure_available": sum(int(row["premarket_bar_count"]) > 0 for row in rows),
        "float_available": sum(row.get("float_shares") is not None for row in rows),
        "catalyst_evidence_present": sum(int(row["catalyst_evidence_count"]) > 0 for row in rows),
        "dilution_flags_present": sum(int(row["dilution_flag_count"]) > 0 for row in rows),
        "halt_evidence_available": False,
        "halt_note": "No point-in-time halt feed is present in the reconstructed dataset. Regular bar gaps are reported only as an IEX/missing-trade proxy and must not be interpreted as confirmed halts.",
    }


def _candidate_separators(attribution: list[dict[str, object]]) -> list[dict[str, object]]:
    """Descriptive shortlist only; not a threshold/rule search."""
    rows = []
    for row in attribution:
        delta = row.get("cliffs_delta")
        if delta is None or abs(float(delta)) < 0.33:
            continue
        if min(int(row["winner_n"]), int(row["loser_n"])) < 5:
            continue
        month_total = int(row["leave_one_month_out_total"])
        symbol_total = int(row["leave_one_symbol_out_total"])
        month_ratio = int(row["leave_one_month_out_same_direction"]) / month_total if month_total else 0
        symbol_ratio = int(row["leave_one_symbol_out_same_direction"]) / symbol_total if symbol_total else 0
        if month_ratio < 0.75 or symbol_ratio < 0.75:
            continue
        rows.append(row)
    return rows


def main() -> int:
    args = _args()
    start = date.fromisoformat(args.development_start)
    end = date.fromisoformat(args.development_end)
    initial_cash = Decimal(args.initial_cash)
    spread = Decimal(args.assumed_spread_bps)

    basis_strategy = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(basis_strategy, spread)
    cache = Path(args.dataset_cache_dir) / namespace
    datasets, coverage = _load_block(cache, start, end)
    if int(coverage["covered_sessions"]) != int(coverage["requested_sessions"]):
        raise SystemExit(
            f"development cache must be complete: {coverage['covered_sessions']}/{coverage['requested_sessions']}; provider access is prohibited"
        )

    frozen = frozen_v2_config()
    configs = {
        "hold_volume_1_5": frozen.model_copy(update={"v2_minimum_breakout_volume_ratio": Decimal("1.5")}),
        "hold_volume_0": frozen.model_copy(update={"v2_minimum_breakout_volume_ratio": Decimal("0")}),
    }

    variants: dict[str, object] = {}
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for variant_id, config in configs.items():
        rows, metrics = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
        attribution = _attribute(rows)
        variants[variant_id] = {
            "profile_fingerprint": v2_profile_fingerprint(config),
            "metrics": metrics,
            "availability": _availability(rows),
            "exit_reasons": dict(Counter(str(row["exit_reason"]) for row in rows)),
            "months": {
                month: {
                    "trades": len(month_rows),
                    "wins": sum(bool(row["winner"]) for row in month_rows),
                    "expectancy_r": sum(float(row["r_multiple"]) for row in month_rows) / len(month_rows),
                }
                for month in sorted({str(row["month"]) for row in rows})
                for month_rows in [[row for row in rows if str(row["month"]) == month]]
            },
            "candidate_separators": _candidate_separators(attribution),
            "attribution": attribution,
        }
        _write_csv(output_dir / f"{variant_id}-trade-features.csv", rows)
        _write_csv(output_dir / f"{variant_id}-feature-attribution.csv", attribution)

    primary = variants["hold_volume_1_5"]
    robust = variants["hold_volume_0"]
    primary_sep = {str(row["feature"]): row for row in primary["candidate_separators"]}
    robust_attr = {str(row["feature"]): row for row in robust["attribution"]}
    cross_variant = []
    for feature, row in primary_sep.items():
        other = robust_attr.get(feature)
        if not other or other.get("cliffs_delta") is None:
            continue
        if _sign(float(row["cliffs_delta"])) == _sign(float(other["cliffs_delta"])) and abs(float(other["cliffs_delta"])) >= 0.20:
            cross_variant.append(
                {
                    "feature": feature,
                    "primary_cliffs_delta": row["cliffs_delta"],
                    "robustness_cliffs_delta": other["cliffs_delta"],
                    "primary_winner_median": row["winner_median"],
                    "primary_loser_median": row["loser_median"],
                }
            )

    payload = {
        "purpose": "winner_loser_feature_attribution_for_future_successor_hypothesis",
        "production_strategy_changed": False,
        "frozen_v2_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "cache_namespace": namespace,
        "cache_basis": basis,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "method": {
            "primary_variant": "hold_volume_1_5",
            "robustness_variant": "hold_volume_0",
            "winner_definition": "realized R > 0 under the already-declared deterministic paper execution/management model",
            "feature_visibility": "candidate snapshot + finalized bars observable no later than the entry timestamp",
            "separator_rule": "|Cliff's delta| >= 0.33, at least 5 winners and 5 losers, and same effect direction in >=75% leave-one-month-out and leave-one-symbol-out recomputations",
            "warning": "Separator screening is descriptive development analysis, not an independently validated trading rule.",
        },
        "variants": variants,
        "cross_variant_stable_separators": cross_variant,
    }
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V3 winner vs loser attribution — development only",
        "",
        f"- Period: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']}**",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
        "- This is descriptive feature attribution, **not threshold optimization**.",
        "",
    ]
    for variant_id in ("hold_volume_1_5", "hold_volume_0"):
        item = variants[variant_id]
        metrics = item["metrics"]
        availability = item["availability"]
        lines.extend(
            [
                f"## {variant_id}",
                "",
                f"- Trades: **{metrics['trade_count']}** ({metrics['win_count']}W/{metrics['loss_count']}L)",
                f"- Expectancy: **{metrics['expectancy_r']:.4f}R**",
                f"- P&L: **${metrics['pnl']:.2f}**",
                f"- Premarket bar structure available: **{availability['premarket_structure_available']}/{availability['trade_count']} trades**",
                f"- Catalyst evidence present: **{availability['catalyst_evidence_present']}/{availability['trade_count']}**",
                f"- Dilution flags present: **{availability['dilution_flags_present']}/{availability['trade_count']}**",
                "",
                "| Feature | Winner median | Loser median | Cliff delta | Month stability | Symbol stability |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in item["attribution"][:12]:
            wm = "N/A" if row["winner_median"] is None else f"{row['winner_median']:.4f}"
            lm = "N/A" if row["loser_median"] is None else f"{row['loser_median']:.4f}"
            cd = "N/A" if row["cliffs_delta"] is None else f"{row['cliffs_delta']:.3f}"
            lines.append(
                f"| {row['feature']} | {wm} | {lm} | {cd} | "
                f"{row['leave_one_month_out_same_direction']}/{row['leave_one_month_out_total']} | "
                f"{row['leave_one_symbol_out_same_direction']}/{row['leave_one_symbol_out_total']} |"
            )
        lines.extend(["", f"Descriptive separators passing the stability screen: **{len(item['candidate_separators'])}**", ""])

    lines.extend(["## Cross-variant stable separators", ""])
    if cross_variant:
        for row in cross_variant:
            lines.append(
                f"- `{row['feature']}` — 1.5x delta {row['primary_cliffs_delta']:.3f}; "
                f"0x delta {row['robustness_cliffs_delta']:.3f}"
            )
    else:
        lines.append("- **None** passed the cross-variant stability screen.")
    lines.extend(
        [
            "",
            "## Data limitations",
            "",
            "- Historical reconstruction uses current listings and Alpaca IEX partial-market bars, so survivorship/listing bias remains.",
            "- Point-in-time catalyst/supply facts are only analyzed when actually present in the frozen candidate snapshot; they are never reconstructed with hindsight.",
            "- No authoritative halt feed exists in this cache. Bar gaps are an IEX/missing-trade proxy only.",
            "- With only 18 primary trades, even large univariate effects remain hypothesis-generating until a separately frozen successor is validated.",
            "",
        ]
    )
    summary = "\n".join(lines)
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
