from __future__ import annotations

"""V5 cache-only research: cross-regime breakout confirmation.

V4 improved profit give-back but remained regime-sensitive. This pass changes
model selection and entry confirmation instead of tuning against the rejected
external block:

* the same 21 Jul-24..Aug-21 development sessions are split into three ordered
  seven-session blocks;
* the initial failed-selloff breakout is never directly actionable when a hold
  rule is enabled;
* a later finalized 1-minute bar must still hold the broken level and VWAP
  before an entry signal is emitted;
* the V4 causal profit-protection variants are compared with/without that extra
  confirmation;
* ranking is driven first by the weakest development block, not by aggregate
  return.

No production defaults are changed. A selected rule still requires validation
on a new block that was never used by this script.
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
from app.trading.strategies.gap_pullback import session_vwap
from app.trading.strategies.models import StrategySignal
import scripts.run_trading_strategy_failed_selloff_v2_sweep as _v2
import scripts.run_trading_strategy_failed_selloff_v4_management as _v4
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _trading_dates,
)


_BASE_V2_EVALUATE = _v2._failed_selloff_v2_evaluate
_ACTIVE_CONFIRMATION = None


@dataclass(frozen=True)
class ConfirmationVariant:
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

    @property
    def variant_id(self) -> str:
        trigger = "none" if self.breakeven_trigger_r is None else str(self.breakeven_trigger_r)
        return (
            f"v5-{self.confirmation_mode}-m{self.hold_close_margin_pct}"
            f"-be{trigger}-lock{self.protected_stop_r}-hold{self.max_hold_minutes}"
        )


def _variant(mode, margin, be_trigger, lock_r):
    return ConfirmationVariant(
        minimum_premarket_dollar_volume=Decimal("100000"),
        minimum_tod_rvol=Decimal("3"),
        selloff_min_pct=Decimal("8"),
        selloff_max_pct=Decimal("25"),
        recovery_min_pct=Decimal("3"),
        breakout_lookback_bars=1,
        bars_after_low=1,
        breakout_volume_ratio=Decimal("0"),
        last_entry_et=time(11, 30),
        reward_multiple=Decimal("1.5"),
        breakeven_trigger_r=be_trigger,
        protected_stop_r=lock_r,
        max_hold_minutes=60,
        confirmation_mode=mode,
        hold_close_margin_pct=margin,
    )


def _grid():
    # Baseline plus 16 compact confirmation/management combinations.
    yield _variant("none", Decimal("0"), None, Decimal("0"))
    yield _variant("none", Decimal("0"), Decimal("0.75"), Decimal("0.25"))
    for mode, margin, management in itertools.product(
        ("close", "green", "low", "low_green"),
        (Decimal("0"), Decimal("0.25")),
        ("none", "v4"),
    ):
        be_trigger = Decimal("0.75") if management == "v4" else None
        lock_r = Decimal("0.25") if management == "v4" else Decimal("0")
        yield _variant(mode, margin, be_trigger, lock_r)


def _waiting(previous, current, reason):
    source = current if current is not None else previous
    return source.model_copy(
        update={
            "state": "lower_high_break",
            "reason_code": reason,
            "signal": None,
            "transitions": tuple(list(source.transitions) + ["breakout_hold_wait"]),
        }
    )


def _confirmation_evaluate(candidate, bars, config=None):
    variant = _ACTIVE_CONFIRMATION
    current_result = _BASE_V2_EVALUATE(candidate, bars, config)
    if variant is None or variant.confirmation_mode == "none":
        return current_result

    # A breakout on the current finalized bar starts the hold requirement; it
    # cannot itself authorize a trade.
    if len(bars) < 2:
        if current_result.signal is not None:
            return _waiting(current_result, current_result, "WAITING_FOR_BREAKOUT_HOLD")
        return current_result

    previous_result = _BASE_V2_EVALUATE(candidate, bars[:-1], config)
    if previous_result.signal is None:
        if current_result.signal is not None:
            return _waiting(current_result, current_result, "WAITING_FOR_BREAKOUT_HOLD")
        return current_result

    regular = _v2._regular_bars(list(bars))
    if not regular:
        return current_result
    bar = regular[-1]
    breakout_level = previous_result.features.b1
    previous_signal = previous_result.signal
    if breakout_level is None or previous_signal is None or breakout_level <= 0:
        return _waiting(previous_result, current_result, "BREAKOUT_HOLD_REFERENCE_MISSING")

    # The setup is invalidated before entry if the hold bar trades through the
    # original selloff-low stop. This is observable only after that bar closes.
    if bar.low <= previous_signal.stop_price:
        return _waiting(previous_result, current_result, "BREAKOUT_HOLD_INVALIDATED")

    vwap = session_vwap(regular)
    margin = variant.hold_close_margin_pct / Decimal("100")
    required_close = breakout_level * (Decimal("1") + margin)
    if vwap is None or bar.close <= vwap or bar.close <= required_close:
        return _waiting(previous_result, current_result, "WAITING_FOR_BREAKOUT_HOLD")

    mode = variant.confirmation_mode
    if mode in {"green", "low_green"} and bar.close <= bar.open:
        return _waiting(previous_result, current_result, "WAITING_FOR_GREEN_HOLD")
    if mode in {"low", "low_green"}:
        # Strong acceptance: the entire finalized hold bar must remain above the
        # broken level. Margin applies to close only, not the low.
        if bar.low < breakout_level:
            return _waiting(previous_result, current_result, "WAITING_FOR_BREAKOUT_LOW_HOLD")

    entry = bar.close
    stop = previous_signal.stop_price
    risk = entry - stop
    if risk <= 0:
        return _waiting(previous_result, current_result, "NON_POSITIVE_CONFIRMED_RISK")
    active = config
    reward = active.reward_multiple if active is not None else Decimal("1.5")
    signal = StrategySignal(
        instrument_id=candidate.instrument_id,
        state="entry_ready",
        entry_price=entry,
        stop_price=stop,
        target_price=entry + risk * reward,
        risk_per_share=risk,
        reason_code="FAILED_SELLOFF_BREAKOUT_HELD",
        quality_score=previous_signal.quality_score,
    )
    return previous_result.model_copy(
        update={
            "state": "entry_ready",
            "reason_code": "FAILED_SELLOFF_BREAKOUT_HELD",
            "signal": signal,
            "evaluated_bar_count": len(regular),
            "transitions": tuple(list(previous_result.transitions) + ["breakout_hold_confirmed", "entry_ready"]),
        }
    )


def _run_variant(variant, datasets, *, initial_cash, spread):
    global _ACTIVE_CONFIRMATION
    _ACTIVE_CONFIRMATION = variant
    _v4._ACTIVE_MANAGEMENT = variant
    return _v4._BASE_RUN_VARIANT(
        variant,
        datasets,
        initial_cash=initial_cash,
        spread=spread,
        max_hold_minutes=variant.max_hold_minutes,
    )


def _expectancy(row):
    return Decimal(str(row["expectancy_r"])) if row.get("expectancy_r") is not None else Decimal("-999")


def _worst_trade(row):
    trades = row.get("trades") or []
    return min((Decimal(str(t["r_multiple"])) for t in trades), default=Decimal("-999"))


def _rank_key(bundle):
    blocks = bundle["blocks"]
    exps = [_expectancy(block) for block in blocks]
    counts = [int(block["trade_count"]) for block in blocks]
    total = bundle["full"]
    total_exp = _expectancy(total)
    positive_blocks = sum(1 for exp in exps if exp > 0)
    min_exp = min(exps)
    return (
        1 if positive_blocks == 3 and all(count >= 1 for count in counts) and int(total["trade_count"]) >= 8 else 0,
        positive_blocks,
        min_exp,
        total_exp,
        min(counts),
        _worst_trade(total),
        Decimal(str(total["pnl"])),
    )


def parse_args():
    p = argparse.ArgumentParser(description="Run V5 three-block failed-selloff confirmation research.")
    p.add_argument("--start-date", default="2026-07-24")
    p.add_argument("--end-date", default="2026-08-21")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--output-dir", default="artifacts/failed-selloff-v5-confirmation")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="40")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    _bt.evaluate_gap_pullback = _confirmation_evaluate
    _bt._find_trade = _v4._managed_find_trade

    dates = _trading_dates(date.fromisoformat(args.start_date), date.fromisoformat(args.end_date))
    if len(dates) != 21:
        raise ValueError(f"V5 expects exactly 21 development sessions, got {len(dates)}")
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)
    namespace, _ = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    cache = Path(args.dataset_cache_dir) / namespace
    datasets = []
    for session_date in dates:
        path = _dataset_cache_path(cache, session_date)
        if not path.exists():
            raise FileNotFoundError(f"missing development dataset: {path}")
        datasets.append(_load_cached_dataset(path, session_date))
    blocks = [datasets[0:7], datasets[7:14], datasets[14:21]]

    variants = list(_grid())
    rows = []
    for variant in variants:
        block_results = [
            _run_variant(variant, block, initial_cash=initial_cash, spread=spread)
            for block in blocks
        ]
        full = _run_variant(variant, datasets, initial_cash=initial_cash, spread=spread)
        rows.append({
            "variant_id": variant.variant_id,
            "parameters": {
                "confirmation_mode": variant.confirmation_mode,
                "hold_close_margin_pct": str(variant.hold_close_margin_pct),
                "breakeven_trigger_r": None if variant.breakeven_trigger_r is None else str(variant.breakeven_trigger_r),
                "protected_stop_r": str(variant.protected_stop_r),
                "max_hold_minutes": variant.max_hold_minutes,
            },
            "blocks": block_results,
            "full": full,
        })

    ranked = sorted(rows, key=_rank_key, reverse=True)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(rows, indent=2, default=str) + "\n", encoding="utf-8")
    (output / "ranked.json").write_text(json.dumps(ranked, indent=2, default=str) + "\n", encoding="utf-8")

    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "rank", "variant_id", "block1_trades", "block1_exp_r", "block1_pnl",
            "block2_trades", "block2_exp_r", "block2_pnl", "block3_trades",
            "block3_exp_r", "block3_pnl", "full_trades", "full_exp_r", "full_pnl", "worst_trade_r",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, bundle in enumerate(ranked, 1):
            b1, b2, b3 = bundle["blocks"]
            full = bundle["full"]
            writer.writerow({
                "rank": rank,
                "variant_id": bundle["variant_id"],
                "block1_trades": b1["trade_count"], "block1_exp_r": b1["expectancy_r"], "block1_pnl": b1["pnl"],
                "block2_trades": b2["trade_count"], "block2_exp_r": b2["expectancy_r"], "block2_pnl": b2["pnl"],
                "block3_trades": b3["trade_count"], "block3_exp_r": b3["expectancy_r"], "block3_pnl": b3["pnl"],
                "full_trades": full["trade_count"], "full_exp_r": full["expectancy_r"], "full_pnl": full["pnl"],
                "worst_trade_r": str(_worst_trade(full)),
            })

    lines = [
        "# Failed-selloff V5 three-block confirmation",
        "",
        "Development-only research. The rejected June/July V4 validation block is not used here.",
        "",
        f"- Block 1: {blocks[0][0].session_date} through {blocks[0][-1].session_date}",
        f"- Block 2: {blocks[1][0].session_date} through {blocks[1][-1].session_date}",
        f"- Block 3: {blocks[2][0].session_date} through {blocks[2][-1].session_date}",
        f"- Variants: {len(variants)}",
        "- Ranking prioritizes all-three-block positive expectancy, then weakest-block expectancy, then aggregate expectancy.",
        "- Confirmation uses only finalized bars; no intrabar high/low ordering is assumed.",
        "",
        "| Rank | Variant | B1 trades / expR | B2 trades / expR | B3 trades / expR | Full trades / expR | Full P&L | Worst R |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, bundle in enumerate(ranked[:17], 1):
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
        if all(exp > 0 for exp in exps) and all(int(block["trade_count"]) >= 1 for block in bundle["blocks"]) and int(bundle["full"]["trade_count"]) >= 8:
            candidate = bundle
            break
    lines.extend(["", "## V5 conclusion", ""])
    if candidate is None:
        lines.append("No confirmation variant is positive across all three development blocks. Do not consume a new external validation block; continue development research instead.")
    else:
        lines.extend([
            f"Preliminary cross-regime candidate: `{candidate['variant_id']}`.",
            f"Full development: {candidate['full']['trade_count']} trades, {candidate['full']['expectancy_r']}R expectancy, P&L {candidate['full']['pnl']}.",
            "Freeze this configuration before using any new external validation block.",
        ])
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((output / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
