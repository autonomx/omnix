from __future__ import annotations

"""V6 cache-only research: restore causal quality around the V5 structure.

V5's external May/June validation failed because most losers never developed
meaningful favorable excursion.  This pass therefore changes entry selection,
not exits.  All previously revealed blocks are development evidence now, while
a new older block must remain untouched for any selected V6 rule.

The V5 finalized-bar breakout hold remains fixed.  V6 only studies quality
conditions that were part of the original failed-selloff thesis and are known at
signal time:

* absolute premarket dollar liquidity;
* breakout-bar volume expansion versus the five prior finalized 1-minute bars;
* minimum stop/risk distance as a percentage of confirmed entry; and
* a tighter last-entry cutoff.

The V4 +0.75R -> +0.25R profit-protection rule and 60-minute maximum hold are
kept fixed.  Production strategy defaults are not changed.
"""

import argparse
import csv
import itertools
import json
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import app.trading.strategy_backtest as _bt
import scripts.run_trading_strategy_failed_selloff_v2_sweep as _v2
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
import scripts.run_trading_strategy_failed_selloff_v5_confirmation as _v5
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


_BASE_V5_EVALUATE = _v5._confirmation_evaluate
_ACTIVE_VARIANT = None


@dataclass(frozen=True)
class QualityRestoreVariant:
    minimum_premarket_dollar_volume: Decimal
    minimum_tod_rvol: Decimal
    selloff_min_pct: Decimal
    selloff_max_pct: Decimal
    recovery_min_pct: Decimal
    breakout_lookback_bars: int
    bars_after_low: int
    breakout_volume_ratio: Decimal
    last_entry_et: time
    reward_multiple: Decimal
    breakeven_trigger_r: Decimal | None
    protected_stop_r: Decimal
    max_hold_minutes: int
    confirmation_mode: str
    hold_close_margin_pct: Decimal
    minimum_breakout_volume_ratio: Decimal
    minimum_risk_pct: Decimal

    @property
    def variant_id(self) -> str:
        return (
            f"v6-liq{int(self.minimum_premarket_dollar_volume)}"
            f"-bvol{self.minimum_breakout_volume_ratio}"
            f"-risk{self.minimum_risk_pct}"
            f"-last{self.last_entry_et.strftime('%H%M')}"
        )


def _grid():
    # 4 * 3 * 2 * 2 = 48 compact, causal variants.
    for liquidity, volume_ratio, risk_pct, last_entry in itertools.product(
        (Decimal("100000"), Decimal("250000"), Decimal("500000"), Decimal("1000000")),
        (Decimal("0.8"), Decimal("1.0"), Decimal("1.25")),
        (Decimal("3"), Decimal("5")),
        (time(10, 30), time(11, 30)),
    ):
        yield QualityRestoreVariant(
            minimum_premarket_dollar_volume=liquidity,
            minimum_tod_rvol=Decimal("3"),
            selloff_min_pct=Decimal("8"),
            selloff_max_pct=Decimal("25"),
            recovery_min_pct=Decimal("3"),
            breakout_lookback_bars=1,
            bars_after_low=1,
            # V6 computes volume on the actual breakout bar below.  Keep the
            # V2 field disabled so the metric is not accidentally measured on
            # a different finalized bar.
            breakout_volume_ratio=Decimal("0"),
            last_entry_et=last_entry,
            reward_multiple=Decimal("1.5"),
            breakeven_trigger_r=Decimal("0.75"),
            protected_stop_r=Decimal("0.25"),
            max_hold_minutes=60,
            confirmation_mode="close",
            hold_close_margin_pct=Decimal("0"),
            minimum_breakout_volume_ratio=volume_ratio,
            minimum_risk_pct=risk_pct,
        )


def _wait(result, reason: str):
    return result.model_copy(
        update={
            "state": "lower_high_break",
            "reason_code": reason,
            "signal": None,
            "transitions": tuple(list(result.transitions) + ["v6_quality_wait"]),
        }
    )


def _quality_restore_evaluate(candidate, bars, config=None):
    result = _BASE_V5_EVALUATE(candidate, bars, config)
    variant = _ACTIVE_VARIANT
    if variant is None or result.signal is None or result.state != "entry_ready":
        return result

    regular = _v2._regular_bars(list(bars))
    if len(regular) < 3:
        return _wait(result, "V6_INSUFFICIENT_FINAL_BARS")

    # V5 emits only after a later finalized hold bar.  The immediately previous
    # regular bar is therefore the breakout bar whose volume belongs in the
    # original breakout-expansion rule.
    hold_bar = regular[-1]
    breakout_bar = regular[-2]

    # The confirmation bar itself must still be inside the configured entry
    # window.  This closes the one-bar edge case where the breakout occurred at
    # the cutoff but its required hold completed after it.
    if hold_bar.end_time.astimezone(_v2._ET).time() > variant.last_entry_et:
        return _wait(result, "V6_CONFIRMED_AFTER_ENTRY_CUTOFF")

    prior = regular[max(0, len(regular) - 7):-2]
    if not prior:
        return _wait(result, "V6_BREAKOUT_VOLUME_BASELINE_MISSING")
    average_volume = sum((bar.volume for bar in prior), Decimal("0")) / Decimal(len(prior))
    if average_volume <= 0:
        return _wait(result, "V6_BREAKOUT_VOLUME_BASELINE_MISSING")
    breakout_volume_ratio = breakout_bar.volume / average_volume
    if breakout_volume_ratio < variant.minimum_breakout_volume_ratio:
        return _wait(result, "V6_BREAKOUT_VOLUME_TOO_LOW")

    signal = result.signal
    if signal.entry_price <= 0:
        return _wait(result, "V6_INVALID_ENTRY_PRICE")
    risk_pct = signal.risk_per_share / signal.entry_price * Decimal("100")
    if risk_pct < variant.minimum_risk_pct:
        return _wait(result, "V6_RISK_DISTANCE_TOO_TIGHT")

    return result


def _run_variant(variant, datasets, *, initial_cash, spread):
    global _ACTIVE_VARIANT
    _ACTIVE_VARIANT = variant
    _v5._ACTIVE_CONFIRMATION = variant
    _v4._ACTIVE_MANAGEMENT = variant
    return _v4._BASE_RUN_VARIANT(
        variant,
        datasets,
        initial_cash=initial_cash,
        spread=spread,
        max_hold_minutes=variant.max_hold_minutes,
    )


def _expectancy(row):
    value = row.get("expectancy_r")
    return Decimal(str(value)) if value is not None else Decimal("-999")


def _worst_trade(row):
    trades = row.get("trades") or []
    return min((Decimal(str(t["r_multiple"])) for t in trades), default=Decimal("-999"))


def _rank_key(bundle):
    blocks = bundle["blocks"]
    exps = [_expectancy(block) for block in blocks]
    counts = [int(block["trade_count"]) for block in blocks]
    full = bundle["full"]
    full_exp = _expectancy(full)
    positive_blocks = sum(exp > 0 for exp in exps)
    robust = (
        positive_blocks == 3
        and all(count >= 2 for count in counts)
        and int(full["trade_count"]) >= 12
        and full_exp > 0
    )
    return (
        1 if robust else 0,
        positive_blocks,
        min(exps),
        min(counts),
        full_exp,
        _worst_trade(full),
        Decimal(str(full["pnl"])),
        -Decimal(str(full["max_drawdown_pct"])),
    )


def _load_block(cache: Path, start: date, end: date):
    datasets = []
    for session_date in _trading_dates(start, end):
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing frozen development dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))
    if not datasets:
        raise ValueError(f"empty development block: {start}..{end}")
    return datasets


def parse_args():
    parser = argparse.ArgumentParser(description="Run V6 cross-regime failed-selloff quality restoration.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--output-dir", default="artifacts/failed-selloff-v6-quality")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="40")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _bt.evaluate_gap_pullback = _quality_restore_evaluate
    _bt._find_trade = _v4._managed_find_trade

    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    cache = Path(args.dataset_cache_dir) / namespace

    # All three blocks have already been revealed by prior experiments.  They
    # are development-only in V6.  No April/May holdout is loaded here.
    block_specs = (
        (date(2026, 5, 26), date(2026, 6, 18)),
        (date(2026, 6, 26), date(2026, 7, 23)),
        (date(2026, 7, 24), date(2026, 8, 21)),
    )
    blocks = [_load_block(cache, start, end) for start, end in block_specs]
    all_datasets = [dataset for block in blocks for dataset in block]
    if len(all_datasets) != 58:
        raise ValueError(f"V6 expects 58 revealed development sessions, got {len(all_datasets)}")

    variants = list(_grid())
    rows = []
    for index, variant in enumerate(variants, 1):
        block_results = [
            _run_variant(variant, block, initial_cash=initial_cash, spread=spread)
            for block in blocks
        ]
        full = _run_variant(variant, all_datasets, initial_cash=initial_cash, spread=spread)
        rows.append(
            {
                "variant_id": variant.variant_id,
                "parameters": {
                    "minimum_premarket_dollar_volume": str(variant.minimum_premarket_dollar_volume),
                    "minimum_breakout_volume_ratio": str(variant.minimum_breakout_volume_ratio),
                    "minimum_risk_pct": str(variant.minimum_risk_pct),
                    "last_entry_et": variant.last_entry_et.isoformat(),
                    "confirmation_mode": variant.confirmation_mode,
                    "breakeven_trigger_r": str(variant.breakeven_trigger_r),
                    "protected_stop_r": str(variant.protected_stop_r),
                    "max_hold_minutes": variant.max_hold_minutes,
                },
                "blocks": block_results,
                "full": full,
            }
        )
        if index % 8 == 0 or index == len(variants):
            print(f"V6 progress: {index}/{len(variants)}")

    ranked = sorted(rows, key=_rank_key, reverse=True)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(rows, indent=2, default=str) + "\n", encoding="utf-8")
    (output / "ranked.json").write_text(json.dumps(ranked, indent=2, default=str) + "\n", encoding="utf-8")

    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "rank", "variant_id",
            "block1_trades", "block1_exp_r", "block1_pnl",
            "block2_trades", "block2_exp_r", "block2_pnl",
            "block3_trades", "block3_exp_r", "block3_pnl",
            "full_trades", "full_exp_r", "full_pnl", "worst_trade_r", "max_drawdown_pct",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, bundle in enumerate(ranked, 1):
            b1, b2, b3 = bundle["blocks"]
            full = bundle["full"]
            writer.writerow(
                {
                    "rank": rank,
                    "variant_id": bundle["variant_id"],
                    "block1_trades": b1["trade_count"], "block1_exp_r": b1["expectancy_r"], "block1_pnl": b1["pnl"],
                    "block2_trades": b2["trade_count"], "block2_exp_r": b2["expectancy_r"], "block2_pnl": b2["pnl"],
                    "block3_trades": b3["trade_count"], "block3_exp_r": b3["expectancy_r"], "block3_pnl": b3["pnl"],
                    "full_trades": full["trade_count"], "full_exp_r": full["expectancy_r"], "full_pnl": full["pnl"],
                    "worst_trade_r": str(_worst_trade(full)),
                    "max_drawdown_pct": full["max_drawdown_pct"],
                }
            )

    lines = [
        "# Failed-selloff V6 cross-regime quality restoration",
        "",
        "All previously revealed sessions are development data. A new April/May block remains excluded from this sweep.",
        "",
        f"- Block 1: {blocks[0][0].session_date} through {blocks[0][-1].session_date} ({len(blocks[0])} sessions)",
        f"- Block 2: {blocks[1][0].session_date} through {blocks[1][-1].session_date} ({len(blocks[1])} sessions)",
        f"- Block 3: {blocks[2][0].session_date} through {blocks[2][-1].session_date} ({len(blocks[2])} sessions)",
        f"- Variants: {len(variants)}",
        "- Fixed structure: V5 one-finalized-bar close hold above breakout/VWAP.",
        "- Fixed management: prior finalized +0.75R excursion ratchets next-bar stop to +0.25R; 60-minute max hold.",
        "- Variable quality: premarket dollar liquidity, actual breakout-bar volume expansion, risk distance, and last-entry cutoff.",
        "- Ranking prioritizes positive expectancy in all three revealed regimes with at least 2 trades per block and 12 total.",
        "",
        "| Rank | Variant | B1 trades / expR | B2 trades / expR | B3 trades / expR | Full trades / expR | Full P&L | Worst R |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, bundle in enumerate(ranked[:20], 1):
        b1, b2, b3 = bundle["blocks"]
        full = bundle["full"]
        lines.append(
            f"| {rank} | `{bundle['variant_id']}` | {b1['trade_count']} / {b1['expectancy_r']} | "
            f"{b2['trade_count']} / {b2['expectancy_r']} | {b3['trade_count']} / {b3['expectancy_r']} | "
            f"{full['trade_count']} / {full['expectancy_r']} | {full['pnl']} | {_worst_trade(full)} |"
        )

    candidate = None
    for bundle in ranked:
        exps = [_expectancy(block) for block in bundle["blocks"]]
        counts = [int(block["trade_count"]) for block in bundle["blocks"]]
        if (
            all(exp > 0 for exp in exps)
            and all(count >= 2 for count in counts)
            and int(bundle["full"]["trade_count"]) >= 12
            and _expectancy(bundle["full"]) > 0
        ):
            candidate = bundle
            break

    lines.extend(["", "## V6 conclusion", ""])
    if candidate is None:
        lines.append("No V6 variant meets the cross-regime robustness rule. Do not consume the new external holdout; continue entry-model research.")
    else:
        full = candidate["full"]
        lines.extend(
            [
                f"Preliminary V6 candidate: `{candidate['variant_id']}`.",
                f"Full revealed development: {full['trade_count']} trades, {full['expectancy_r']}R expectancy, P&L {full['pnl']}.",
                "Freeze this exact configuration before any new April/May validation run.",
            ]
        )

    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
