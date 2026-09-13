from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .gapper_dataset import GapperCandidate, freeze_gapper_universe
from .strategy_dynamic_discovery import CandidateLifecycleState, EvaluationTier, INTERDAY_TRADING_STRATEGY_ID
from .strategy_dynamic_discovery_repository import DynamicDiscoveryEventRepository, EVENT_DISCOVERY
from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .strategy_universe_archiver import _archive_universe_id


_ET = ZoneInfo("America/New_York")


def _is_interday_group(config: TradingStrategyConfigDocument) -> bool:
    return config.strategy_id == INTERDAY_TRADING_STRATEGY_ID or config.parent_strategy_id == INTERDAY_TRADING_STRATEGY_ID


def _dynamic_shadow_union(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    frozen,
    *,
    session_date: date,
    observed_at: datetime | None = None,
):
    """Append causally discovered Tier A/B candidates for SHADOW evaluation only.

    The persisted frozen archive is never mutated.  Existing frozen members retain
    their original morning evidence, which keeps the benchmark arm reproducible.
    New symbols use the exact point-in-time GapperCandidate payload captured by the
    discovery source.  AUTO PAPER never reaches this helper.
    """

    if frozen is None or config.mode != "shadow" or not _is_interday_group(config):
        return frozen
    event_repo = DynamicDiscoveryEventRepository(repository)
    try:
        latest = event_repo.latest_candidates(session_date)
        events = event_repo.session_events(session_date)
    except Exception:
        return frozen
    eligible_ids = {
        instrument_id
        for instrument_id, candidate in latest.items()
        if candidate.lifecycle != CandidateLifecycleState.EXPIRED
        and candidate.tier in {EvaluationTier.A, EvaluationTier.B}
    }
    if not eligible_ids:
        return frozen

    latest_source: dict[str, tuple[datetime, GapperCandidate]] = {}
    for event in events:
        if event.event_type != EVENT_DISCOVERY or event.instrument_id not in eligible_ids:
            continue
        raw = event.payload.get("payload")
        if not isinstance(raw, dict):
            continue
        candidate_payload = raw.get("candidate")
        if not isinstance(candidate_payload, dict):
            continue
        try:
            candidate = GapperCandidate.model_validate(candidate_payload)
        except Exception:
            continue
        current = latest_source.get(event.instrument_id)
        if current is None or event.observed_at > current[0]:
            latest_source[event.instrument_id] = (event.observed_at, candidate)

    existing = {candidate.instrument_id for candidate in frozen.candidates}
    additions = [
        candidate
        for instrument_id, (_, candidate) in latest_source.items()
        if instrument_id not in existing
    ]
    if not additions:
        return frozen
    evaluation_time = observed_at or max(
        [frozen.evaluation_time, *(candidate.observed_at for candidate in additions if candidate.observed_at is not None)]
    )
    if evaluation_time.tzinfo is None:
        raise ValueError("dynamic shadow union evaluation time must be timezone-aware")
    return freeze_gapper_universe(
        universe_id=f"{frozen.universe_id}-live-shadow-{evaluation_time.astimezone(timezone.utc).strftime('%H%M%S')}",
        session_date=session_date,
        evaluation_time=evaluation_time,
        discovery_source="import",
        source_locator="omnix:interday-dynamic-discovery-v2",
        candidates=[*frozen.candidates, *additions],
    )


def resolve_v2_evidence_archive_for_session(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    session_date: date,
):
    """Return the immutable strategy-owned V2 raw archive for qualification evidence.

    This resolver is deliberately read-only and independent of ``active_universe_id``.
    It may be used while V2 is in SHADOW or AUTO PAPER so post-session evidence keeps
    accumulating after promotion. It never attaches the archive to the strategy and
    therefore cannot grant order authority.
    """

    if config.mode not in {"shadow", "auto_paper"} or config.config.strategy_version != "2.0.0":
        return None

    marker = datetime.combine(session_date, config.config.universe_scan_time_et, tzinfo=_ET)
    universe_id = _archive_universe_id(config, marker)
    try:
        snapshot = repository.get_universe(universe_id)
    except ValueError as exc:
        if str(exc) == "gapper_universe_not_found":
            return None
        raise
    if snapshot.session_date != session_date:
        return None
    return snapshot


def resolve_v2_shadow_archive_for_session(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    session_date: date,
):
    """Return frozen + live discovery candidates only for V2 SHADOW evaluation."""

    if config.mode != "shadow" or config.active_universe_id is not None:
        return None
    frozen = resolve_v2_evidence_archive_for_session(
        config,
        repository,
        session_date=session_date,
    )
    return _dynamic_shadow_union(config, repository, frozen, session_date=session_date)


def resolve_v2_runtime_archive(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
):
    """Return today's runtime archive without broadening AUTO PAPER authority.

    SHADOW interday strategies receive the frozen benchmark plus causally admitted
    live Tier A/B candidates. AUTO PAPER receives only the immutable frozen archive
    that was used for qualification.
    """

    if config.active_universe_id is not None:
        return None
    if config.mode not in {"shadow", "auto_paper"}:
        return None
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("runtime archive clock must be timezone-aware")
    session_date = observed.astimezone(_ET).date()
    frozen = resolve_v2_evidence_archive_for_session(
        config,
        repository,
        session_date=session_date,
    )
    if config.mode == "shadow":
        return _dynamic_shadow_union(
            config,
            repository,
            frozen,
            session_date=session_date,
            observed_at=observed,
        )
    return frozen


def resolve_stoch_rsi_5m_runtime_archive(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
):
    """Return frozen + live discovery candidates for shadow-only Stoch RSI."""

    if (
        config.strategy_kind != "stoch_rsi_5m_v1"
        or config.mode != "shadow"
        or config.active_universe_id is not None
    ):
        return None
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("stoch-rsi-5min archive clock must be timezone-aware")
    session_date = observed.astimezone(_ET).date()
    marker = datetime.combine(session_date, config.config.universe_scan_time_et, tzinfo=_ET)
    universe_id = _archive_universe_id(config, marker)
    try:
        frozen = repository.get_universe(universe_id)
    except ValueError as exc:
        if str(exc) == "gapper_universe_not_found":
            return None
        raise
    if frozen.session_date != session_date:
        return None
    return _dynamic_shadow_union(
        config,
        repository,
        frozen,
        session_date=session_date,
        observed_at=observed,
    )


def resolve_v2_shadow_archive(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
):
    """Return today's frozen + causally discovered universe for V2 SHADOW."""

    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("shadow archive clock must be timezone-aware")
    session_date = observed.astimezone(_ET).date()
    frozen = resolve_v2_evidence_archive_for_session(config, repository, session_date=session_date)
    return _dynamic_shadow_union(
        config,
        repository,
        frozen,
        session_date=session_date,
        observed_at=observed,
    )


__all__ = [
    "resolve_v2_evidence_archive_for_session",
    "resolve_v2_runtime_archive",
    "resolve_v2_shadow_archive",
    "resolve_v2_shadow_archive_for_session",
    "resolve_stoch_rsi_5m_runtime_archive",
]
