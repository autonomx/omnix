from __future__ import annotations

import argparse
import csv
import json
import time as time_module
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from app.trading.historical_gapper_reconstruction import (
    AlpacaHistoricalGapperReconstructor,
    reconstructed_strategy_config,
)
from app.trading.paper import PaperExecutionPolicy
from app.trading.providers.errors import ProviderRateLimitedError
from app.trading.providers.http_runtime import ProviderHttpRuntime
from app.trading.strategy_backtest import freeze_backtest_session, run_gap_pullback_backtest
from app.trading.strategy_historical_bars import alpaca_historical_session_bars
from app.trading.us_equity_calendar import regular_holidays
from scripts.run_trading_strategy_backtest import strict_v11_strategy


_ET = ZoneInfo("America/New_York")
_DEFAULT_THRESHOLDS = (
    Decimal("250000"),
    Decimal("500000"),
    Decimal("1000000"),
    Decimal("2000000"),
    Decimal("5000000"),
    Decimal("10000000"),
)


def _dates(start_raw: str | None, end_raw: str | None, lookback_days: int) -> tuple[date, date]:
    today_et = datetime.now(_ET).date()
    end = date.fromisoformat(end_raw) if end_raw else today_et - timedelta(days=1)
    start = date.fromisoformat(start_raw) if start_raw else end - timedelta(days=lookback_days - 1)
    if end < start:
        raise ValueError("end date must be on or after start date")
    return start, end


def _trading_dates(start_date: date, end_date: date) -> list[date]:
    output: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5 and cursor not in regular_holidays(cursor.year):
            output.append(cursor)
        cursor += timedelta(days=1)
    return output


def _thresholds(raw: str) -> tuple[Decimal, ...]:
    values = tuple(Decimal(item.strip()) for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError("at least one liquidity threshold is required")
    if any(value < 0 for value in values):
        raise ValueError("liquidity thresholds cannot be negative")
    return tuple(sorted(set(values)))


def _label(threshold: Decimal) -> str:
    value = int(threshold)
    if value >= 1_000_000 and value % 1_000_000 == 0:
        return f"{value // 1_000_000}m"
    if value >= 1_000 and value % 1_000 == 0:
        return f"{value // 1_000}k"
    return str(value)


def _with_rate_limit_retry(label: str, function):
    delays = (15, 30, 60)
    for attempt in range(len(delays) + 1):
        try:
            return function()
        except ProviderRateLimitedError:
            if attempt >= len(delays):
                raise
            delay = delays[attempt]
            print(f"{label}: Alpaca rate limited the request; retrying after {delay}s")
            time_module.sleep(delay)
    raise AssertionError("unreachable")


def _outcome_counts(backtest_result) -> Counter[str]:
    counts: Counter[str] = Counter()
    for decision in backtest_result.candidate_decisions:
        reason = decision.rejection_reason or ("TRIGGERED" if decision.triggered else decision.state.upper())
        counts[str(reason)] += 1
    return counts


def _trade_dump(trade) -> dict[str, object]:
    return trade.model_dump(mode="json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sweep the strict v1.1 premarket dollar-volume gate while reusing identical frozen historical datasets."
    )
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    parser.add_argument("--max-hold-minutes", type=int, default=90)
    parser.add_argument("--reconstruction-max-age-days", type=int, default=30)
    parser.add_argument("--max-sessions", type=int, default=60)
    parser.add_argument(
        "--thresholds",
        default=",".join(str(value) for value in _DEFAULT_THRESHOLDS),
        help="Comma-separated premarket dollar-volume thresholds.",
    )
    parser.add_argument("--output-dir", default="artifacts/liquidity-sweep")
    parser.add_argument("--require-covered-session", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start, end = _dates(args.start_date or None, args.end_date or None, args.lookback_days)
    sessions = _trading_dates(start, end)
    if len(sessions) > args.max_sessions:
        raise ValueError(f"backtest session limit exceeded: {len(sessions)}>{args.max_sessions}")

    thresholds = _thresholds(args.thresholds)
    initial_cash = Decimal(args.initial_cash)
    assumed_spread_bps = Decimal(args.assumed_spread_bps)
    if initial_cash <= 0:
        raise ValueError("initial cash must be positive")

    # Reconstruction does not filter on premarket dollar volume. Use the lowest
    # threshold solely so every variant receives the same reconstructed candidate
    # universe, then freeze regular-session bars once and replay all variants.
    reconstruction_strategy = strict_v11_strategy(
        minimum_premarket_dollar_volume=min(thresholds),
    )
    reconstructor = AlpacaHistoricalGapperReconstructor(
        start_date=start,
        end_date=end,
        config=reconstruction_strategy.config,
        assumed_spread_bps=assumed_spread_bps,
        max_age_days=args.reconstruction_max_age_days,
    )
    regular_runtime = ProviderHttpRuntime("alpaca_strategy_liquidity_sweep", max_concurrency=2)
    execution_policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))

    state: dict[Decimal, dict[str, object]] = {}
    for threshold in thresholds:
        state[threshold] = {
            "cash": initial_cash,
            "candidate_count": 0,
            "trigger_count": 0,
            "trades": [],
            "outcomes": Counter(),
            "days": [],
        }

    covered_sessions = 0
    no_candidate_sessions = 0
    unavailable_sessions: list[dict[str, object]] = []
    dataset_fingerprints: dict[str, str] = {}

    for session_date in sessions:
        print(f"Reconstructing {session_date} once for {len(thresholds)} variants")
        reconstruction = _with_rate_limit_retry(
            f"reconstruct {session_date}",
            lambda session_date=session_date: reconstructor(
                session_date=session_date,
                scan_time=time(9, 20),
                config=reconstruction_strategy.config,
                assumed_spread_bps=assumed_spread_bps,
                max_age_days=args.reconstruction_max_age_days,
            ),
        )
        universe = reconstruction.snapshot
        if universe is None:
            if reconstruction.fidelity == "reconstructed_current_listings_iex":
                covered_sessions += 1
                no_candidate_sessions += 1
                for threshold in thresholds:
                    state[threshold]["days"].append(
                        {
                            "session_date": session_date.isoformat(),
                            "status": "no_candidates",
                            "detail": reconstruction.detail,
                        }
                    )
            else:
                unavailable_sessions.append(
                    {
                        "session_date": session_date.isoformat(),
                        "fidelity": reconstruction.fidelity,
                        "detail": reconstruction.detail,
                    }
                )
            continue

        bars_by_instrument = _with_rate_limit_retry(
            f"regular bars {session_date}",
            lambda universe=universe, session_date=session_date: alpaca_historical_session_bars(
                universe.candidates,
                session_date,
                runtime=regular_runtime,
            ),
        )
        dataset = freeze_backtest_session(
            session_date=session_date,
            universe=universe,
            bars_by_instrument=bars_by_instrument,
        )
        covered_sessions += 1
        dataset_fingerprints[session_date.isoformat()] = dataset.dataset_fingerprint

        for threshold in thresholds:
            strategy = strict_v11_strategy(minimum_premarket_dollar_volume=threshold)
            active_config, fidelity_adjustments = reconstructed_strategy_config(strategy.config)
            current_cash = state[threshold]["cash"]
            result = run_gap_pullback_backtest(
                dataset,
                active_config,
                execution_policy,
                assumed_spread_bps=assumed_spread_bps,
                max_hold_minutes=args.max_hold_minutes,
                max_concurrent_positions=strategy.risk.max_positions,
                risk_profile=strategy.risk,
                initial_cash=current_cash,
            )
            pnl = sum(
                (trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades),
                Decimal("0"),
            )
            state[threshold]["cash"] = current_cash + pnl
            state[threshold]["candidate_count"] += result.summary.candidate_count
            state[threshold]["trigger_count"] += result.summary.trigger_count
            state[threshold]["trades"].extend(result.trades)
            state[threshold]["outcomes"].update(_outcome_counts(result))
            state[threshold]["days"].append(
                {
                    "session_date": session_date.isoformat(),
                    "status": "backtested",
                    "dataset_fingerprint": result.dataset_fingerprint,
                    "candidate_count": result.summary.candidate_count,
                    "trigger_count": result.summary.trigger_count,
                    "trade_count": result.summary.trade_count,
                    "pnl": str(pnl),
                    "fidelity_adjustments": list(fidelity_adjustments),
                    "candidate_outcomes": dict(_outcome_counts(result)),
                    "trades": [_trade_dump(trade) for trade in result.trades],
                }
            )

    comparison: list[dict[str, object]] = []
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for threshold in thresholds:
        threshold_state = state[threshold]
        trades = list(threshold_state["trades"])
        outcomes: Counter[str] = threshold_state["outcomes"]
        ending_cash: Decimal = threshold_state["cash"]
        pnl = ending_cash - initial_cash if covered_sessions else None
        return_pct = (pnl / initial_cash) * Decimal("100") if pnl is not None else None
        expectancy_r = (
            sum((trade.r_multiple for trade in trades), Decimal("0")) / Decimal(len(trades))
            if trades
            else None
        )
        win_count = sum(trade.r_multiple > 0 for trade in trades)
        loss_count = sum(trade.r_multiple < 0 for trade in trades)
        candidate_count = int(threshold_state["candidate_count"])
        liquidity_rejected = int(outcomes.get("PREMARKET_DOLLAR_VOLUME_LOW", 0))
        comparison_row = {
            "threshold": int(threshold),
            "label": _label(threshold),
            "covered_sessions": covered_sessions,
            "requested_sessions": len(sessions),
            "candidate_count": candidate_count,
            "not_rejected_by_liquidity_gate": candidate_count - liquidity_rejected,
            "trigger_count": int(threshold_state["trigger_count"]),
            "trade_count": len(trades),
            "win_count": win_count,
            "loss_count": loss_count,
            "pnl": None if pnl is None else str(pnl),
            "return_pct": None if return_pct is None else str(return_pct),
            "expectancy_r": None if expectancy_r is None else str(expectancy_r),
            "premarket_volume_low": liquidity_rejected,
            "no_market_data": int(outcomes.get("NO_MARKET_DATA", 0)),
            "candidate_outcomes": dict(outcomes),
        }
        comparison.append(comparison_row)
        variant = {
            **comparison_row,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "result_quality": "approximate" if covered_sessions else "unavailable",
            "days": threshold_state["days"],
            "trades": [_trade_dump(trade) for trade in trades],
        }
        (output_dir / f"variant-{_label(threshold)}.json").write_text(
            json.dumps(variant, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    fieldnames = [
        "threshold",
        "label",
        "covered_sessions",
        "requested_sessions",
        "candidate_count",
        "not_rejected_by_liquidity_gate",
        "trigger_count",
        "trade_count",
        "win_count",
        "loss_count",
        "pnl",
        "return_pct",
        "expectancy_r",
        "premarket_volume_low",
        "no_market_data",
    ]
    with (output_dir / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in comparison:
            writer.writerow({field: row[field] for field in fieldnames})

    (output_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "dataset-fingerprints.json").write_text(
        json.dumps(dataset_fingerprints, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "unavailable-sessions.json").write_text(
        json.dumps(unavailable_sessions, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Premarket liquidity sensitivity sweep",
        "",
        f"- Period: {start} through {end}",
        f"- Coverage: {covered_sessions}/{len(sessions)} trading sessions",
        f"- Valid no-candidate sessions: {no_candidate_sessions}",
        "- Fidelity: **approximate reconstructed Alpaca IEX**",
        "- All variants reuse the same frozen reconstructed universe and regular-session bars for each date.",
        "- Only `minimum_premarket_dollar_volume` changes; all other strict v1.1 structure and risk rules remain fixed.",
        "",
        "| Premarket $ gate | Candidates | Pass $ gate | Triggers | Trades | W-L | P&L | Expectancy R |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison:
        threshold_text = f"${row['threshold']:,}"
        pnl_text = "N/A" if row["pnl"] is None else str(row["pnl"])
        expectancy_text = "N/A" if row["expectancy_r"] is None else str(row["expectancy_r"])
        lines.append(
            f"| {threshold_text} | {row['candidate_count']} | {row['not_rejected_by_liquidity_gate']} | "
            f"{row['trigger_count']} | {row['trade_count']} | {row['win_count']}-{row['loss_count']} | "
            f"{pnl_text} | {expectancy_text} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Reconstruction uses today's active listing set and Alpaca IEX partial-market history, so survivorship/listing bias remains possible.",
            "- Historical catalyst, dilution/supply, float, and true historical spread evidence are unavailable and are explicitly downgraded for reconstructed sessions.",
            "- This sweep diagnoses the liquidity gate; it is not sufficient evidence by itself to promote a production threshold.",
        ]
    )
    summary = "\n".join(lines) + "\n"
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    if args.require_covered_session and covered_sessions == 0:
        print("No sessions were covered; refusing to treat this as a successful sweep.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
