from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .strategy_universe_archiver import _archive_universe_id


_ET = ZoneInfo("America/New_York")


def resolve_v2_shadow_archive(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
):
    """Return today's raw strategy-owned archive for prospective V2 SHADOW.

    The resolver is read-only. It does not attach the universe to the strategy and
    therefore cannot turn archival evidence into execution authority. AUTO PAPER,
    non-V2 strategies, and SHADOW configs with an explicit active universe do not
    use this fallback.
    """

    if (
        config.mode != "shadow"
        or config.config.strategy_version != "2.0.0"
        or config.active_universe_id is not None
    ):
        return None

    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("shadow archive clock must be timezone-aware")
    now_et = observed.astimezone(_ET)
    universe_id = _archive_universe_id(config, now_et)
    try:
        snapshot = repository.get_universe(universe_id)
    except ValueError as exc:
        if str(exc) == "gapper_universe_not_found":
            return None
        raise
    if snapshot.session_date != now_et.date():
        return None
    return snapshot


__all__ = ["resolve_v2_shadow_archive"]
