from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .catalyst_discovery import discover_yahoo_catalyst_headlines
from .catalyst_repository import TradingCatalystRepository
from .gapper_dataset import GapperUniverseSnapshot, freeze_gapper_universe
from .finviz_gapper_discovery import (
    FINVIZ_ATOMIC_SOURCE_LOCATOR,
    discover_finviz_gappers,
)
from .gapper_discovery import discover_yahoo_gappers
from .providers.errors import ProviderDataUnavailableError
from .strategy_data_integrity import assess_universe_integrity
from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .trade_logging import trade_log
from .us_equity_calendar import regular_holidays


_ET = ZoneInfo("America/New_York")


def _archive_universe_id(config: TradingStrategyConfigDocument, now_et: datetime) -> str:
    digest = hashlib.sha256(config.strategy_id.encode("utf-8")).hexdigest()[:10]
    return (
        f"auto-archive-{now_et.date().isoformat()}-"
        f"{config.config.universe_scan_time_et.strftime('%H%M')}-"
        f"{config.config.universe_discovery_source}-{digest}"
    )


def _enrich_finviz_catalysts(
    snapshot: GapperUniverseSnapshot,
    repository: TradingStrategyRepository,
    *,
    catalyst_repository: TradingCatalystRepository | None = None,
    catalyst_discovery: Callable[..., tuple] = discover_yahoo_catalyst_headlines,
) -> tuple[GapperUniverseSnapshot, int, dict[str, str]]:
    """Attach current Yahoo headline evidence before the immutable archive is saved."""

    if snapshot.discovery_source != "finviz" or not snapshot.candidates:
        return snapshot, 0, {}

    active_repository = catalyst_repository
    if active_repository is None:
        context = getattr(repository, "context", None)
        if context is None:
            # Lightweight in-memory repositories used by tests may not expose a
            # tenant context. Production repositories always do.
            return snapshot, 0, {}
        active_repository = TradingCatalystRepository(
            context=context,
            uow_factory=getattr(repository, "uow_factory"),
        )

    enriched = []
    evidence_count = 0
    errors: dict[str, str] = {}
    for candidate in snapshot.candidates:
        symbol = candidate.instrument_id.split(":")[-1]
        captured_at = datetime.now(timezone.utc)
        try:
            evidence = catalyst_discovery(
                instrument_id=candidate.instrument_id,
                symbol=symbol,
                evaluation_time=captured_at,
                lookback_hours=72,
                max_items=5,
            )
        except Exception as exc:
            errors[candidate.instrument_id] = f"{type(exc).__name__}: {exc}"
            evidence = ()

        persisted_evidence = []
        for item in evidence:
            try:
                active_repository.save_evidence(item)
            except Exception as exc:
                # Catalyst enrichment is research evidence, not execution authority.
                # A duplicate/transient evidence write must never erase the already
                # captured Finviz cohort or prevent deterministic monitoring.
                detail = f"{type(exc).__name__}: {exc}"
                previous = errors.get(candidate.instrument_id)
                errors[candidate.instrument_id] = (
                    f"{previous}; evidence_save={detail}"
                    if previous
                    else f"evidence_save={detail}"
                )
                continue
            persisted_evidence.append(item)

        evidence_count += len(persisted_evidence)
        evidence_ids = tuple(
            dict.fromkeys(
                (
                    *candidate.catalyst_evidence_ids,
                    *(item.evidence_id for item in persisted_evidence),
                )
            )
        )
        dilution_flags = tuple(
            sorted(
                set(candidate.dilution_flags).union(
                    *(set(item.dilution_flags) for item in persisted_evidence)
                )
            )
        )
        evidence_times = dict(candidate.evidence_observed_at)
        for item in persisted_evidence:
            evidence_times[f"catalyst:{item.evidence_id}"] = item.captured_at
        enriched.append(
            candidate.model_copy(
                update={
                    "catalyst_evidence_ids": evidence_ids,
                    "dilution_flags": dilution_flags,
                    "evidence_observed_at": evidence_times,
                }
            )
        )

    freeze_time = datetime.now(timezone.utc)
    return (
        freeze_gapper_universe(
            universe_id=snapshot.universe_id,
            session_date=snapshot.session_date,
            evaluation_time=freeze_time,
            discovery_source="finviz",
            source_locator=snapshot.source_locator,
            source_candidate_symbols=snapshot.source_candidate_symbols,
            candidates=enriched,
            allow_empty=not enriched,
        ),
        evidence_count,
        errors,
    )


def archive_daily_universe_if_due(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
    catalyst_repository: TradingCatalystRepository | None = None,
    catalyst_discovery: Callable[..., tuple] = discover_yahoo_catalyst_headlines,
) -> GapperUniverseSnapshot | None:
    """Create one configured point-in-time morning archive when due, otherwise return ``None``.

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

    discovery_source = config.config.universe_discovery_source
    discover = discover_finviz_gappers if discovery_source == "finviz" else discover_yahoo_gappers
    try:
        snapshot = discover(
            universe_id=universe_id,
            evaluation_time=observed.astimezone(timezone.utc),
            count=config.config.universe_discovery_count,
            minimum_gap_pct=config.config.minimum_gap_pct,
            minimum_price=config.config.minimum_price,
            maximum_price=config.config.maximum_price,
        )
    except ProviderDataUnavailableError as exc:
        if discovery_source == "finviz":
            raise
        if "no qualifying listed equities" not in str(exc).lower():
            raise
        snapshot = freeze_gapper_universe(
            universe_id=universe_id,
            session_date=now_et.date(),
            evaluation_time=observed.astimezone(timezone.utc),
            discovery_source="finviz" if discovery_source == "finviz" else "provider",
            source_locator=FINVIZ_ATOMIC_SOURCE_LOCATOR if discovery_source == "finviz" else None,
            candidates=[],
            allow_empty=True,
        )

    catalyst_evidence_count = 0
    catalyst_errors: dict[str, str] = {}
    if discovery_source == "finviz":
        snapshot, catalyst_evidence_count, catalyst_errors = _enrich_finviz_catalysts(
            snapshot,
            repository,
            catalyst_repository=catalyst_repository,
            catalyst_discovery=catalyst_discovery,
        )

    integrity = assess_universe_integrity(snapshot)
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
        source_candidate_count=len(saved.source_candidate_symbols),
        catalyst_evidence_count=catalyst_evidence_count,
        catalyst_capture_errors=catalyst_errors,
        capture_on_time=integrity.capture_on_time,
        cohort_complete=integrity.cohort_complete,
        cohort_integrity=integrity.cohort_integrity,
        market_data_complete=integrity.market_data_complete,
        prospective_eligible=integrity.prospective_eligible,
        integrity_reason_codes=integrity.reason_codes,
        configured_scan_time_et=config.config.universe_scan_time_et,
        configured_discovery_source=config.config.universe_discovery_source,
        configured_discovery_count=config.config.universe_discovery_count,
        grace_minutes=config.config.universe_archive_grace_minutes,
        execution_authority=False,
    )
    return saved


__all__ = ["archive_daily_universe_if_due"]
