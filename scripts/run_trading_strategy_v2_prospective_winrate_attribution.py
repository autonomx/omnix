from __future__ import annotations

"""Analyze only captured Aug-24+ SHADOW feature/outcome pairs.

This script never calls a market/research provider and never proposes production
thresholds. It reports readiness plus winner/loser descriptive separation for
predeclared prospective feature families once enough matched outcomes exist.
"""

import argparse
import json
import math
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any, Callable

from app.trading.strategy_prospective_dataset import (
    ProspectiveSignalOutcomeRow,
    matched_prospective_signal_outcomes,
    prospective_dataset_readiness,
)
from app.trading.strategy_repository import default_strategy_repository
from app.trading.strategy_v2_qualification import V2_PROSPECTIVE_START


MIN_MATCHED_TRADES = 20
MIN_CLASS_TRADES = 5


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Describe prospective V2 winner/loser feature separation.")
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--output-dir", default="artifacts/v2-prospective-winrate-attribution")
    parser.add_argument("--event-limit", type=int, default=20000)
    return parser.parse_args()


def _number(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _nested(row: ProspectiveSignalOutcomeRow, *path: str) -> object:
    value: object = row.features
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _ratio_pct(value: object, denominator: object) -> Decimal | None:
    numerator = _number(value)
    base = _number(denominator)
    if numerator is None or base is None or base == 0:
        return None
    return numerator / base * Decimal("100")


def _bool_number(value: object) -> Decimal | None:
    if value is True:
        return Decimal("1")
    if value is False:
        return Decimal("0")
    return None


def _feature_extractors() -> dict[str, Callable[[ProspectiveSignalOutcomeRow], Decimal | None]]:
    return {
        "premarket_range_pct": lambda row: _number(_nested(row, "premarket", "range_pct")),
        "premarket_return_pct": lambda row: _number(_nested(row, "premarket", "return_pct")),
        "premarket_close_vs_vwap_pct": lambda row: _number(_nested(row, "premarket", "close_vs_vwap_pct")),
        "premarket_close_vs_high_pct": lambda row: _number(_nested(row, "premarket", "close_vs_high_pct")),
        "premarket_dollar_volume": lambda row: _number(_nested(row, "premarket", "dollar_volume")),
        "premarket_last_30m_return_pct": lambda row: _number(_nested(row, "premarket", "last_30m_return_pct")),
        "primary_catalyst_confirmed": lambda row: _bool_number(_nested(row, "research", "catalyst", "primary_confirmed")),
        "catalyst_same_day": lambda row: _bool_number(_nested(row, "research", "catalyst", "same_day")),
        "catalyst_primary_source_count": lambda row: _number(_nested(row, "research", "catalyst", "source_count_primary")),
        "catalyst_age_minutes": lambda row: _number(_nested(row, "research", "catalyst", "age_minutes")),
        "immediate_supply_risk": lambda row: _bool_number(_nested(row, "research", "supply", "immediate_supply_risk")),
        "potential_dilution_pct_float": lambda row: _number(_nested(row, "research", "supply", "potential_dilution_pct_float")),
        "remaining_atm_pct_market_cap": lambda row: _number(_nested(row, "research", "supply", "remaining_atm_pct_market_cap")),
        "itm_warrant_pct_float": lambda row: _number(_nested(row, "research", "supply", "in_the_money_warrant_pct_float")),
        "registered_resale_pct_float": lambda row: _number(_nested(row, "research", "supply", "registered_resale_pct_float")),
        "halt_event_count": lambda row: _number(_nested(row, "halt_history", "halt_event_count")),
        "halted_at_decision": lambda row: _bool_number(_nested(row, "halt_history", "halted_at_decision")),
        "one_minute_price_vs_ema9_pct": lambda row: (
            (_number(_nested(row, "momentum", "one_minute", "close")) / _number(_nested(row, "momentum", "one_minute", "ema9")) - Decimal("1")) * Decimal("100")
            if _number(_nested(row, "momentum", "one_minute", "close")) is not None
            and _number(_nested(row, "momentum", "one_minute", "ema9")) not in {None, Decimal("0")}
            else None
        ),
        "one_minute_macd_hist_pct_price": lambda row: _ratio_pct(
            _nested(row, "momentum", "one_minute", "macd_histogram"),
            _nested(row, "momentum", "one_minute", "close"),
        ),
        "one_minute_stoch_k": lambda row: _number(_nested(row, "momentum", "one_minute", "stochastic_rsi_k")),
        "five_minute_price_vs_ema9_pct": lambda row: (
            (_number(_nested(row, "momentum", "five_minute", "close")) / _number(_nested(row, "momentum", "five_minute", "ema9")) - Decimal("1")) * Decimal("100")
            if _number(_nested(row, "momentum", "five_minute", "close")) is not None
            and _number(_nested(row, "momentum", "five_minute", "ema9")) not in {None, Decimal("0")}
            else None
        ),
        "five_minute_macd_hist_pct_price": lambda row: _ratio_pct(
            _nested(row, "momentum", "five_minute", "macd_histogram"),
            _nested(row, "momentum", "five_minute", "close"),
        ),
        "five_minute_stoch_k": lambda row: _number(_nested(row, "momentum", "five_minute", "stochastic_rsi_k")),
    }


def _cliffs_delta(winners: list[Decimal], losers: list[Decimal]) -> Decimal | None:
    if not winners or not losers:
        return None
    greater = 0
    lower = 0
    for winner in winners:
        for loser in losers:
            if winner > loser:
                greater += 1
            elif winner < loser:
                lower += 1
    return Decimal(greater - lower) / Decimal(len(winners) * len(losers))


def _describe(rows: tuple[ProspectiveSignalOutcomeRow, ...]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for name, extractor in _feature_extractors().items():
        winners = [value for row in rows if row.won and (value := extractor(row)) is not None]
        losers = [value for row in rows if not row.won and (value := extractor(row)) is not None]
        delta = _cliffs_delta(winners, losers)
        output.append(
            {
                "feature": name,
                "winner_count": len(winners),
                "loser_count": len(losers),
                "winner_median": str(median(winners)) if winners else None,
                "loser_median": str(median(losers)) if losers else None,
                "cliffs_delta": str(delta) if delta is not None else None,
                "descriptively_usable": len(winners) >= MIN_CLASS_TRADES and len(losers) >= MIN_CLASS_TRADES,
            }
        )
    output.sort(
        key=lambda item: abs(float(item["cliffs_delta"])) if item["cliffs_delta"] is not None else -math.inf,
        reverse=True,
    )
    return output


def main() -> int:
    args = _args()
    repository = default_strategy_repository()
    start = datetime(V2_PROSPECTIVE_START.year, V2_PROSPECTIVE_START.month, V2_PROSPECTIVE_START.day, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    if hasattr(repository, "events_by_types_between"):
        events = repository.events_by_types_between(
            args.strategy_id,
            event_types=("shadow_execution", "v2_shadow_replay_trade"),
            start_time=start,
            end_time=end,
            limit=args.event_limit,
        )
    else:
        events = [
            event
            for event in repository.recent_events(args.strategy_id, args.event_limit)
            if event.event_type in {"shadow_execution", "v2_shadow_replay_trade"}
            and start <= event.observed_at.astimezone(timezone.utc) <= end
        ]
    rows = matched_prospective_signal_outcomes(events)
    readiness = prospective_dataset_readiness(rows)
    ready = (
        len(rows) >= MIN_MATCHED_TRADES
        and int(readiness["winner_count"]) >= MIN_CLASS_TRADES
        and int(readiness["loser_count"]) >= MIN_CLASS_TRADES
    )
    payload: dict[str, Any] = {
        "purpose": "prospective winner/loser attribution from captured SHADOW features only",
        "strategy_id": args.strategy_id,
        "prospective_start": V2_PROSPECTIVE_START.isoformat(),
        "generated_at": end.isoformat(),
        "provider_calls": 0,
        "execution_authority": False,
        "minimum_matched_trades_before_attribution": MIN_MATCHED_TRADES,
        "minimum_winners_and_losers_per_feature": MIN_CLASS_TRADES,
        "status": "ready_for_descriptive_attribution" if ready else "collecting_prospective_outcomes",
        "readiness": readiness,
        "feature_descriptions": _describe(rows) if ready else [],
        "rows": [row.model_dump(mode="json") for row in rows],
        "warning": "Descriptive separation is hypothesis generation only. Do not derive and promote thresholds from the same prospective sample without a later untouched validation block.",
    }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = [
        "# Prospective V2 win-rate attribution",
        "",
        f"- Status: **{payload['status']}**",
        f"- Matched trades: **{readiness['matched_trade_count']}**",
        f"- Winners / losers: **{readiness['winner_count']} / {readiness['loser_count']}**",
        f"- All-core feature rows: **{readiness['all_core_available_count']}**",
        f"- Distinct sessions / symbols: **{readiness['distinct_sessions']} / {readiness['distinct_symbols']}**",
        "- Provider calls: **none**",
        "- Execution authority: **none**",
        "",
    ]
    if not ready:
        summary.append("Continue collecting untouched prospective SHADOW outcomes; no winner/loser threshold attribution is emitted yet.")
    else:
        summary.append("Descriptive feature separation is available in results.json; reserve a later untouched block before any threshold proposal is considered authoritative.")
    text = "\n".join(summary) + "\n"
    (output / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
