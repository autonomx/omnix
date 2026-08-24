from __future__ import annotations

"""Cache-only walk-forward sweep for evolving gap_pullback_v1.

This script deliberately separates parameter discovery from validation:
- rank deterministic variants on the earlier cached sessions only;
- evaluate only the top training variants on the later holdout sessions;
- never fetch market data or mutate production defaults.

The missing-TOD-RVOL fallback remains diagnostic-only: if TOD RVOL is missing,
a candidate may continue only after it has already passed the configured absolute
premarket-dollar-volume gate. Numeric TOD RVOL must still satisfy the configured
minimum. This policy is explicit in the artifact and is not silently promoted.
"""

import argparse
import csv
import itertools
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

import app.trading.strategy_backtest as _backtest_module
from app.trading.historical_gapper_reconstruction import reconstructed_strategy_config
from app.trading.paper import PaperExecutionPolicy
from app.trading.strategies.gap_pullback import evaluate_gap_pullback as _production_evaluate
from app.trading.strategies.models import GapPullbackConfig
from app.trading.strategy_backtest import BacktestSessionDataset, run_gap_pullback_backtest
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


@dataclass(frozen=True)
class Variant:
    minimum_premarket_dollar_volume: Decimal
    opening_impulse_min_pct: Decimal
    pullback_min_pct: Decimal
    pivot_bars: int
    higher_low_buffer_bps: Decimal
    pullback_volume_max_ratio: Decimal
    breakout_volume_ratio: Decimal
    require_breakout_hold: bool
    minimum_quality_score: int

    @property
    def variant_id(self) -> str:
        hold = "hold" if self.require_breakout_hold else "nohold"
        return (
            f"liq{int(self.minimum_premarket_dollar_volume)}"
            f"-imp{self.opening_impulse_min_pct}"
            f"-pb{self.pullback_min_pct}"
            f"-pv{self.pivot_bars}"
            f"-hl{self.higher_low_buffer_bps}"
            f"-sv{self.pullback_volume_max_ratio}"
            f"-bv{self.breakout_volume_ratio}"
            f"-{hold}-q{self.minimum_quality_score}"
        )


def _diagnostic_evaluate(candidate, bars, config: GapPullbackConfig | None = None):
    active = config or GapPullbackConfig()
    diagnostic_candidate = candidate
    if (
        candidate.tod_rvol is None
        and candidate.premarket_dollar_volume >= active.minimum_premarket_dollar_volume
    ):
        diagnostic_candidate = candidate.model_copy(update={"tod_rvol": active.minimum_tod_rvol})
    return _production_evaluate(diagnostic_candidate, bars, active)


def _grid() -> Iterable[Variant]:
    return (
        Variant(
            minimum_premarket_dollar_volume=Decimal(str(liquidity)),
            opening_impulse_min_pct=Decimal(str(impulse)),
            pullback_min_pct=Decimal(str(pullback_min)),
            pivot_bars=int(pivot),
            higher_low_buffer_bps=Decimal(str(higher_low)),
            pullback_volume_max_ratio=Decimal(str(pullback_volume)),
            breakout_volume_ratio=Decimal(str(breakout_volume)),
            require_breakout_hold=bool(hold),
            minimum_quality_score=int(quality),
        )
        for (
            liquidity,
            impulse,
            pullback_min,
            pivot,
            higher_low,
            pullback_volume,
            breakout_volume,
            hold,
            quality,
        ) in itertools.product(
            (250000, 500000),
            (3, 5, 8),
            (5, 10, 15),
            (1, 2),
            (0, 20),
            (0.70, 1.00),
            (0.80, 1.00, 1.25),
            (False, True),
            (5, 7),
        )
    )


def _active_config(variant: Variant) -> tuple[GapPullbackConfig, object]:
    strategy = strict_v11_strategy(
        minimum_premarket_dollar_volume=variant.minimum_premarket_dollar_volume
    )
    config = strategy.config.model_copy(
        update={
            "opening_impulse_min_pct": variant.opening_impulse_min_pct,
            "pullback_min_pct": variant.pullback_min_pct,
            "pullback_max_pct": Decimal("60"),
            "pivot_left_bars": variant.pivot_bars,
            "pivot_right_bars": variant.pivot_bars,
            "higher_low_buffer_bps": variant.higher_low_buffer_bps,
            "pullback_volume_max_ratio": variant.pullback_volume_max_ratio,
            "breakout_volume_ratio": variant.breakout_volume_ratio,
            "require_breakout_hold": variant.require_breakout_hold,
            "minimum_quality_score": variant.minimum_quality_score,
        }
    )
    active, _ = reconstructed_strategy_config(config)
    return active, strategy.risk


def _outcomes(result) -> Counter[str]:
    counts: Counter[str] = Counter()
    for decision in result.candidate_decisions:
        reason = decision.rejection_reason or (
            "TRIGGERED" if decision.triggered else decision.state.upper()
        )
        counts[str(reason)] += 1
    return counts


def _run_variant(
    variant: Variant,
    datasets: list[BacktestSessionDataset],
    *,
    initial_cash: Decimal,
    assumed_spread_bps: Decimal,
    max_hold_minutes: int,
) -> dict[str, object]:
    active_config, risk = _active_config(variant)
    execution_policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    cash = initial_cash
    peak_cash = cash
    max_drawdown = Decimal("0")
    candidate_count = 0
    trigger_count = 0
    trades = []
    outcomes: Counter[str] = Counter()
    day_rows: list[dict[str, object]] = []

    for dataset in datasets:
        result = run_gap_pullback_backtest(
            dataset,
            active_config,
            execution_policy,
            assumed_spread_bps=assumed_spread_bps,
            max_hold_minutes=max_hold_minutes,
            max_concurrent_positions=risk.max_positions,
            risk_profile=risk,
            initial_cash=cash,
        )
        pnl = sum(
            (trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades),
            Decimal("0"),
        )
        cash += pnl
        peak_cash = max(peak_cash, cash)
        if peak_cash > 0:
            drawdown = (peak_cash - cash) / peak_cash * Decimal("100")
            max_drawdown = max(max_drawdown, drawdown)
        candidate_count += result.summary.candidate_count
        trigger_count += result.summary.trigger_count
        trades.extend(result.trades)
        day_outcomes = _outcomes(result)
        outcomes.update(day_outcomes)
        day_rows.append(
            {
                "session_date": dataset.session_date.isoformat(),
                "pnl": str(pnl),
                "trade_count": result.summary.trade_count,
                "trigger_count": result.summary.trigger_count,
                "candidate_outcomes": dict(day_outcomes),
            }
        )

    r_values = [trade.r_multiple for trade in trades]
    expectancy = (
        sum(r_values, Decimal("0")) / Decimal(len(r_values)) if r_values else None
    )
    wins = sum(1 for value in r_values if value > 0)
    losses = sum(1 for value in r_values if value < 0)
    pnl = cash - initial_cash
    return_pct = pnl / initial_cash * Decimal("100") if initial_cash else Decimal("0")

    return {
        "variant_id": variant.variant_id,
        "parameters": {
            "minimum_premarket_dollar_volume": str(variant.minimum_premarket_dollar_volume),
            "opening_impulse_min_pct": str(variant.opening_impulse_min_pct),
            "pullback_min_pct": str(variant.pullback_min_pct),
            "pullback_max_pct": "60",
            "pivot_bars": variant.pivot_bars,
            "higher_low_buffer_bps": str(variant.higher_low_buffer_bps),
            "pullback_volume_max_ratio": str(variant.pullback_volume_max_ratio),
            "breakout_volume_ratio": str(variant.breakout_volume_ratio),
            "require_breakout_hold": variant.require_breakout_hold,
            "minimum_quality_score": variant.minimum_quality_score,
        },
        "session_count": len(datasets),
        "candidate_count": candidate_count,
        "trigger_count": trigger_count,
        "trade_count": len(trades),
        "win_count": wins,
        "loss_count": losses,
        "pnl": str(pnl),
        "return_pct": str(return_pct),
        "expectancy_r": None if expectancy is None else str(expectancy),
        "max_drawdown_pct": str(max_drawdown),
        "candidate_outcomes": dict(outcomes),
        "trades": [trade.model_dump(mode="json") for trade in trades],
        "days": day_rows,
    }


def _rank_key(row: dict[str, object]) -> tuple[object, ...]:
    trade_count = int(row["trade_count"])
    trigger_count = int(row["trigger_count"])
    expectancy_raw = row["expectancy_r"]
    expectancy = Decimal(str(expectancy_raw)) if expectancy_raw is not None else Decimal("-999")
    pnl = Decimal(str(row["pnl"]))
    drawdown = Decimal(str(row["max_drawdown_pct"]))
    # Prefer actual positive evidence, then sample size, then expectancy/P&L,
    # while using trigger count only as a final funnel-progress tiebreaker.
    return (
        1 if trade_count >= 2 and expectancy > 0 else 0,
        1 if trade_count >= 1 else 0,
        min(trade_count, 8),
        expectancy,
        pnl,
        -drawdown,
        trigger_count,
    )


def _csv_row(row: dict[str, object], split: str) -> dict[str, object]:
    params = dict(row["parameters"])
    return {
        "split": split,
        "variant_id": row["variant_id"],
        **params,
        "session_count": row["session_count"],
        "candidate_count": row["candidate_count"],
        "trigger_count": row["trigger_count"],
        "trade_count": row["trade_count"],
        "win_count": row["win_count"],
        "loss_count": row["loss_count"],
        "pnl": row["pnl"],
        "return_pct": row["return_pct"],
        "expectancy_r": row["expectancy_r"],
        "max_drawdown_pct": row["max_drawdown_pct"],
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _summary(
    path: Path,
    train_dates: list[date],
    holdout_dates: list[date],
    ranked_train: list[dict[str, object]],
    validation: list[dict[str, object]],
) -> None:
    validation_by_id = {row["variant_id"]: row for row in validation}
    lines = [
        "# Gap-pullback strategy evolution sweep",
        "",
        "This is a cache-only research sweep over fingerprint-verified reconstructed Alpaca IEX sessions.",
        "Production strategy defaults are unchanged.",
        "",
        f"- Training sessions: {', '.join(item.isoformat() for item in train_dates)}",
        f"- Holdout sessions: {', '.join(item.isoformat() for item in holdout_dates)}",
        f"- Variants searched on training data: {len(ranked_train)}",
        "- Selection policy: rank on training only; holdout is reported afterward and is not used to choose the candidates.",
        "- Diagnostic missing-RVOL policy: missing TOD RVOL may continue only after passing absolute premarket liquidity; numeric RVOL still requires >=5x.",
        "- Fixed in this pass: 5m structure / 1m execution, 2R target, 0.35% risk/trade, 09:35-11:30 ET entries, <=150 bps spread.",
        "",
        "## Top training variants and untouched holdout",
        "",
        "| Rank | Variant | Train trades | Train W-L | Train exp R | Train P&L | Holdout trades | Holdout W-L | Holdout exp R | Holdout P&L |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, train in enumerate(ranked_train[:20], start=1):
        holdout = validation_by_id.get(train["variant_id"])
        if holdout is None:
            continue
        lines.append(
            "| {rank} | `{variant}` | {tt} | {tw}-{tl} | {te} | {tp} | {ht} | {hw}-{hl} | {he} | {hp} |".format(
                rank=rank,
                variant=train["variant_id"],
                tt=train["trade_count"],
                tw=train["win_count"],
                tl=train["loss_count"],
                te=train["expectancy_r"] if train["expectancy_r"] is not None else "N/A",
                tp=train["pnl"],
                ht=holdout["trade_count"],
                hw=holdout["win_count"],
                hl=holdout["loss_count"],
                he=holdout["expectancy_r"] if holdout["expectancy_r"] is not None else "N/A",
                hp=holdout["pnl"],
            )
        )

    robust = []
    for train in ranked_train[:20]:
        holdout = validation_by_id.get(train["variant_id"])
        if holdout is None:
            continue
        train_exp = Decimal(str(train["expectancy_r"])) if train["expectancy_r"] is not None else None
        holdout_exp = Decimal(str(holdout["expectancy_r"])) if holdout["expectancy_r"] is not None else None
        if (
            int(train["trade_count"]) >= 2
            and train_exp is not None
            and train_exp > 0
            and int(holdout["trade_count"]) >= 1
            and holdout_exp is not None
            and holdout_exp > 0
        ):
            robust.append((train, holdout))

    lines.extend(["", "## Promotion signal", ""])
    if robust:
        train, holdout = robust[0]
        lines.extend(
            [
                f"The strongest candidate with positive training and holdout expectancy is `{train['variant_id']}`.",
                f"Training: {train['trade_count']} trades, {train['expectancy_r']}R expectancy, P&L {train['pnl']}.",
                f"Holdout: {holdout['trade_count']} trades, {holdout['expectancy_r']}R expectancy, P&L {holdout['pnl']}.",
                "This is still a tiny reconstructed sample and is not sufficient for production promotion; the next step is a longer, newly frozen validation window.",
            ]
        )
    else:
        lines.append(
            "No top-ranked variant yet has both >=2 positive-expectancy training trades and at least one positive-expectancy holdout trade. Do not promote a production rule from this sweep."
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the cache-only gap-pullback evolution sweep.")
    parser.add_argument("--start-date", default="2026-08-10")
    parser.add_argument("--end-date", default="2026-08-21")
    parser.add_argument("--train-sessions", type=int, default=6)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/strategy-evolution")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    parser.add_argument("--max-hold-minutes", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _backtest_module.evaluate_gap_pullback = _diagnostic_evaluate

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    sessions = _trading_dates(start, end)
    if len(sessions) < 4:
        raise ValueError("at least four cached sessions are required for train/holdout validation")
    if args.train_sessions <= 0 or args.train_sessions >= len(sessions):
        raise ValueError("train-sessions must leave at least one holdout session")

    assumed_spread_bps = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    reconstruction_strategy = strict_v11_strategy(
        minimum_premarket_dollar_volume=Decimal("250000")
    )
    namespace, _ = _cache_namespace(reconstruction_strategy, assumed_spread_bps)
    cache_dir = Path(args.dataset_cache_dir) / namespace

    datasets: list[BacktestSessionDataset] = []
    for session_date in sessions:
        path = _dataset_cache_path(cache_dir, session_date)
        if not path.exists():
            raise FileNotFoundError(
                f"missing fingerprint-verified frozen dataset for {session_date}: {path}"
            )
        datasets.append(_load_cached_dataset(path, session_date))

    train = datasets[: args.train_sessions]
    holdout = datasets[args.train_sessions :]
    variants = list(_grid())
    print(
        f"Searching {len(variants)} variants on {len(train)} training sessions; "
        f"{len(holdout)} later sessions are untouched holdout."
    )

    training_results: list[dict[str, object]] = []
    for index, variant in enumerate(variants, start=1):
        training_results.append(
            _run_variant(
                variant,
                train,
                initial_cash=initial_cash,
                assumed_spread_bps=assumed_spread_bps,
                max_hold_minutes=args.max_hold_minutes,
            )
        )
        if index % 200 == 0 or index == len(variants):
            print(f"Training sweep progress: {index}/{len(variants)}")

    ranked_train = sorted(training_results, key=_rank_key, reverse=True)
    top_ids = {row["variant_id"] for row in ranked_train[: args.top_k]}
    variant_by_id = {variant.variant_id: variant for variant in variants}

    validation_results: list[dict[str, object]] = []
    full_results: list[dict[str, object]] = []
    for variant_id in [row["variant_id"] for row in ranked_train[: args.top_k]]:
        variant = variant_by_id[variant_id]
        validation_results.append(
            _run_variant(
                variant,
                holdout,
                initial_cash=initial_cash,
                assumed_spread_bps=assumed_spread_bps,
                max_hold_minutes=args.max_hold_minutes,
            )
        )
        full_results.append(
            _run_variant(
                variant,
                datasets,
                initial_cash=initial_cash,
                assumed_spread_bps=assumed_spread_bps,
                max_hold_minutes=args.max_hold_minutes,
            )
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "training-results.json").write_text(
        json.dumps(training_results, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (output_dir / "top-training.json").write_text(
        json.dumps(ranked_train[: args.top_k], indent=2, default=str) + "\n", encoding="utf-8"
    )
    (output_dir / "holdout-results.json").write_text(
        json.dumps(validation_results, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (output_dir / "full-results.json").write_text(
        json.dumps(full_results, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _write_csv(
        output_dir / "top-comparison.csv",
        [_csv_row(row, "train") for row in ranked_train[: args.top_k]]
        + [_csv_row(row, "holdout") for row in validation_results]
        + [_csv_row(row, "full") for row in full_results],
    )
    _summary(
        output_dir / "summary.md",
        [item.session_date for item in train],
        [item.session_date for item in holdout],
        ranked_train,
        validation_results,
    )
    print((output_dir / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
