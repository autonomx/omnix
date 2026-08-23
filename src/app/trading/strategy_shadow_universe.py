from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .strategy_universe_archiver import _archive_universe_id


_ET = ZoneInfo("America/New_York")


def resolve_v2_shadow_archive_for_session(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    session_date: date,
):
    """Return one raw strategy-owned V2 SHADOW archive by session date.

    This is a read-only evidence lookup. It never attaches a universe to the
    strategy and is intentionally unavailable to AUTO PAPER, non-V2 strategies,
    or SHADOW configs that already carry an explicit active universe.
    """

    if (
        config.mode != "shadow"
        or config.config.strategy_version != "2.0.0"
        or config.active_universe_id is not None
    ):
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


__all__ = ["resolve_v2_shadow_archive", "resolve_v2_shadow_archive_for_session"]
