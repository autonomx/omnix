from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .strategy_universe_archiver import _archive_universe_id


_ET = ZoneInfo("America/New_York")


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
    """Return one raw strategy-owned archive only for the V2 SHADOW execution fallback.

    Unlike the qualification evidence resolver, this path remains unavailable to
    AUTO PAPER and to SHADOW configs with an explicitly selected universe.
    """

    if config.mode != "shadow" or config.active_universe_id is not None:
        return None
    return resolve_v2_evidence_archive_for_session(
        config,
        repository,
        session_date=session_date,
    )



def resolve_v2_runtime_archive(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
):
    """Return today's immutable strategy-owned archive for V2 runtime evaluation.

    SHADOW and already-promoted AUTO PAPER may both consume the same frozen
    morning archive when no explicit universe is attached. This lookup does not
    grant execution authority: AUTO PAPER must already be persisted on the
    strategy, and the monitor re-validates the V2 qualification fingerprint
    before it reaches this resolver.
    """

    if config.active_universe_id is not None:
        return None
    if config.mode not in {"shadow", "auto_paper"}:
        return None
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("runtime archive clock must be timezone-aware")
    return resolve_v2_evidence_archive_for_session(
        config,
        repository,
        session_date=observed.astimezone(_ET).date(),
    )

def resolve_v2_shadow_archive(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
):
    """Return today's raw strategy-owned archive for prospective V2 SHADOW."""

    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("shadow archive clock must be timezone-aware")
    return resolve_v2_shadow_archive_for_session(
        config,
        repository,
        session_date=observed.astimezone(_ET).date(),
    )


__all__ = [
    "resolve_v2_evidence_archive_for_session",
    "resolve_v2_runtime_archive",
    "resolve_v2_shadow_archive",
    "resolve_v2_shadow_archive_for_session",
]
