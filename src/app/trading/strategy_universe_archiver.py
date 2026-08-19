from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .gapper_dataset import GapperUniverseSnapshot, freeze_gapper_universe
from .gapper_discovery import discover_yahoo_gappers
from .providers.errors import ProviderDataUnavailableError
from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .trade_logging import trade_log
from .us_equity_calendar import regular_holidays


_ET = ZoneInfo("America/New_York")


def _archive_universe_id(config: TradingStrategyConfigDocument, now_et: datetime) -> str:
    digest = hashlib.sha256(config.strategy_id.encode("utf-8")).hexdigest()[:10]
    return (
        f"auto-archive-{now_et.date().isoformat()}-"
        f"{config.config.universe_scan_time_et.strftime('%H%M')}-{digest}"
    )


def archive_daily_universe_if_due(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
) -> GapperUniverseSnapshot | None:
    """Create one raw Yahoo morning archive when due, otherwise return ``None``.

    Archival is evidence-only: it never changes ``active_universe_id`` and cannot
    authorize a trade. A completed scan with zero qualifying names is stored as an
    empty immutable archive so later backtests can distinguish a real no-candidate
    day from a missing scan. Other provider failures remain failures.
    """

    if not config.enabled or not config.config.auto_archive_daily_universe:
        return None
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("strategy universe archive clock must be timezone-aware")
    now_et = observed.astimezone(_ET)
    if now_et.weekday() >= 5 or now_et.date() in regular_holidays(now_et.year):
        return None
    scan_start = datetime.combine(
        now_et.date(),
        config.config.universe_scan_time_et,
        tzinfo=_ET,
    )
    scan_end = scan_start + timedelta(minutes=config.config.universe_archive_grace_minutes)
    if not scan_start <= now_et <= scan_end:
        return None

    universe_id = _archive_universe_id(config, now_et)
    try:
        repository.get_universe(universe_id)
    except ValueError as exc:
        if str(exc) != "gapper_universe_not_found":
            raise
    else:
        return None

    try:
        snapshot = discover_yahoo_gappers(
            universe_id=universe_id,
            evaluation_time=observed.astimezone(timezone.utc),
            count=config.config.universe_discovery_count,
            minimum_gap_pct=config.config.minimum_gap_pct,
            minimum_price=config.config.minimum_price,
            maximum_price=config.config.maximum_price,
        )
    except ProviderDataUnavailableError as exc:
        if "no qualifying listed equities" not in str(exc).lower():
            raise
        snapshot = freeze_gapper_universe(
            universe_id=universe_id,
            session_date=now_et.date(),
            evaluation_time=observed.astimezone(timezone.utc),
            discovery_source="provider",
            candidates=[],
            allow_empty=True,
        )

    saved = repository.save_universe(snapshot)
    trade_log(
        "auto_trading",
        "daily_universe_archived",
        strategy_id=config.strategy_id,
        universe_id=saved.universe_id,
        session_date=saved.session_date,
        evaluation_time=saved.evaluation_time,
        source_fingerprint=saved.source_fingerprint,
        candidate_count=len(saved.candidates),
        zero_candidate_scan=len(saved.candidates) == 0,
        configured_scan_time_et=config.config.universe_scan_time_et,
        grace_minutes=config.config.universe_archive_grace_minutes,
        execution_authority=False,
    )
    return saved


__all__ = ["archive_daily_universe_if_due"]
