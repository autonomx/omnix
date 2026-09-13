from __future__ import annotations

"""Narrow correctness refinements for the completed causal-discovery stack.

Installed after ``strategy_dynamic_discovery_completeness`` so existing public
contracts remain stable while production/replay semantics are tightened.
"""

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from types import SimpleNamespace
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from . import strategy_dynamic_discovery as dd
from . import strategy_dynamic_discovery_completeness as base
from .strategy_repository import StrategyEvent, TradingStrategyRepository, default_strategy_repository

_ET = ZoneInfo("America/New_York")
_INSTALLED = False

_ORIGINAL_COMPLETE_RUN = base._run_dynamic_discovery_once_complete
_ORIGINAL_COMPLETE_REPLAY = base._replay_dynamic_discovery_complete
_ORIGINAL_APPLY_SCAN = base.apply_discovery_scan
_ORIGINAL_UNION = base._union_complete
_ORIGINAL_STRICT_QUALIFICATION = base._complete_evaluate_shadow_qualification
_ORIGINAL_COMPLETE_CHARACTERIZATION = base._complete_opportunity_characterization
_ORIGINAL_PERSIST_AUTOMATIC_REPLAY = base._persist_automatic_replay


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _apply_scan_refined(
    *,
    previous_state: Mapping[str, dd.DynamicCandidate],
    observations: Sequence[object],
    watermark: datetime,
    session_date: date,
    config: dd.DynamicDiscoveryConfig = dd.DEFAULT_DYNAMIC_DISCOVERY_CONFIG,
):
    """Preserve ``last_observed_at`` as causal evidence time, not scan time."""

    result = _ORIGINAL_APPLY_SCAN(
        previous_state=previous_state,
        observations=observations,
        watermark=watermark,
        session_date=session_date,
        config=config,
    )
    latest_by_symbol: dict[str, datetime] = {}
    for row in observations:
        if row.session_date != session_date or row.observed_at > _utc(watermark):
            continue
        current = latest_by_symbol.get(row.instrument_id)
        if current is None or row.observed_at > current:
            latest_by_symbol[row.instrument_id] = row.observed_at

    repaired = []
    for candidate in result.candidates:
        prior = previous_state.get(candidate.instrument_id)
        causal_times = [candidate.discovered_at]
        if prior is not None:
            causal_times.append(prior.last_observed_at)
        latest = latest_by_symbol.get(candidate.instrument_id)
        if latest is not None:
            causal_times.append(latest)
        repaired.append(
            candidate.model_copy(update={"last_observed_at": max(causal_times)})
        )
    return result.model_copy(update={"candidates": tuple(repaired)})


async def _run_dynamic_discovery_once_refined(
    *,
    now: datetime | None = None,
    repository: TradingStrategyRepository | None = None,
    observations=None,
):
    """Reject explicit future evidence before touching repository state."""

    if observations is not None and now is not None:
        watermark = _utc(now)
        for row in observations:
            if row.observed_at > watermark:
                raise ValueError("live_discovery_observation_cannot_be_future_dated")
    return await _ORIGINAL_COMPLETE_RUN(
        now=now,
        repository=repository,
        observations=observations,
    )


def _replay_dynamic_discovery_refined(
    *,
    session_date: date,
    observations,
    labels=(),
    config: dd.DynamicDiscoveryConfig = dd.DEFAULT_DYNAMIC_DISCOVERY_CONFIG,
):
    for row in observations:
        if row.observed_at.astimezone(_ET).date() != session_date:
            raise ValueError("replay_observation_outside_exchange_session")
    return _ORIGINAL_COMPLETE_REPLAY(
        session_date=session_date,
        observations=observations,
        labels=labels,
        config=config,
    )


def _legacy_qualification(metrics: Mapping[str, object]):
    sessions = int(metrics.get("independent_sessions", 0) or 0)
    opportunities = int(metrics.get("labeled_opportunities", 0) or 0)
    recall = _float(metrics.get("discovery_recall"))
    precision = _float(metrics.get("discovery_precision"))
    expectancy = metrics.get("execution_adjusted_expectancy_r")
    reliability = _float(metrics.get("data_reliability_fraction"))
    violations = int(metrics.get("causality_violations", 0) or 0)
    latency = metrics.get("median_discovery_latency_minutes")
    drawdown = metrics.get("max_drawdown_r")
    reasons: list[str] = []
    if sessions < 20:
        reasons.append("insufficient_independent_sessions")
    if opportunities < 100:
        reasons.append("insufficient_labeled_opportunities")
    if recall < 0.70:
        reasons.append("discovery_recall_below_gate")
    if precision < 0.10:
        reasons.append("discovery_precision_below_gate")
    if expectancy is None or _float(expectancy) <= 0:
        reasons.append("non_positive_execution_adjusted_expectancy")
    if reliability < 0.95:
        reasons.append("data_reliability_below_gate")
    if violations:
        reasons.append("causality_violations_present")
    return base.CompleteShadowQualificationEvidence(
        independent_sessions=sessions,
        labeled_opportunities=opportunities,
        discovery_recall=max(0.0, min(1.0, recall)),
        discovery_precision=max(0.0, min(1.0, precision)),
        median_discovery_latency_minutes=(
            _float(latency) if latency is not None else None
        ),
        execution_adjusted_expectancy_r=(
            _float(expectancy) if expectancy is not None else None
        ),
        max_drawdown_r=_float(drawdown) if drawdown is not None else None,
        data_reliability_fraction=max(0.0, min(1.0, reliability)),
        causality_violations=violations,
        eligible_for_review=not reasons,
        auto_paper_authorized=False,
        reasons=tuple(reasons),
        evidence_complete=False,
    )


def _qualification_refined(metrics: Mapping[str, object]):
    """Keep legacy research helper compatibility; production uses strong gates."""

    strong_keys = {
        "execution_sample_count",
        "holdout_session_count",
        "expectancy_lcb_r",
        "stressed_expectancy_r",
        "holdout_expectancy_r",
    }
    if not any(key in metrics for key in strong_keys):
        return _legacy_qualification(metrics)
    return _ORIGINAL_STRICT_QUALIFICATION(metrics)


def _normalized_catalyst(catalyst: object | None):
    positive = (
        "catalyst_strength",
        "expected_attention_duration",
        "intraday_persistence_class",
        "fundamental_materiality",
        "materiality_to_company_size",
        "event_certainty",
    )
    payload = {
        key: (
            getattr(catalyst, key, None)
            if catalyst is not None and getattr(catalyst, key, None) is not None
            else "none"
        )
        for key in positive
    }
    payload["supply_pressure"] = (
        getattr(catalyst, "supply_pressure", None)
        if catalyst is not None and getattr(catalyst, "supply_pressure", None) is not None
        else "unknown"
    )
    payload["promotional_risk"] = (
        getattr(catalyst, "promotional_risk", None)
        if catalyst is not None and getattr(catalyst, "promotional_risk", None) is not None
        else "unknown"
    )
    return SimpleNamespace(**payload)


def _characterization_refined(
    candidate: dd.DynamicCandidate,
    *,
    observed_at: datetime,
    catalyst: object | None = None,
    market_structure: object | None = None,
    execution_quality: float = 50.0,
    market_context: dd.MarketContext | None = None,
    relationships: Sequence[dd.RelationshipExposure] = (),
):
    """Unknown upside is zero; unknown supply/promo risk is neutral, never benign."""

    return _ORIGINAL_COMPLETE_CHARACTERIZATION(
        candidate,
        observed_at=observed_at,
        catalyst=_normalized_catalyst(catalyst),
        market_structure=market_structure,
        execution_quality=execution_quality,
        market_context=market_context,
        relationships=relationships,
    )


def _explicit_relationships(instrument_id: str, observed_at: datetime):
    try:
        from .research.repository import default_research_repository

        evidence = default_research_repository().list_evidence_as_of(
            instrument_id, observed_at, limit=200
        )
    except Exception:
        return ()
    rows = []
    for item in evidence:
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        relationship_type = metadata.get("relationship_type")
        subject = metadata.get("subject_entity") or metadata.get("related_entity")
        if not isinstance(relationship_type, str) or not relationship_type.strip():
            continue
        if not isinstance(subject, str) or not subject.strip():
            continue
        affected = metadata.get("affected_symbol") or instrument_id
        try:
            strength = max(
                0.0, min(1.0, float(metadata.get("relationship_strength", 0.5)))
            )
            exposure = max(
                0.0, min(1.0, float(metadata.get("economic_exposure", 0.5)))
            )
        except (TypeError, ValueError):
            continue
        known_at = item.omnix_known_at or item.captured_at
        rows.append(
            dd.RelationshipExposure(
                subject_entity=subject.strip(),
                affected_symbol=str(affected),
                relationship_type=relationship_type.strip(),
                relationship_strength=strength,
                economic_exposure=exposure,
                direction_of_effect=str(
                    metadata.get("direction_of_effect") or "unknown"
                ),
                observed_at=known_at,
                evidence_ids=(item.evidence_id,),
            )
        )
    return tuple(rows)


def _context_from_research(
    instrument_id: str,
    observed_at: datetime,
    market_service,
):
    base_context = base._market_context(market_service, observed_at)
    updates: dict[str, float] = {}
    try:
        from .research.repository import default_research_repository

        evidence = default_research_repository().list_evidence_as_of(
            instrument_id, observed_at, limit=100
        )
    except Exception:
        evidence = ()
    keys = (
        "sector_return_pct",
        "industry_return_pct",
        "peer_median_return_pct",
        "peer_positive_fraction",
        "market_breadth",
        "sector_news_strength",
    )
    for item in evidence:
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        for key in keys:
            if key in updates or metadata.get(key) is None:
                continue
            try:
                updates[key] = float(metadata[key])
            except (TypeError, ValueError):
                continue
    return base_context.model_copy(update=updates) if updates else base_context


def _build_characterization_refined(
    candidate: base.CompleteDynamicCandidate,
    *,
    observed_at: datetime,
    observation: object | None,
    market_service,
):
    catalyst = base._snapshot_object(candidate)
    structure = base._market_structure_for(
        candidate.instrument_id, market_service, observed_at
    )
    context = _context_from_research(
        candidate.instrument_id, observed_at, market_service
    )
    relationships = _explicit_relationships(
        candidate.instrument_id, observed_at
    )
    execution_quality = 50.0
    if (
        observation is not None
        and getattr(observation, "market", None) is not None
        and observation.market.spread_bps is not None
    ):
        execution_quality = max(
            0.0,
            min(100.0, 100.0 - float(observation.market.spread_bps) / 2.0),
        )
    return _characterization_refined(
        candidate,
        observed_at=observed_at,
        catalyst=catalyst,
        market_structure=structure,
        execution_quality=execution_quality,
        market_context=context,
        relationships=relationships,
    )


def _union_refined(
    config,
    repository,
    frozen,
    *,
    session_date,
    observed_at=None,
):
    """Support both new candidate snapshots and pre-completeness discovery rows."""

    result = _ORIGINAL_UNION(
        config,
        repository,
        frozen,
        session_date=session_date,
        observed_at=observed_at,
    )
    if (
        frozen is None
        or config.mode != "shadow"
        or not (
            config.strategy_id == dd.INTERDAY_TRADING_STRATEGY_ID
            or config.parent_strategy_id == dd.INTERDAY_TRADING_STRATEGY_ID
        )
    ):
        return result

    from .gapper_dataset import GapperCandidate, freeze_gapper_universe
    from .strategy_dynamic_discovery_repository import (
        DynamicDiscoveryEventRepository,
        EVENT_DISCOVERY,
    )

    try:
        event_repo = DynamicDiscoveryEventRepository(repository)
        latest = event_repo.latest_candidates(session_date)
        events = event_repo.session_events(session_date)
    except Exception:
        return result

    if config.strategy_id == dd.INTERDAY_TRADING_STRATEGY_ID:
        applicable = set(dd.INTERDAY_SUBSTRATEGIES[:4])
    else:
        applicable = {config.strategy_id}
    eligible = {
        symbol: base._current_candidate(candidate)
        for symbol, candidate in latest.items()
        if candidate.lifecycle != dd.CandidateLifecycleState.EXPIRED
        and (
            candidate.tier in {dd.EvaluationTier.A, dd.EvaluationTier.B}
            or bool(
                set(base._current_candidate(candidate).selected_for_strategies)
                & applicable
            )
        )
    }
    if not eligible:
        return result

    payload_by_symbol: dict[str, dict[str, object]] = {}
    for event in events:
        if event.event_type != EVENT_DISCOVERY or event.instrument_id not in eligible:
            continue
        nested = event.payload.get("payload")
        if not isinstance(nested, dict):
            continue
        raw = nested.get("candidate")
        if not isinstance(raw, dict):
            continue
        payload_by_symbol[event.instrument_id] = raw

    existing_universe = result or frozen
    existing = {row.instrument_id for row in existing_universe.candidates}
    additions = []
    for symbol, candidate in eligible.items():
        if symbol in existing:
            continue
        raw = candidate.latest_candidate_payload or payload_by_symbol.get(symbol)
        if not isinstance(raw, dict):
            continue
        try:
            additions.append(GapperCandidate.model_validate(raw))
        except Exception:
            continue
    if not additions:
        return result

    evaluation_time = observed_at or max(
        [
            existing_universe.evaluation_time,
            *[
                row.observed_at
                for row in additions
                if row.observed_at is not None
            ],
        ]
    )
    return freeze_gapper_universe(
        universe_id=(
            f"{frozen.universe_id}-live-shadow-"
            f"{evaluation_time.astimezone(timezone.utc).strftime('%H%M%S')}"
        ),
        session_date=session_date,
        evaluation_time=evaluation_time,
        discovery_source="import",
        source_locator="omnix:interday-dynamic-discovery-refined",
        candidates=[*existing_universe.candidates, *additions],
    )


def _build_replay_result(
    *,
    session_date: date,
    state: Mapping[str, dd.DynamicCandidate],
    events,
    labels,
    observations,
    fingerprint_payload,
):
    from .strategy_discovery_replay import DiscoveryReplayResult

    label_by_symbol = {row.instrument_id: row for row in labels}
    labeled_symbols = set(label_by_symbol)
    discovered = set(state)
    discovered_labeled = discovered & labeled_symbols
    positives = {
        symbol for symbol, label in label_by_symbol.items() if label.opportunity
    }
    true_positive = discovered_labeled & positives
    false_positive = discovered_labeled - positives
    missed = positives - discovered
    recall = len(true_positive) / len(positives) if positives else None
    precision = (
        len(true_positive) / len(discovered_labeled)
        if discovered_labeled
        else None
    )
    latencies = []
    for symbol in true_positive:
        actionable = label_by_symbol[symbol].first_actionable_at
        if actionable is None:
            continue
        latencies.append(
            max(
                0.0,
                (state[symbol].discovered_at - actionable).total_seconds()
                / 60.0,
            )
        )
    median_latency = None
    if latencies:
        ordered = sorted(latencies)
        middle = len(ordered) // 2
        median_latency = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2.0
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    finals = tuple(
        sorted(
            state.values(),
            key=lambda row: (-row.common_priority, row.instrument_id),
        )
    )
    return DiscoveryReplayResult(
        session_date=session_date,
        observation_count=len(observations),
        observable_symbol_count=len({row.instrument_id for row in observations}),
        discovered_symbol_count=len(discovered),
        first_discovered_at={
            symbol: candidate.discovered_at
            for symbol, candidate in sorted(state.items())
        },
        false_positive_symbols=tuple(sorted(false_positive)),
        missed_opportunity_symbols=tuple(sorted(missed)),
        discovery_recall=recall,
        discovery_precision=precision,
        median_discovery_latency_minutes=median_latency,
        fingerprint=fingerprint,
        final_candidates=finals,
        events=tuple(events),
    )


def _replay_captured_scans(
    stored,
    *,
    session_date: date,
    labels,
):
    groups: dict[datetime, list[object]] = defaultdict(list)
    for watermark_raw, observation in stored:
        if observation.observed_at.astimezone(_ET).date() != session_date:
            continue
        if isinstance(watermark_raw, datetime):
            watermark = _utc(watermark_raw)
        elif isinstance(watermark_raw, str) and watermark_raw:
            watermark = _utc(
                datetime.fromisoformat(watermark_raw.replace("Z", "+00:00"))
            )
        else:
            watermark = observation.observed_at
        groups[watermark].append(observation)

    state: dict[str, dd.DynamicCandidate] = {}
    events = []
    violations = []
    all_observations = []
    fingerprint_records = []
    for watermark in sorted(groups):
        batch = tuple(groups[watermark])
        scan = _apply_scan_refined(
            previous_state=state,
            observations=batch,
            watermark=watermark,
            session_date=session_date,
        )
        state = {row.instrument_id: row for row in scan.candidates}
        events.extend(scan.events)
        violations.extend(scan.violations)
        all_observations.extend(batch)
        fingerprint_records.append(
            {
                "watermark": watermark.isoformat(),
                "observations": [
                    row.model_dump(mode="json") for row in batch
                ],
            }
        )
    result = _build_replay_result(
        session_date=session_date,
        state=state,
        events=events,
        labels=labels,
        observations=tuple(all_observations),
        fingerprint_payload={"scans": fingerprint_records},
    )
    return result, tuple(violations)


def _persist_automatic_replay_refined(
    repository: TradingStrategyRepository,
    *,
    session_date: date,
    outcomes,
    observed_at: datetime,
):
    from .service import default_market_data_service
    from .strategy_discovery_replay import DiscoveryOpportunityLabel
    from .strategy_dynamic_discovery_repository import DynamicDiscoveryEventRepository

    stored = base._observations_for_session(repository, session_date=session_date)
    if not stored:
        return None
    observations = [observation for _, observation in stored]
    first_by_symbol: dict[str, object] = {}
    for observation in sorted(observations, key=lambda row: row.observed_at):
        first_by_symbol.setdefault(observation.instrument_id, observation)

    known_outcomes = {row.instrument_id: row for row in outcomes}
    market_service = default_market_data_service()
    label_by_symbol = {}
    for symbol, first in first_by_symbol.items():
        outcome = known_outcomes.get(symbol)
        if outcome is None:
            synthetic = base.CompleteDynamicCandidate(
                session_date=session_date,
                instrument_id=symbol,
                first_seen_at=first.observed_at,
                discovered_at=first.observed_at,
                last_observed_at=first.observed_at,
            )
            try:
                outcome = base._label_candidate_outcome_complete(
                    market_service,
                    synthetic,
                    observed_at=observed_at,
                )
            except Exception:
                outcome = None
        if outcome is None:
            continue
        actionable = getattr(outcome, "tradeable_reference_at", None) or outcome.discovered_at
        label_by_symbol[symbol] = DiscoveryOpportunityLabel(
            instrument_id=symbol,
            opportunity=outcome.plus_2r_before_minus_1r is True,
            first_actionable_at=actionable,
        )

    replay_result, violations = _replay_captured_scans(
        stored,
        session_date=session_date,
        labels=tuple(label_by_symbol.values()),
    )
    payload = replay_result.model_dump(mode="json")
    payload["causality_violation_count"] = len(violations)
    payload["labeled_symbol_count"] = len(label_by_symbol)
    DynamicDiscoveryEventRepository(repository).persist_replay(
        session_date=session_date,
        observed_at=observed_at,
        payload=payload,
    )
    return replay_result


def install_dynamic_discovery_completeness_refinements() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_discovery_replay as replay
    from . import strategy_dynamic_discovery_monitor as monitor
    from . import strategy_interday_learning_monitor as learning
    from . import strategy_interday_postclose as postclose
    from . import strategy_shadow_universe as universe

    base.apply_discovery_scan = _apply_scan_refined
    base._run_dynamic_discovery_once_complete = _run_dynamic_discovery_once_refined
    base._replay_dynamic_discovery_complete = _replay_dynamic_discovery_refined
    base._complete_evaluate_shadow_qualification = _qualification_refined
    base._complete_opportunity_characterization = _characterization_refined
    base._build_complete_characterization = _build_characterization_refined
    base._union_complete = _union_refined
    base._persist_automatic_replay = _persist_automatic_replay_refined

    dd.evaluate_shadow_qualification = _qualification_refined
    dd.build_opportunity_characterization = _characterization_refined

    monitor.run_dynamic_discovery_once = _run_dynamic_discovery_once_refined
    replay.replay_dynamic_discovery = _replay_dynamic_discovery_refined
    postclose.qualification_from_persisted_evidence = (
        base._qualification_from_persisted_evidence_complete
    )
    learning.qualification_from_persisted_evidence = (
        base._qualification_from_persisted_evidence_complete
    )
    learning.run_interday_learning_once = base._run_interday_learning_once_complete
    universe._dynamic_shadow_union = _union_refined

    _INSTALLED = True


__all__ = [
    "_apply_scan_refined",
    "_persist_automatic_replay_refined",
    "_replay_captured_scans",
    "install_dynamic_discovery_completeness_refinements",
]
