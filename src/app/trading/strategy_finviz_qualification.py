from __future__ import annotations

"""Separate prospective AUTO PAPER qualification for the frozen Finviz V2 cohort.

The Finviz learning experiment has a different execution-profile fingerprint
from the canonical Yahoo-backed V2 profile. This module owns separate promotion
evidence and review events so Yahoo evidence can never authorize Finviz.
"""

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from .strategy_repository import StrategyEvent, TradingStrategyConfigDocument
from .strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint


FINVIZ_V2_PROSPECTIVE_START = date(2026, 8, 31)
FINVIZ_V2_MIN_MATCHED_TRADES = 20
FINVIZ_V2_MIN_DISTINCT_SESSIONS = 15
FINVIZ_V2_MIN_DISTINCT_SYMBOLS = 10
FINVIZ_V2_MIN_EXECUTION_MATCH_RATE = Decimal("0.90")
FINVIZ_V2_MIN_EXPECTANCY_R = Decimal("0.20")
FINVIZ_V2_MAX_DRAWDOWN_R = Decimal("5")
FINVIZ_V2_ONE_SIDED_90_Z = Decimal("1.2815515655446004")
FINVIZ_V2_LIVE_MATCH_WINDOW_MINUTES = 10
FINVIZ_V2_QUALIFICATION_VERSION = "finviz-v2-prospective-qualification-1"
FINVIZ_V2_REPLAY_VERSION = "finviz-v2-shadow-replay-1"

FINVIZ_V2_QUALIFICATION_EVENT_TYPES = (
    "shadow_execution",
    "finviz_v2_shadow_replay_trade",
    "finviz_v2_shadow_replay_session",
    "finviz_v2_promotion_review",
)


class FinvizV2QualificationThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)

    prospective_start: date = FINVIZ_V2_PROSPECTIVE_START
    minimum_matched_trades: int = FINVIZ_V2_MIN_MATCHED_TRADES
    minimum_distinct_sessions: int = FINVIZ_V2_MIN_DISTINCT_SESSIONS
    minimum_distinct_symbols: int = FINVIZ_V2_MIN_DISTINCT_SYMBOLS
    minimum_execution_match_rate: Decimal = FINVIZ_V2_MIN_EXECUTION_MATCH_RATE
    minimum_expectancy_r: Decimal = FINVIZ_V2_MIN_EXPECTANCY_R
    one_sided_confidence_level: Decimal = Decimal("0.90")
    maximum_drawdown_r: Decimal = FINVIZ_V2_MAX_DRAWDOWN_R
    live_match_window_minutes: int = FINVIZ_V2_LIVE_MATCH_WINDOW_MINUTES


class FinvizV2ProspectiveQualification(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    qualification_version: str = FINVIZ_V2_QUALIFICATION_VERSION
    prospective_start: date = FINVIZ_V2_PROSPECTIVE_START
    expected_profile_fingerprint: str
    current_profile_fingerprint: str
    profile_match: bool
    replay_trade_count: int = Field(ge=0)
    matched_eligible_trade_count: int = Field(ge=0)
    distinct_sessions: int = Field(ge=0)
    distinct_symbols: int = Field(ge=0)
    execution_match_rate: Decimal | None = None
    expectancy_r: Decimal | None = None
    one_sided_90_lcb_r: Decimal | None = None
    max_drawdown_r: Decimal | None = None
    thresholds: FinvizV2QualificationThresholds = Field(
        default_factory=FinvizV2QualificationThresholds
    )
    evidence_fingerprint: str
    qualified: bool = False
    reviewed: bool = False
    auto_paper_authorized: bool = False
    reason_codes: tuple[str, ...] = ()


def frozen_finviz_v2_config():
    """Return the exact frozen Finviz V2 execution profile."""

    return frozen_v2_config().model_copy(
        update={
            "universe_discovery_source": "finviz",
            "intraday_learning_enabled": True,
            "intraday_llm_enabled": True,
            "intraday_llm_top_n": 5,
            "intraday_llm_interval_minutes": 10,
        }
    )


FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT = v2_profile_fingerprint(
    frozen_finviz_v2_config()
)


def is_frozen_finviz_v2_profile(strategy: TradingStrategyConfigDocument) -> bool:
    return (
        strategy.strategy_version == "2.0.0"
        and strategy.config.strategy_version == "2.0.0"
        and strategy.config.universe_discovery_source == "finviz"
        and v2_profile_fingerprint(strategy.config)
        == FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT
    )


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _session_date(event: StrategyEvent) -> date | None:
    raw = event.payload.get("session_date")
    if raw:
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            return None
    return event.observed_at.date()


def _entry_time(event: StrategyEvent) -> datetime | None:
    raw = event.payload.get("entry_time")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _is_finviz_replay(event: StrategyEvent, expected_profile: str) -> bool:
    if event.event_type != "finviz_v2_shadow_replay_trade":
        return False
    if event.payload.get("qualification_version") != FINVIZ_V2_QUALIFICATION_VERSION:
        return False
    if event.payload.get("replay_version") != FINVIZ_V2_REPLAY_VERSION:
        return False
    if event.payload.get("profile_fingerprint") != expected_profile:
        return False
    if event.payload.get("universe_source") != "auto_archive_shadow":
        return False
    if event.payload.get("discovery_source") != "finviz":
        return False
    session = _session_date(event)
    return (
        session is not None
        and session >= FINVIZ_V2_PROSPECTIVE_START
        and _decimal(event.payload.get("r_result")) is not None
    )


def _is_eligible_live_shadow(event: StrategyEvent, expected_profile: str) -> bool:
    execution = event.payload.get("execution")
    execution_dict = execution if isinstance(execution, dict) else {}
    return (
        event.event_type == "shadow_execution"
        and event.reason_code == "SHADOW_EXECUTION_OBSERVED"
        and event.payload.get("execution_authority") is False
        and event.payload.get("universe_source") == "auto_archive_shadow"
        and event.payload.get("profile_fingerprint") == expected_profile
        and execution_dict.get("execution_eligible") is True
        and event.observed_at.date() >= FINVIZ_V2_PROSPECTIVE_START
    )


def _matches_live(replay: StrategyEvent, live: StrategyEvent) -> bool:
    if replay.instrument_id != live.instrument_id:
        return False
    if _session_date(replay) != _session_date(live):
        return False
    entry = _entry_time(replay)
    if entry is None:
        return False
    delta_minutes = abs(
        Decimal(str((entry - live.observed_at).total_seconds())) / Decimal("60")
    )
    return delta_minutes <= Decimal(FINVIZ_V2_LIVE_MATCH_WINDOW_MINUTES)


def _sample_stdev(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(
        ((value - mean) ** 2 for value in values), Decimal("0")
    ) / Decimal(len(values) - 1)
    return Decimal(str(math.sqrt(float(variance))))


def _one_sided_90_lcb(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    stdev = _sample_stdev(values)
    if stdev is None:
        return None
    standard_error = stdev / Decimal(str(math.sqrt(len(values))))
    return mean - FINVIZ_V2_ONE_SIDED_90_Z * standard_error


def _max_drawdown_r(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    equity = Decimal("0")
    peak = Decimal("0")
    maximum = Decimal("0")
    for value in values:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def _evidence_fingerprint(
    *,
    strategy_id: str,
    profile_fingerprint: str,
    replay_events: list[StrategyEvent],
    matched_events: list[StrategyEvent],
    expectancy_r: Decimal | None,
    lcb_r: Decimal | None,
    max_drawdown_r: Decimal | None,
) -> str:
    payload = {
        "qualification_version": FINVIZ_V2_QUALIFICATION_VERSION,
        "strategy_id": strategy_id,
        "profile_fingerprint": profile_fingerprint,
        "prospective_start": FINVIZ_V2_PROSPECTIVE_START.isoformat(),
        "replay_event_ids": [event.event_id for event in replay_events],
        "matched_replay_event_ids": [event.event_id for event in matched_events],
        "expectancy_r": str(expectancy_r) if expectancy_r is not None else None,
        "one_sided_90_lcb_r": str(lcb_r) if lcb_r is not None else None,
        "max_drawdown_r": str(max_drawdown_r) if max_drawdown_r is not None else None,
        "thresholds": FinvizV2QualificationThresholds().model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_finviz_v2_prospective_qualification(
    strategy: TradingStrategyConfigDocument,
    events: Iterable[StrategyEvent],
) -> FinvizV2ProspectiveQualification:
    current_profile = v2_profile_fingerprint(strategy.config)
    expected_profile = FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT
    ordered = sorted(events, key=lambda item: (item.observed_at, item.event_id))
    replay_events = [
        event for event in ordered if _is_finviz_replay(event, expected_profile)
    ]
    live_events = [
        event for event in ordered if _is_eligible_live_shadow(event, expected_profile)
    ]

    matched: list[StrategyEvent] = []
    used_live: set[str] = set()
    for replay in replay_events:
        candidate = next(
            (
                live
                for live in live_events
                if live.event_id not in used_live and _matches_live(replay, live)
            ),
            None,
        )
        if candidate is not None:
            used_live.add(candidate.event_id)
            matched.append(replay)

    r_values = [
        value
        for value in (_decimal(event.payload.get("r_result")) for event in matched)
        if value is not None
    ]
    expectancy = (
        sum(r_values, Decimal("0")) / Decimal(len(r_values)) if r_values else None
    )
    lcb = _one_sided_90_lcb(r_values)
    drawdown = _max_drawdown_r(r_values)
    replay_count = len(replay_events)
    match_rate = (
        Decimal(len(matched)) / Decimal(replay_count) if replay_count else None
    )
    sessions = {_session_date(event) for event in matched}
    sessions.discard(None)
    symbols = {event.instrument_id for event in matched}

    evidence_fingerprint = _evidence_fingerprint(
        strategy_id=strategy.strategy_id,
        profile_fingerprint=current_profile,
        replay_events=replay_events,
        matched_events=matched,
        expectancy_r=expectancy,
        lcb_r=lcb,
        max_drawdown_r=drawdown,
    )

    reasons: list[str] = []
    profile_match = is_frozen_finviz_v2_profile(strategy)
    if not profile_match:
        reasons.append("FINVIZ_V2_PROFILE_MISMATCH")
    if len(matched) < FINVIZ_V2_MIN_MATCHED_TRADES:
        reasons.append("FINVIZ_V2_MATCHED_TRADES_LOW")
    if len(sessions) < FINVIZ_V2_MIN_DISTINCT_SESSIONS:
        reasons.append("FINVIZ_V2_DISTINCT_SESSIONS_LOW")
    if len(symbols) < FINVIZ_V2_MIN_DISTINCT_SYMBOLS:
        reasons.append("FINVIZ_V2_DISTINCT_SYMBOLS_LOW")
    if match_rate is None or match_rate < FINVIZ_V2_MIN_EXECUTION_MATCH_RATE:
        reasons.append("FINVIZ_V2_EXECUTION_MATCH_RATE_LOW")
    if expectancy is None or expectancy < FINVIZ_V2_MIN_EXPECTANCY_R:
        reasons.append("FINVIZ_V2_EXPECTANCY_LOW")
    if lcb is None or lcb <= 0:
        reasons.append("FINVIZ_V2_EXPECTANCY_LCB_NOT_POSITIVE")
    if drawdown is None or drawdown > FINVIZ_V2_MAX_DRAWDOWN_R:
        reasons.append("FINVIZ_V2_DRAWDOWN_TOO_HIGH")

    qualified = not reasons
    reviewed = any(
        event.event_type == "finviz_v2_promotion_review"
        and event.payload.get("qualification_version")
        == FINVIZ_V2_QUALIFICATION_VERSION
        and event.payload.get("profile_fingerprint") == current_profile
        and event.payload.get("evidence_fingerprint") == evidence_fingerprint
        and event.payload.get("approved") is True
        and event.payload.get("execution_authority") is False
        for event in ordered
    )
    if qualified and not reviewed:
        reasons.append("FINVIZ_V2_OPERATOR_REVIEW_REQUIRED")

    return FinvizV2ProspectiveQualification(
        strategy_id=strategy.strategy_id,
        expected_profile_fingerprint=expected_profile,
        current_profile_fingerprint=current_profile,
        profile_match=profile_match,
        replay_trade_count=replay_count,
        matched_eligible_trade_count=len(matched),
        distinct_sessions=len(sessions),
        distinct_symbols=len(symbols),
        execution_match_rate=match_rate,
        expectancy_r=expectancy,
        one_sided_90_lcb_r=lcb,
        max_drawdown_r=drawdown,
        evidence_fingerprint=evidence_fingerprint,
        qualified=qualified,
        reviewed=reviewed,
        auto_paper_authorized=qualified and reviewed,
        reason_codes=tuple(reasons),
    )


__all__ = [
    "FINVIZ_V2_PROSPECTIVE_START",
    "FINVIZ_V2_QUALIFICATION_EVENT_TYPES",
    "FINVIZ_V2_QUALIFICATION_VERSION",
    "FINVIZ_V2_REPLAY_VERSION",
    "FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT",
    "FinvizV2ProspectiveQualification",
    "evaluate_finviz_v2_prospective_qualification",
    "frozen_finviz_v2_config",
    "is_frozen_finviz_v2_profile",
]
