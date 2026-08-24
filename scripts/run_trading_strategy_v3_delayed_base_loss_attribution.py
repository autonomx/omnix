from __future__ import annotations

"""Descriptive loser/winner attribution for delayed-base development trades.

Research only. This replays the already-rejected delayed-base cohort on the
immutable Oct-Feb cache and compares causal as-of-entry features. It does not
search thresholds, alter production strategy state, call providers, or read
March.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Iterable

from app.trading.indicator_signals import multi_timeframe_indicator_context
from app.trading.paper import PaperExecutionPolicy
from app.trading.strategies.gap_pullback import _ET, _regular_bars, session_vwap
from app.trading.strategies.models import GapPullbackConfig, StrategyRiskProfile
from app.trading.strategy_backtest import BacktestSessionDataset, run_gap_pullback_backtest
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block
from scripts.run_trading_strategy_v3_canonical_path_research import _research_evaluator
from scripts.run_trading_strategy_v3_delayed_base_acceptance_research import evaluate_delayed_base_acceptance


_BASE_MINUTES = 15
_OPEN_END = time(10, 0)


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Review causal features of delayed-base winners and losers.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--development-start", default="2025-10-01")
    p.add_argument("--development-end", default="2026-02-27")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--output-dir", default="artifacts/v3-delayed-base-loss-attribution")
    return p.parse_args()


def _f(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _pct_ratio(numerator: Decimal | None, denominator: Decimal | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float((numerator / denominator - Decimal("1")) * Decimal("100"))


def _range_pct(high: Decimal | None, low: Decimal | None) -> float | None:
    return _pct_ratio(high, low)


def _vwap(bars) -> Decimal | None:
    usable = [bar for bar in bars if bar.volume > 0]
    volume = sum((bar.volume for bar in usable), Decimal("0"))
    if not usable or volume <= 0:
        return None
    return sum((bar.close * bar.volume for bar in usable), Decimal("0")) / volume


def _median(values: Iterable[float]) -> float | None:
    rows = list(values)
    return median(rows) if rows else None


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


def _sign(value: float | None) -> int:
    if value is None or abs(value) < 1e-12:
        return 0
    return 1 if value > 0 else -1


def _stability(rows: list[dict[str, object]], feature: str, delta: float | None) -> dict[str, int]:
    direction = _sign(delta)
    if direction == 0:
        return {"month_same": 0, "month_total": 0, "symbol_same": 0, "symbol_total": 0}

    def _score(groups: list[str], key: str) -> tuple[int, int]:
        same = total = 0
        for group in groups:
            subset = [row for row in rows if str(row[key]) != group]
            w = [float(row[feature]) for row in subset if row.get(feature) is not None and bool(row["winner"])]
            l = [float(row[feature]) for row in subset if row.get(feature) is not None and not bool(row["winner"])]
            d = _cliffs_delta(w, l)
            if d is None:
                continue
            total += 1
            same += int(_sign(d) == direction)
        return same, total

    month_same, month_total = _score(sorted({str(r["month"]) for r in rows}), "month")
    symbol_same, symbol_total = _score(sorted({str(r["symbol"]) for r in rows}), "symbol")
    return {
        "month_same": month_same,
        "month_total": month_total,
        "symbol_same": symbol_same,
        "symbol_total": symbol_total,
    }


def _bool_rate(rows: list[dict[str, object]], feature: str) -> dict[str, object]:
    available = [row for row in rows if row.get(feature) is not None]
    true_rows = [row for row in available if bool(row[feature])]
    false_rows = [row for row in available if not bool(row[feature])]

    def rate(group):
        return sum(bool(row["winner"]) for row in group) / len(group) if group else None

    tr = rate(true_rows)
    fr = rate(false_rows)
    return {
        "feature": feature,
        "available_n": len(available),
        "true_n": len(true_rows),
        "true_wins": sum(bool(row["winner"]) for row in true_rows),
        "true_win_rate": tr,
        "false_n": len(false_rows),
        "false_wins": sum(bool(row["winner"]) for row in false_rows),
        "false_win_rate": fr,
        "win_rate_delta_true_minus_false": (tr - fr) if tr is not None and fr is not None else None,
    }


def _row(dataset: BacktestSessionDataset, trade, config: GapPullbackConfig) -> dict[str, object]:
    candidate = next(item for item in dataset.universe.candidates if item.instrument_id == trade.instrument_id)
    bars = list(dataset.bars_by_instrument[trade.instrument_id])
    prefix = [bar for bar in bars if bar.end_time <= trade.entry_time]
    regular = list(_regular_bars(prefix))
    premarket = [bar for bar in prefix if bar.start_time.astimezone(_ET).time() < time(9, 30)]
    signal = regular[-1]
    opening = [bar for bar in regular if bar.start_time.astimezone(_ET).time() < _OPEN_END]
    base_start = signal.start_time - timedelta(minutes=_BASE_MINUTES)
    base = [bar for bar in regular[:-1] if bar.start_time >= base_start and bar.end_time <= signal.start_time]

    opening_high = max((bar.high for bar in opening), default=None)
    opening_low = min((bar.low for bar in opening), default=None)
    base_high = max((bar.high for bar in base), default=None)
    base_low = min((bar.low for bar in base), default=None)
    opening_range = _range_pct(opening_high, opening_low)
    base_range = _range_pct(base_high, base_low)
    base_avg_volume = sum((bar.volume for bar in base), Decimal("0")) / Decimal(len(base)) if base else Decimal("0")
    regular_vwap = session_vwap(regular)
    pm_high = max((bar.high for bar in premarket), default=None)
    pm_low = min((bar.low for bar in premarket), default=None)
    pm_vwap = _vwap(premarket)
    signal_range = signal.high - signal.low
    risk_pct = float((trade.entry_price - trade.stop_price) / trade.entry_price * Decimal("100")) if trade.entry_price > 0 else None

    ctx = multi_timeframe_indicator_context(prefix)
    one = ctx.one_minute
    five = ctx.five_minute
    bools = [
        one.price_above_ema9,
        one.ema9_above_ema20,
        one.ema9_rising,
        one.macd_bullish,
        one.stochastic_rsi_bullish,
        five.price_above_ema9,
        five.ema9_above_ema20,
        five.ema9_rising,
        five.macd_bullish,
        five.stochastic_rsi_bullish,
    ]
    indicator_available = [value for value in bools if value is not None]
    indicator_bullish = [value for value in indicator_available if value]

    et = trade.entry_time.astimezone(_ET)
    return {
        "session_date": dataset.session_date.isoformat(),
        "month": dataset.session_date.strftime("%Y-%m"),
        "symbol": trade.instrument_id.rsplit(":", 1)[-1],
        "instrument_id": trade.instrument_id,
        "entry_time": trade.entry_time.isoformat(),
        "entry_time_et": et.strftime("%H:%M"),
        "entry_minutes_since_open": et.hour * 60 + et.minute - 570,
        "winner": trade.r_multiple > 0,
        "r_multiple": float(trade.r_multiple),
        "mfe_r": float(trade.mfe_r),
        "mae_r": float(trade.mae_r),
        "exit_reason": trade.exit_reason,
        "gap_pct": _f(candidate.gap_pct),
        "premarket_dollar_volume": _f(candidate.premarket_dollar_volume),
        "tod_rvol": _f(candidate.tod_rvol),
        "spread_bps": _f(candidate.spread_bps),
        "discovery_rank": candidate.discovery_rank,
        "premarket_bar_count": len(premarket),
        "premarket_range_pct": _range_pct(pm_high, pm_low),
        "signal_vs_premarket_high_pct": _pct_ratio(signal.close, pm_high),
        "signal_vs_premarket_vwap_pct": _pct_ratio(signal.close, pm_vwap),
        "opening_range_pct": opening_range,
        "base_range_pct": base_range,
        "base_to_opening_range_ratio": (base_range / opening_range) if base_range is not None and opening_range not in (None, 0) else None,
        "base_trend_pct": _pct_ratio(base[-1].close, base[0].open) if base else None,
        "signal_vs_base_high_pct": _pct_ratio(signal.close, base_high),
        "signal_vs_opening_high_pct": _pct_ratio(signal.close, opening_high),
        "signal_vs_regular_vwap_pct": _pct_ratio(signal.close, regular_vwap),
        "breakout_volume_ratio": float(signal.volume / base_avg_volume) if base_avg_volume > 0 else None,
        "signal_bar_body_pct": _pct_ratio(signal.close, signal.open),
        "signal_bar_close_location": float((signal.close - signal.low) / signal_range) if signal_range > 0 else None,
        "risk_distance_pct": risk_pct,
        "indicator_available_count": len(indicator_available),
        "indicator_bullish_count": len(indicator_bullish),
        "indicator_bullish_fraction": len(indicator_bullish) / len(indicator_available) if indicator_available else None,
        "one_price_above_ema9": one.price_above_ema9,
        "one_ema9_above_ema20": one.ema9_above_ema20,
        "one_ema9_rising": one.ema9_rising,
        "one_macd_bullish": one.macd_bullish,
        "one_stoch_bullish": one.stochastic_rsi_bullish,
        "five_price_above_ema9": five.price_above_ema9,
        "five_ema9_above_ema20": five.ema9_above_ema20,
        "five_ema9_rising": five.ema9_rising,
        "five_macd_bullish": five.macd_bullish,
        "five_stoch_bullish": five.stochastic_rsi_bullish,
    }


CONTINUOUS = [
    "entry_minutes_since_open",
    "gap_pct",
    "premarket_dollar_volume",
    "tod_rvol",
    "spread_bps",
    "discovery_rank",
    "premarket_bar_count",
    "premarket_range_pct",
    "signal_vs_premarket_high_pct",
    "signal_vs_premarket_vwap_pct",
    "opening_range_pct",
    "base_range_pct",
    "base_to_opening_range_ratio",
    "base_trend_pct",
    "signal_vs_base_high_pct",
    "signal_vs_opening_high_pct",
    "signal_vs_regular_vwap_pct",
    "breakout_volume_ratio",
    "signal_bar_body_pct",
    "signal_bar_close_location",
    "risk_distance_pct",
    "indicator_available_count",
    "indicator_bullish_count",
    "indicator_bullish_fraction",
]

BOOLEAN = [
    "one_price_above_ema9",
    "one_ema9_above_ema20",
    "one_ema9_rising",
    "one_macd_bullish",
    "one_stoch_bullish",
    "five_price_above_ema9",
    "five_ema9_above_ema20",
    "five_ema9_rising",
    "five_macd_bullish",
    "five_stoch_bullish",
]


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
        raise SystemExit("development cache incomplete; provider access prohibited")

    config = frozen_v2_config()
    policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    risk = StrategyRiskProfile()
    cash = initial_cash
    rows: list[dict[str, object]] = []
    candidate_count = 0
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
                initial_cash=cash,
            )
            candidate_count += result.summary.candidate_count
            cash += sum((trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades), Decimal("0"))
            for trade in result.trades:
                rows.append(_row(dataset, trade, config))

    rows.sort(key=lambda row: (str(row["entry_time"]), str(row["instrument_id"])))
    winners = [row for row in rows if bool(row["winner"])]
    losers = [row for row in rows if not bool(row["winner"])]

    continuous = []
    for feature in CONTINUOUS:
        w = [float(row[feature]) for row in winners if row.get(feature) is not None]
        l = [float(row[feature]) for row in losers if row.get(feature) is not None]
        wm = _median(w)
        lm = _median(l)
        delta = _cliffs_delta(w, l)
        stability = _stability(rows, feature, delta)
        continuous.append({
            "feature": feature,
            "winner_n": len(w),
            "loser_n": len(l),
            "winner_median": wm,
            "loser_median": lm,
            "median_difference": wm - lm if wm is not None and lm is not None else None,
            "cliffs_delta": delta,
            "absolute_cliffs_delta": abs(delta) if delta is not None else None,
            **stability,
        })
    continuous.sort(key=lambda row: (row["absolute_cliffs_delta"] is not None, row["absolute_cliffs_delta"] or -1), reverse=True)

    boolean = [_bool_rate(rows, feature) for feature in BOOLEAN]
    boolean.sort(key=lambda row: abs(row["win_rate_delta_true_minus_false"] or 0), reverse=True)

    loss_mfe = Counter()
    for row in losers:
        mfe = float(row["mfe_r"])
        if mfe <= 0.25:
            loss_mfe["mfe_le_0_25r"] += 1
        elif mfe <= 0.50:
            loss_mfe["mfe_0_25_to_0_50r"] += 1
        elif mfe < 0.75:
            loss_mfe["mfe_0_50_to_0_75r"] += 1
        else:
            loss_mfe["mfe_ge_0_75r"] += 1

    time_bins = defaultdict(lambda: {"trades": 0, "wins": 0})
    for row in rows:
        minute = int(row["entry_minutes_since_open"])
        key = "10:15-10:29" if minute < 60 else "10:30-10:59" if minute < 90 else "11:00+"
        time_bins[key]["trades"] += 1
        time_bins[key]["wins"] += int(bool(row["winner"]))
    for value in time_bins.values():
        value["win_rate"] = value["wins"] / value["trades"] if value["trades"] else None

    separators = []
    for row in continuous:
        mtotal = int(row["month_total"])
        stotal = int(row["symbol_total"])
        if (
            row["absolute_cliffs_delta"] is not None
            and float(row["absolute_cliffs_delta"]) >= 0.33
            and int(row["winner_n"]) >= 5
            and int(row["loser_n"]) >= 5
            and (mtotal == 0 or int(row["month_same"]) / mtotal >= 0.75)
            and (stotal == 0 or int(row["symbol_same"]) / stotal >= 0.75)
        ):
            separators.append(row)

    payload = {
        "purpose": "descriptive_delayed_base_loss_attribution",
        "production_strategy_changed": False,
        "frozen_v2_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "cache_namespace": namespace,
        "cache_basis": basis,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(config),
        "candidate_count": candidate_count,
        "trade_count": len(rows),
        "win_count": len(winners),
        "loss_count": len(losers),
        "loss_mfe_taxonomy": dict(loss_mfe),
        "time_of_entry_descriptive": dict(time_bins),
        "continuous_attribution": continuous,
        "stable_large_effect_descriptive_separators": separators,
        "boolean_indicator_attribution": boolean,
        "trades": rows,
        "warning": "Descriptive same-sample hypothesis generation only. Do not convert medians/effect sizes into production thresholds without a separately frozen validation design.",
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out / "trades.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Delayed-base loser review",
        "",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']}**",
        f"- Trades: **{len(rows)}** ({len(winners)}W/{len(losers)}L)",
        f"- Loss MFE: **{dict(loss_mfe)}**",
        f"- Time bins: **{dict(time_bins)}**",
        "- Stable large-effect descriptive separators:",
    ]
    for row in separators:
        lines.append(
            f"  - `{row['feature']}`: winner median={row['winner_median']}, loser median={row['loser_median']}, "
            f"Cliff delta={row['cliffs_delta']:.3f}, month={row['month_same']}/{row['month_total']}, symbol={row['symbol_same']}/{row['symbol_total']}"
        )
    lines.append("- Top boolean indicator splits:")
    for row in boolean[:8]:
        lines.append(
            f"  - `{row['feature']}`: true {row['true_wins']}/{row['true_n']} ({row['true_win_rate']}), "
            f"false {row['false_wins']}/{row['false_n']} ({row['false_win_rate']})"
        )
    lines.append("")
    lines.append("Same-sample descriptive evidence only; March was not loaded.")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
