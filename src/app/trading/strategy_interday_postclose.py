from __future__ import annotations

"""Post-close outcome labeling and evidence-only qualification for interday discovery."""

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from .strategy_dynamic_discovery import (
    DynamicCandidate,
    ShadowQualificationEvidence,
    TrendDurabilityOutcome,
    evaluate_shadow_qualification,
    trend_durability_from_prices,
)
from .strategy_dynamic_discovery_learning import DiscoveryDailyReport
from .strategy_dynamic_discovery_repository import (
    EVENT_DAILY_REPORT,
    EVENT_REPLAY,
    DynamicDiscoveryEventRepository,
)
from .strategy_repository import StrategyEvent, TradingStrategyRepository

_ET = ZoneInfo("America/New_York")
EVENT_OUTCOME = "interday_discovery_outcome"


def _event_id(*values: object) -> str:
    return hashlib.sha256("|".join(str(value) for value in values).encode("utf-8")).hexdigest()[:32]


def _session_bounds(session_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, time(0, 0), tzinfo=_ET).astimezone(timezone.utc)
    end = (datetime.combine(session_date, time(0, 0), tzinfo=_ET) + timedelta(days=1)).astimezone(timezone.utc)
    return start, end


def _regular_session_bars(response, *, session_date: date, observed_at: datetime):
    cutoff = observed_at.astimezone(timezone.utc)
    return sorted(
        [
            bar
            for bar in list(getattr(response, "bars", ()) or ())
            if bool(getattr(bar, "is_final", False))
            and getattr(bar, "session", None) == "regular"
            and bar.end_time.astimezone(timezone.utc) <= cutoff
            and bar.start_time.astimezone(_ET).date() == session_date
        ],
        key=lambda bar: bar.end_time,
    )


def label_candidate_outcome(
    market_service,
    candidate: DynamicCandidate,
    *,
    observed_at: datetime,
) -> TrendDurabilityOutcome | None:
    """Label one candidate using only its same-session finalized price path.

    The reference is the latest finalized close already knowable at discovery.
    For pre-open discoveries, where no regular close yet exists, the regular-open
    price is used. This is post-close labeling only and has no execution authority.
    """

    response = market_service.bars(candidate.instrument_id, "1m", 500, None)
    bars = _regular_session_bars(
        response,
        session_date=candidate.session_date,
        observed_at=observed_at,
    )
    if not bars:
        return None

    discovered = candidate.discovered_at.astimezone(timezone.utc)
    causal_reference = [bar for bar in bars if bar.end_time.astimezone(timezone.utc) <= discovered]
    if causal_reference:
        reference_price = float(causal_reference[-1].close)
        reference_time = causal_reference[-1].end_time.astimezone(timezone.utc)
    else:
        first = bars[0]
        reference_price = float(first.open)
        reference_time = first.start_time.astimezone(timezone.utc)

    if reference_price <= 0:
        return None
    samples = [
        (bar.end_time.astimezone(timezone.utc), float(bar.close))
        for bar in bars
        if bar.end_time.astimezone(timezone.utc) >= reference_time
    ]
    if not samples:
        return None
    return trend_durability_from_prices(
        candidate.instrument_id,
        discovered_at=reference_time,
        reference_price=reference_price,
        samples=samples,
    )


def persist_candidate_outcome(
    repository: TradingStrategyRepository,
    outcome: TrendDurabilityOutcome,
    *,
    session_date: date,
    observed_at: datetime,
) -> bool:
    event_id = _event_id(EVENT_OUTCOME, session_date, outcome.instrument_id)
    return repository.append_event(
        StrategyEvent(
            strategy_id="interday-trading-strategy-shadow",
            event_id=event_id,
            run_id=f"interday-discovery:{session_date.isoformat()}",
            instrument_id=outcome.instrument_id,
            event_type=EVENT_OUTCOME,
            state="labeled",
            reason_code=None,
            observed_at=observed_at,
            idempotency_key=f"{EVENT_OUTCOME}:{session_date.isoformat()}:{outcome.instrument_id}",
            payload=outcome.model_dump(mode="json"),
        )
    )


def session_outcomes(
    repository: TradingStrategyRepository,
    *,
    session_date: date,
) -> tuple[TrendDurabilityOutcome, ...]:
    start, end = _session_bounds(session_date)
    rows = repository.events_by_types_between(
        "interday-trading-strategy-shadow",
        event_types=(EVENT_OUTCOME,),
        start_time=start,
        end_time=end,
        limit=10_000,
    )
    values: list[TrendDurabilityOutcome] = []
    for row in rows:
        try:
            values.append(TrendDurabilityOutcome.model_validate(row.payload))
        except Exception:
            continue
    return tuple(values)


def _historical_parent_events(repository: TradingStrategyRepository) -> list[StrategyEvent]:
    if not hasattr(repository, "recent_events"):
        return []
    try:
        return list(repository.recent_events("interday-trading-strategy-shadow", 50_000))
    except Exception:
        return []


def qualification_from_persisted_evidence(
    repository: TradingStrategyRepository,
    *,
    current_report: DiscoveryDailyReport | None = None,
    data_reliability_fraction: float = 1.0,
    causality_violations: int = 0,
) -> ShadowQualificationEvidence:
    """Build a review gate from durable reports/replays without self-promotion.

    Recall/precision are aggregated only from replay rows that actually contain
    labeled metrics. Execution-adjusted expectancy and drawdown are intentionally
    left unavailable until a dedicated execution-economics dataset supplies them;
    therefore this evidence cannot become eligible merely from price-path labels.
    """

    reports: dict[date, DiscoveryDailyReport] = {}
    replays: list[dict[str, object]] = []
    for event in _historical_parent_events(repository):
        if event.event_type == EVENT_DAILY_REPORT:
            try:
                report = DiscoveryDailyReport.model_validate(event.payload)
            except Exception:
                continue
            reports[report.session_date] = report
        elif event.event_type == EVENT_REPLAY and isinstance(event.payload, dict):
            if event.payload.get("discovery_recall") is not None and event.payload.get("discovery_precision") is not None:
                replays.append(dict(event.payload))
    if current_report is not None:
        reports[current_report.session_date] = current_report

    true_positive = 0
    positive_labels = 0
    discovered_labeled = 0
    latencies: list[float] = []
    for replay in replays:
        discovered_count = int(replay.get("discovered_symbol_count", 0) or 0)
        false_positive = replay.get("false_positive_symbols") or ()
        missed = replay.get("missed_opportunity_symbols") or ()
        fp_count = len(false_positive) if isinstance(false_positive, (list, tuple)) else 0
        missed_count = len(missed) if isinstance(missed, (list, tuple)) else 0
        tp = max(0, discovered_count - fp_count)
        true_positive += tp
        positive_labels += tp + missed_count
        discovered_labeled += discovered_count
        latency = replay.get("median_discovery_latency_minutes")
        if latency is not None:
            try:
                latencies.append(float(latency))
            except (TypeError, ValueError):
                pass

    recall = true_positive / positive_labels if positive_labels else 0.0
    precision = true_positive / discovered_labeled if discovered_labeled else 0.0
    median_latency = median(latencies) if latencies else None
    labeled = max(positive_labels, sum(report.durability_labeled_count for report in reports.values()))

    return evaluate_shadow_qualification(
        {
            "independent_sessions": len(reports),
            "labeled_opportunities": labeled,
            "discovery_recall": recall,
            "discovery_precision": precision,
            "median_discovery_latency_minutes": median_latency,
            # Do not substitute raw price-path returns for execution-adjusted
            # expectancy or portfolio drawdown. Their absence keeps promotion
            # gated until the proper economics evidence is wired.
            "execution_adjusted_expectancy_r": None,
            "max_drawdown_r": None,
            "data_reliability_fraction": data_reliability_fraction,
            "causality_violations": causality_violations,
        }
    )


__all__ = [
    "EVENT_OUTCOME",
    "label_candidate_outcome",
    "persist_candidate_outcome",
    "qualification_from_persisted_evidence",
    "session_outcomes",
]
