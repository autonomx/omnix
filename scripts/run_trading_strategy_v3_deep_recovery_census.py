from __future__ import annotations

"""Provider-free census of post-open deep recoveries in the immutable V3 development cache.

The primary outcome label is an absolute >=30% rebound from a post-opening running
low after a meaningful >=5% selloff from the first-15-minute opening high. The
script reports both 11:30-ET actionable recovery and full-session recovery, then
joins those labels to the unmodified frozen-V2 candidate decision.

This script is descriptive research only. It never loads March, never calls a
provider and never changes frozen V2 or execution authority.
"""

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from app.trading.models import MarketBar
from app.trading.paper import PaperExecutionPolicy
from app.trading.strategies.gap_pullback import _ET, _regular_bars
from app.trading.strategies.models import StrategyRiskProfile
from app.trading.strategy_backtest import run_gap_pullback_backtest
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block


_OPENING_END = time(9, 45)
_ACTIONABLE_END = time(11, 30)
_MINIMUM_SELLOFF_PCT = Decimal("5")
_RECOVERY_THRESHOLD_PCT = Decimal("30")


@dataclass(frozen=True)
class RecoveryPath:
    opening_high: Decimal | None = None
    opening_high_at: str | None = None
    trough: Decimal | None = None
    trough_at: str | None = None
    peak: Decimal | None = None
    peak_at: str | None = None
    selloff_pct: Decimal | None = None
    absolute_recovery_pct: Decimal | None = None
    selloff_retracement_pct: Decimal | None = None

    @property
    def qualifies_30(self) -> bool:
        return (
            self.absolute_recovery_pct is not None
            and self.absolute_recovery_pct >= _RECOVERY_THRESHOLD_PCT
        )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Census >=30% recoveries across every cached development candidate.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2025-10-01")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--output-dir", default="artifacts/v3-deep-recovery-census")
    return parser.parse_args()


def _iso_end(bar: MarketBar) -> str:
    return bar.end_time.isoformat()


def _eligible_regular(bars: Iterable[MarketBar], *, actionable_only: bool) -> list[MarketBar]:
    regular = _regular_bars(list(bars))
    if actionable_only:
        return [bar for bar in regular if bar.end_time.astimezone(_ET).time() <= _ACTIONABLE_END]
    return regular


def recovery_path(
    bars: Iterable[MarketBar],
    *,
    actionable_only: bool,
) -> RecoveryPath:
    """Return the best sequence opening high -> later low -> later high.

    A new low is not paired with the same 1-minute bar's high because OHLC does
    not reveal intra-bar ordering. The earliest recovery from a newly established
    trough is therefore the next finalized bar, which is deliberately conservative.
    """

    regular = _eligible_regular(bars, actionable_only=actionable_only)
    if not regular:
        return RecoveryPath()
    opening = [bar for bar in regular if bar.start_time.astimezone(_ET).time() < _OPENING_END]
    if not opening:
        return RecoveryPath()
    opening_high = max(bar.high for bar in opening)
    opening_index = next(index for index, bar in enumerate(regular) if bar.high == opening_high)
    opening_bar = regular[opening_index]
    if opening_index + 1 >= len(regular):
        return RecoveryPath(opening_high=opening_high, opening_high_at=_iso_end(opening_bar))

    running_low: Decimal | None = None
    running_low_at: str | None = None
    best_recovery: Decimal | None = None
    best_low: Decimal | None = None
    best_low_at: str | None = None
    best_peak: Decimal | None = None
    best_peak_at: str | None = None

    for bar in regular[opening_index + 1 :]:
        # Evaluate the current high only against a trough known before this bar.
        if running_low is not None and running_low > 0:
            selloff = (opening_high - running_low) / opening_high * Decimal("100")
            if selloff >= _MINIMUM_SELLOFF_PCT:
                recovery = (bar.high / running_low - Decimal("1")) * Decimal("100")
                if best_recovery is None or recovery > best_recovery:
                    best_recovery = recovery
                    best_low = running_low
                    best_low_at = running_low_at
                    best_peak = bar.high
                    best_peak_at = _iso_end(bar)
        if running_low is None or bar.low < running_low:
            running_low = bar.low
            running_low_at = _iso_end(bar)

    if best_recovery is None or best_low is None or best_peak is None:
        return RecoveryPath(opening_high=opening_high, opening_high_at=_iso_end(opening_bar))
    selloff_pct = (opening_high - best_low) / opening_high * Decimal("100")
    selloff_denominator = opening_high - best_low
    retracement = (
        (best_peak - best_low) / selloff_denominator * Decimal("100")
        if selloff_denominator > 0
        else None
    )
    return RecoveryPath(
        opening_high=opening_high,
        opening_high_at=_iso_end(opening_bar),
        trough=best_low,
        trough_at=best_low_at,
        peak=best_peak,
        peak_at=best_peak_at,
        selloff_pct=selloff_pct,
        absolute_recovery_pct=best_recovery,
        selloff_retracement_pct=retracement,
    )


def _value(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _path_columns(prefix: str, path: RecoveryPath) -> dict[str, object]:
    return {
        f"{prefix}_opening_high": _value(path.opening_high),
        f"{prefix}_opening_high_at": path.opening_high_at,
        f"{prefix}_trough": _value(path.trough),
        f"{prefix}_trough_at": path.trough_at,
        f"{prefix}_peak": _value(path.peak),
        f"{prefix}_peak_at": path.peak_at,
        f"{prefix}_selloff_pct": _value(path.selloff_pct),
        f"{prefix}_absolute_recovery_pct": _value(path.absolute_recovery_pct),
        f"{prefix}_selloff_retracement_pct": _value(path.selloff_retracement_pct),
        f"{prefix}_qualifies_30": path.qualifies_30,
    }


def _decision_bucket(row: dict[str, object]) -> str:
    if bool(row["v2_selected_trade"]):
        return "TRADED"
    if bool(row["v2_triggered"]):
        reason = str(row.get("v2_rejection_reason") or "NOT_SELECTED_AFTER_TRIGGER")
        return f"TRIGGERED:{reason}"
    reason = str(row.get("v2_rejection_reason") or row.get("v2_state") or "UNKNOWN")
    return reason


def _counter_dict(rows: list[dict[str, object]]) -> dict[str, int]:
    return dict(sorted(Counter(_decision_bucket(row) for row in rows).items(), key=lambda item: (-item[1], item[0])))


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal("2")


def _recovery_stats(rows: list[dict[str, object]], field: str) -> dict[str, object]:
    values = [Decimal(str(row[field])) for row in rows if row.get(field) not in {None, ""}]
    return {
        "count": len(values),
        "median_pct": _value(_median(values)),
        "maximum_pct": _value(max(values)) if values else None,
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


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
    policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    risk = StrategyRiskProfile()
    current_cash = initial_cash
    rows: list[dict[str, object]] = []
    session_fingerprints: dict[str, str] = {}

    for dataset in datasets:
        session_fingerprints[dataset.session_date.isoformat()] = dataset.dataset_fingerprint
        result = run_gap_pullback_backtest(
            dataset,
            config=config,
            execution_policy=policy,
            assumed_spread_bps=spread,
            max_hold_minutes=config.v2_max_hold_minutes,
            max_concurrent_positions=risk.max_positions,
            risk_profile=risk,
            initial_cash=current_cash,
        )
        decisions = {decision.instrument_id: decision for decision in result.candidate_decisions}
        for candidate in dataset.universe.candidates:
            bars = dataset.bars_by_instrument[candidate.instrument_id]
            actionable = recovery_path(bars, actionable_only=True)
            full = recovery_path(bars, actionable_only=False)
            decision = decisions.get(candidate.instrument_id)
            row: dict[str, object] = {
                "session_date": dataset.session_date.isoformat(),
                "instrument_id": candidate.instrument_id,
                "discovery_rank": candidate.discovery_rank,
                "gap_pct": _value(candidate.gap_pct),
                "premarket_price": _value(candidate.premarket_price),
                "premarket_dollar_volume": _value(candidate.premarket_dollar_volume),
                "tod_rvol": _value(candidate.tod_rvol),
                "spread_bps": _value(candidate.spread_bps),
                "v2_state": decision.state if decision is not None else "missing_decision",
                "v2_rejection_reason": decision.rejection_reason if decision is not None else "MISSING_DECISION",
                "v2_triggered": decision.triggered if decision is not None else False,
                "v2_selected_trade": decision.selected_trade if decision is not None else False,
            }
            row.update(_path_columns("actionable", actionable))
            row.update(_path_columns("full", full))
            row["full_session_only_30"] = full.qualifies_30 and not actionable.qualifies_30
            rows.append(row)
        session_pnl = sum(
            (trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades),
            Decimal("0"),
        )
        current_cash += session_pnl

    expected_candidates = int(coverage.get("candidate_count", len(rows)))
    if len(rows) != expected_candidates:
        # Older coverage payloads do not always carry candidate_count. Only fail
        # when the field is present and actually disagrees.
        if "candidate_count" in coverage:
            raise SystemExit(f"candidate census mismatch: rows={len(rows)} coverage={expected_candidates}")

    actionable_30 = [row for row in rows if bool(row["actionable_qualifies_30"])]
    full_30 = [row for row in rows if bool(row["full_qualifies_30"])]
    full_only_30 = [row for row in rows if bool(row["full_session_only_30"])]
    actionable_v2_missed = [row for row in actionable_30 if not bool(row["v2_triggered"])]
    actionable_v2_not_traded = [row for row in actionable_30 if not bool(row["v2_selected_trade"])]

    payload = {
        "purpose": "all_candidate_deep_recovery_census",
        "protocol_version": "deep-recovery-census-v1",
        "production_strategy_changed": False,
        "frozen_v2_changed": False,
        "march_holdout_loaded": False,
        "provider_calls": 0,
        "development_period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "candidate_rows": len(rows),
        "cache_namespace": namespace,
        "cache_basis": basis,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(config),
        "definition": {
            "opening_window_et": "09:30-09:45",
            "minimum_selloff_pct": str(_MINIMUM_SELLOFF_PCT),
            "absolute_recovery_threshold_pct": str(_RECOVERY_THRESHOLD_PCT),
            "actionable_cutoff_et": "11:30",
            "same_bar_low_high_pairing": False,
        },
        "counts": {
            "actionable_30": len(actionable_30),
            "full_session_30": len(full_30),
            "full_session_only_30": len(full_only_30),
            "actionable_30_v2_never_triggered": len(actionable_v2_missed),
            "actionable_30_v2_not_traded": len(actionable_v2_not_traded),
        },
        "rates": {
            "actionable_30_of_all_candidates": _value(Decimal(len(actionable_30)) / Decimal(len(rows))) if rows else None,
            "full_session_30_of_all_candidates": _value(Decimal(len(full_30)) / Decimal(len(rows))) if rows else None,
            "v2_trigger_capture_of_actionable_30": _value(Decimal(len(actionable_30) - len(actionable_v2_missed)) / Decimal(len(actionable_30))) if actionable_30 else None,
            "v2_trade_capture_of_actionable_30": _value(Decimal(len(actionable_30) - len(actionable_v2_not_traded)) / Decimal(len(actionable_30))) if actionable_30 else None,
        },
        "actionable_30_v2_attribution": _counter_dict(actionable_30),
        "full_session_only_30_v2_attribution": _counter_dict(full_only_30),
        "recovery_stats": {
            "actionable_all": _recovery_stats(rows, "actionable_absolute_recovery_pct"),
            "actionable_30": _recovery_stats(actionable_30, "actionable_absolute_recovery_pct"),
            "full_session_all": _recovery_stats(rows, "full_absolute_recovery_pct"),
            "full_session_30": _recovery_stats(full_30, "full_absolute_recovery_pct"),
        },
        "session_dataset_fingerprints": session_fingerprints,
        "warning": "Eventual recovery is an outcome label and cannot be used as earlier execution knowledge. Any successor rule formulated from this census is in-sample until independently validated.",
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / "candidate_recovery.csv", rows)
    _write_csv(out / "recovery_30_actionable.csv", actionable_30)
    _write_csv(out / "recovery_30_full_session.csv", full_30)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Deep-recovery candidate census",
        "",
        f"- Development: **{start} through {end}**",
        f"- Coverage: **{coverage['covered_sessions']}/{coverage['requested_sessions']} sessions**",
        f"- Candidate/day rows: **{len(rows)}**",
        "- Provider calls: **none**",
        "- March holdout loaded: **no**",
        "- Frozen V2 changed: **no**",
        "",
        "Recovery definition: first-15-minute opening high -> later >=5% selloff -> later trough-to-peak rebound. Same-bar low/high ordering is not assumed.",
        f"Primary threshold: **>={_RECOVERY_THRESHOLD_PCT}% absolute rebound from trough**.",
        "",
        f"- >=30% by 11:30 ET: **{len(actionable_30)}**",
        f"- >=30% at any regular-session time: **{len(full_30)}**",
        f"- >=30% only after 11:30 ET: **{len(full_only_30)}**",
        f"- >=30% by 11:30 that frozen V2 never structurally triggered: **{len(actionable_v2_missed)}**",
        f"- >=30% by 11:30 that frozen V2 did not trade: **{len(actionable_v2_not_traded)}**",
        "",
        "## Frozen V2 attribution for actionable >=30% recoveries",
        "",
    ]
    for reason, count in payload["actionable_30_v2_attribution"].items():
        lines.append(f"- `{reason}`: **{count}**")
    lines.extend([
        "",
        "## Frozen V2 attribution for >=30% recoveries occurring only after 11:30",
        "",
    ])
    for reason, count in payload["full_session_only_30_v2_attribution"].items():
        lines.append(f"- `{reason}`: **{count}**")
    lines.extend([
        "",
        "The CSV artifacts contain the complete candidate-level census and exact low/high sequence used for each recovery measurement.",
        "",
        "> This is outcome-side descriptive evidence. It does not grant execution authority and must not be converted into an earlier-time signal with hindsight.",
        "",
    ])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
