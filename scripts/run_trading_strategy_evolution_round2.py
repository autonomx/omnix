from __future__ import annotations

"""Round-two cache-only evolution sweep.

This pass explores whether the strategy should recognize a failed sell-off as a
strict higher low only, or also as a small undercut/double-bottom followed by the
same VWAP/B1 reclaim. Negative higher_low_buffer_bps values are used ONLY inside
this diagnostic to represent an undercut tolerance; production validation still
forbids them and production defaults remain unchanged.
"""

import argparse
import itertools
import json
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from app.trading.historical_gapper_reconstruction import reconstructed_strategy_config
from app.trading.strategy_backtest import BacktestSessionDataset
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)
import scripts.run_trading_strategy_evolution_sweep as _r1


@dataclass(frozen=True)
class Variant:
    structure_interval: str
    pivot_bars: int
    minimum_premarket_dollar_volume: Decimal
    minimum_tod_rvol: Decimal
    opening_impulse_min_pct: Decimal
    pullback_min_pct: Decimal
    higher_low_buffer_bps: Decimal
    last_entry_et: time
    pullback_volume_max_ratio: Decimal
    minimum_quality_score: int
    breakout_volume_ratio: Decimal = Decimal("1.0")
    require_breakout_hold: bool = False

    @property
    def variant_id(self) -> str:
        undercut = (
            f"u{abs(int(self.higher_low_buffer_bps))}"
            if self.higher_low_buffer_bps < 0
            else f"hl{int(self.higher_low_buffer_bps)}"
        )
        return (
            f"s{self.structure_interval}-pv{self.pivot_bars}"
            f"-liq{int(self.minimum_premarket_dollar_volume)}"
            f"-rv{self.minimum_tod_rvol}"
            f"-imp{self.opening_impulse_min_pct}"
            f"-pb{self.pullback_min_pct}"
            f"-{undercut}"
            f"-last{self.last_entry_et.strftime('%H%M')}"
            f"-sv{self.pullback_volume_max_ratio}"
            f"-q{self.minimum_quality_score}"
        )


def _grid():
    structure_pairs = (("5m", 1), ("1m", 2), ("1m", 3), ("1m", 5))
    for (
        structure_pair,
        liquidity,
        rvol,
        impulse,
        pullback_min,
        higher_low,
        last_entry,
        pullback_volume,
        quality,
    ) in itertools.product(
        structure_pairs,
        (250000, 500000),
        (3, 5),
        (2, 3),
        (3, 5),
        (-200, -100, 0),
        (time(11, 30), time(13, 0)),
        (0.70, 1.00),
        (4, 5),
    ):
        structure_interval, pivot_bars = structure_pair
        yield Variant(
            structure_interval=structure_interval,
            pivot_bars=pivot_bars,
            minimum_premarket_dollar_volume=Decimal(str(liquidity)),
            minimum_tod_rvol=Decimal(str(rvol)),
            opening_impulse_min_pct=Decimal(str(impulse)),
            pullback_min_pct=Decimal(str(pullback_min)),
            higher_low_buffer_bps=Decimal(str(higher_low)),
            last_entry_et=last_entry,
            pullback_volume_max_ratio=Decimal(str(pullback_volume)),
            minimum_quality_score=int(quality),
        )


def _active_config(variant: Variant):
    strategy = strict_v11_strategy(
        minimum_premarket_dollar_volume=variant.minimum_premarket_dollar_volume
    )
    # model_copy intentionally avoids production field validation for the negative
    # diagnostic undercut tolerance. No persisted strategy can contain this value.
    config = strategy.config.model_copy(
        update={
            "structure_interval": variant.structure_interval,
            "execution_interval": "1m",
            "minimum_tod_rvol": variant.minimum_tod_rvol,
            "opening_impulse_min_pct": variant.opening_impulse_min_pct,
            "pullback_min_pct": variant.pullback_min_pct,
            "pullback_max_pct": Decimal("60"),
            "pivot_left_bars": variant.pivot_bars,
            "pivot_right_bars": variant.pivot_bars,
            "higher_low_buffer_bps": variant.higher_low_buffer_bps,
            "pullback_volume_max_ratio": variant.pullback_volume_max_ratio,
            "breakout_volume_ratio": variant.breakout_volume_ratio,
            "require_breakout_hold": False,
            "minimum_quality_score": variant.minimum_quality_score,
            "last_entry_et": variant.last_entry_et,
        }
    )
    active, _ = reconstructed_strategy_config(config)
    risk = strategy.risk.model_copy(update={"last_entry_et": variant.last_entry_et})
    return active, risk


def _run_variant(variant: Variant, datasets: list[BacktestSessionDataset], **kwargs):
    original = _r1._active_config
    try:
        _r1._active_config = _active_config
        row = _r1._run_variant(variant, datasets, **kwargs)
    finally:
        _r1._active_config = original
    row["parameters"].update(
        {
            "structure_interval": variant.structure_interval,
            "minimum_tod_rvol": str(variant.minimum_tod_rvol),
            "last_entry_et": variant.last_entry_et.isoformat(),
            "diagnostic_second_low_undercut_tolerance_bps": (
                str(abs(variant.higher_low_buffer_bps))
                if variant.higher_low_buffer_bps < 0
                else "0"
            ),
        }
    )
    return row


def _write_summary(path: Path, train_dates, holdout_dates, ranked_train, validation):
    holdout_by_id = {row["variant_id"]: row for row in validation}
    lines = [
        "# Gap-pullback strategy evolution — round 2",
        "",
        "Cache-only research over the same fingerprint-verified reconstructed sessions. Production defaults are unchanged.",
        "",
        f"- Training: {', '.join(item.isoformat() for item in train_dates)}",
        f"- Holdout: {', '.join(item.isoformat() for item in holdout_dates)}",
        f"- Training variants: {len(ranked_train)}",
        "- Holdout remains untouched until after training rank selection.",
        "- Diagnostic missing-RVOL fallback remains enabled; numeric RVOL minimum itself is swept at 3x/5x.",
        "- Diagnostic second-low tolerance: 0%, 1%, or 2% undercut below L1 before the normal VWAP/B1 reclaim. Negative production config values are NOT persisted or promoted.",
        "- Fixed: 2R target, 0.35% risk/trade, 1m execution, <=150 bps spread, breakout volume >=1.0x, no extra hold-confirmation requirement.",
        "",
        "## Top training variants vs untouched holdout",
        "",
        "| Rank | Variant | Train trades | Train W-L | Train exp R | Train P&L | Holdout trades | Holdout W-L | Holdout exp R | Holdout P&L |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, train in enumerate(ranked_train[:30], 1):
        holdout = holdout_by_id[train["variant_id"]]
        lines.append(
            f"| {rank} | `{train['variant_id']}` | {train['trade_count']} | {train['win_count']}-{train['loss_count']} | "
            f"{train['expectancy_r'] if train['expectancy_r'] is not None else 'N/A'} | {train['pnl']} | "
            f"{holdout['trade_count']} | {holdout['win_count']}-{holdout['loss_count']} | "
            f"{holdout['expectancy_r'] if holdout['expectancy_r'] is not None else 'N/A'} | {holdout['pnl']} |"
        )

    robust = []
    for train in ranked_train[:30]:
        holdout = holdout_by_id[train["variant_id"]]
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

    lines.extend(["", "## Round-2 conclusion", ""])
    if robust:
        train, holdout = robust[0]
        lines.extend(
            [
                f"Best preliminary train+holdout candidate: `{train['variant_id']}`.",
                f"Training: {train['trade_count']} trades, {train['expectancy_r']}R expectancy, P&L {train['pnl']}.",
                f"Holdout: {holdout['trade_count']} trades, {holdout['expectancy_r']}R expectancy, P&L {holdout['pnl']}.",
                "This is still insufficient for production promotion; next validate exit/risk choices and a longer newly frozen date range.",
            ]
        )
    else:
        lines.append("No candidate yet meets the preliminary positive-expectancy train+holdout rule. Continue evolving structure rather than promoting a setting.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Run round-two cache-only strategy evolution.")
    parser.add_argument("--start-date", default="2026-08-10")
    parser.add_argument("--end-date", default="2026-08-21")
    parser.add_argument("--train-sessions", type=int, default=6)
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/strategy-evolution-round2")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    parser.add_argument("--max-hold-minutes", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Reuse the explicit diagnostic missing-RVOL evaluator from round 1.
    _r1._backtest_module.evaluate_gap_pullback = _r1._diagnostic_evaluate

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    sessions = _trading_dates(start, end)
    if args.train_sessions <= 0 or args.train_sessions >= len(sessions):
        raise ValueError("train-sessions must leave at least one holdout session")

    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("250000")),
        spread,
    )
    cache_dir = Path(args.dataset_cache_dir) / namespace
    datasets: list[BacktestSessionDataset] = []
    for session_date in sessions:
        path = _dataset_cache_path(cache_dir, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing frozen dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))

    train = datasets[: args.train_sessions]
    holdout = datasets[args.train_sessions :]
    variants = list(_grid())
    print(f"Round 2: searching {len(variants)} variants on {len(train)} train sessions; {len(holdout)} holdout.")

    training = []
    for index, variant in enumerate(variants, 1):
        training.append(
            _run_variant(
                variant,
                train,
                initial_cash=initial_cash,
                assumed_spread_bps=spread,
                max_hold_minutes=args.max_hold_minutes,
            )
        )
        if index % 200 == 0 or index == len(variants):
            print(f"Round-2 progress: {index}/{len(variants)}")

    ranked = sorted(training, key=_r1._rank_key, reverse=True)
    variant_by_id = {variant.variant_id: variant for variant in variants}
    selected_ids = [row["variant_id"] for row in ranked[: args.top_k]]
    validation = [
        _run_variant(
            variant_by_id[variant_id],
            holdout,
            initial_cash=initial_cash,
            assumed_spread_bps=spread,
            max_hold_minutes=args.max_hold_minutes,
        )
        for variant_id in selected_ids
    ]
    full = [
        _run_variant(
            variant_by_id[variant_id],
            datasets,
            initial_cash=initial_cash,
            assumed_spread_bps=spread,
            max_hold_minutes=args.max_hold_minutes,
        )
        for variant_id in selected_ids
    ]

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "training-results.json").write_text(json.dumps(training, indent=2, default=str) + "\n", encoding="utf-8")
    (output / "top-training.json").write_text(json.dumps(ranked[: args.top_k], indent=2, default=str) + "\n", encoding="utf-8")
    (output / "holdout-results.json").write_text(json.dumps(validation, indent=2, default=str) + "\n", encoding="utf-8")
    (output / "full-results.json").write_text(json.dumps(full, indent=2, default=str) + "\n", encoding="utf-8")
    _r1._write_csv(
        output / "top-comparison.csv",
        [_r1._csv_row(row, "train") for row in ranked[: args.top_k]]
        + [_r1._csv_row(row, "holdout") for row in validation]
        + [_r1._csv_row(row, "full") for row in full],
    )
    _write_summary(
        output / "summary.md",
        [item.session_date for item in train],
        [item.session_date for item in holdout],
        ranked,
        validation,
    )
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
