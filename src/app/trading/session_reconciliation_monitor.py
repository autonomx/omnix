from __future__ import annotations

"""Automatic formal-session SIP reconciliation.

The monitor freezes the exact strategy/event/universe population after the
session, then retries only the authoritative consolidated-SIP evidence contract.
It never substitutes IEX, web quotes, adjusted daily bars, or partial prints.
"""

import asyncio
import os
from contextlib import suppress
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .feature_qualification import FeatureRequirement, qualify_bar_feature
from .providers.alpaca_sip import AlpacaSipResearchProvider
from .prospective_prediction_evidence import select_analysis_session_prices
from .prospective_prediction_scoring import build_formal_outcome_labels
from .session_evidence import (
    SessionEvidenceManifest,
    SessionEvidenceRepository,
    begin_reconciliation,
    build_session_evidence_manifest,
    default_session_evidence_repository,
    defer_reconciliation,
    finalize_reconciliation,
    permanently_unscorable,
    provider_evidence_input,
)
from .strategy_repository import (
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)
from .strategy_shadow_universe import resolve_v2_evidence_archive_for_session
from .trade_logging import trade_log


_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_trading_session_reconciliation_monitor"
_SESSION_CLOSE = time(16, 0)
_DEFAULT_CREATE_AFTER = time(16, 5)


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def session_reconciliation_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_SESSION_RECONCILIATION_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_SESSION_RECONCILIATION_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(
            os.environ.get(
                "OMNIX_TRADING_SESSION_RECONCILIATION_INTERVAL_SECONDS",
                "300",
            )
        )
    except ValueError:
        value = 300.0
    return max(60.0, value)


def _retry_minutes() -> int:
    try:
        value = int(
            os.environ.get(
                "OMNIX_TRADING_SESSION_RECONCILIATION_RETRY_MINUTES",
                "15",
            )
        )
    except ValueError:
        value = 15
    return max(5, value)


def _max_age_days() -> int:
    try:
        value = int(
            os.environ.get(
                "OMNIX_TRADING_SESSION_RECONCILIATION_MAX_AGE_DAYS",
                "7",
            )
        )
    except ValueError:
        value = 7
    return max(1, value)


def _session_bounds(session_date: date) -> tuple[datetime, datetime]:
    start_et = datetime.combine(session_date, time.min, tzinfo=_ET)
    end_et = start_et + timedelta(days=1)
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def _formal_close(session_date: date) -> datetime:
    return datetime.combine(
        session_date,
        _SESSION_CLOSE,
        tzinfo=_ET,
    ).astimezone(timezone.utc)


def _confirmed_nontrading_starts(
    bars,
    trades,
    *,
    session_date: date,
) -> tuple[datetime, ...]:
    session_start = datetime.combine(
        session_date,
        time(9, 30),
        tzinfo=_ET,
    ).astimezone(timezone.utc)
    session_end = _formal_close(session_date)
    bar_starts = {
        bar.start_time.astimezone(timezone.utc)
        for bar in bars
        if bar.is_final and bar.session == "regular"
    }
    trade_times = [
        trade.event_timestamp.astimezone(timezone.utc)
        for trade in trades
    ]
    confirmed: list[datetime] = []
    cursor = session_start
    step = timedelta(minutes=5)
    while cursor < session_end:
        if cursor not in bar_starts:
            has_trade = any(cursor <= value < cursor + step for value in trade_times)
            if not has_trade:
                confirmed.append(cursor)
        cursor += step
    return tuple(confirmed)


def _complete_sip_5m_certificate(
    bars,
    trades,
    *,
    instrument_id: str,
    session_date: date,
):
    confirmed_nontrading = _confirmed_nontrading_starts(
        bars,
        trades,
        session_date=session_date,
    )
    return qualify_bar_feature(
        bars,
        FeatureRequirement(
            requirement_id="formal-sip-5m-session-v1",
            feature_name="formal_sip_5m_session",
            interval="5m",
            dependency_class="EVENT_SEQUENCE",
            source_policy=("alpaca_sip",),
        ),
        instrument_id=instrument_id,
        session_date=session_date,
        observed_at=_formal_close(session_date) + timedelta(seconds=1),
        confirmed_nontrading_starts=confirmed_nontrading,
    )


def _serializable_outcome(
    *,
    prices,
    measurements,
    labels,
    coverage_certificate,
) -> dict[str, object]:
    return {
        "analysis_prices": prices.model_dump(mode="json"),
        "measurements": measurements.model_dump(mode="json"),
        "labels": labels.model_dump(mode="json"),
        "formal_bar_coverage": coverage_certificate.model_dump(mode="json"),
    }


class TradingSessionReconciliationMonitor:
    def __init__(
        self,
        *,
        strategy_repository_factory: Callable[[], TradingStrategyRepository] = default_strategy_repository,
        manifest_repository_factory: Callable[[], SessionEvidenceRepository] = default_session_evidence_repository,
        sip_provider_factory: Callable[[], AlpacaSipResearchProvider] = AlpacaSipResearchProvider,
        now_factory: Callable[[], datetime] | None = None,
        interval_seconds: float | None = None,
    ) -> None:
        self.strategy_repository_factory = strategy_repository_factory
        self.manifest_repository_factory = manifest_repository_factory
        self.sip_provider_factory = sip_provider_factory
        self.now_factory = now_factory or (lambda: datetime.now(timezone.utc))
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.manifest_create_count = 0
        self.attempt_count = 0
        self.final_count = 0
        self.deferred_count = 0
        self.permanently_unscorable_count = 0

    async def _events_for_session(
        self,
        repository: TradingStrategyRepository,
        strategy_id: str,
        session_date: date,
    ):
        start, end = _session_bounds(session_date)
        events = await asyncio.to_thread(
            repository.events_between,
            strategy_id,
            start_time=start,
            end_time=end,
            limit=100_000,
        )
        if len(events) >= 100_000:
            raise RuntimeError(
                f"session_event_population_limit_reached:{strategy_id}:{session_date}"
            )
        return events, start, end

    async def _create_current_manifests(
        self,
        repository: TradingStrategyRepository,
        manifests: SessionEvidenceRepository,
        *,
        now: datetime,
    ) -> int:
        now_et = now.astimezone(_ET)
        if now_et.time() < _DEFAULT_CREATE_AFTER:
            return 0
        session_date = now_et.date()
        configs = await asyncio.to_thread(repository.list_configs, active_only=True)
        created = 0
        for config in configs:
            if config.config.strategy_version != "2.0.0":
                continue
            universe = await asyncio.to_thread(
                resolve_v2_evidence_archive_for_session,
                config,
                repository,
                session_date=session_date,
            )
            if universe is None:
                continue
            existing = await asyncio.to_thread(
                manifests.get_for_session,
                config.strategy_id,
                session_date,
            )
            if existing is not None:
                continue
            try:
                events, start, end = await self._events_for_session(
                    repository,
                    config.strategy_id,
                    session_date,
                )
                manifest = build_session_evidence_manifest(
                    strategy_id=config.strategy_id,
                    session_date=session_date,
                    events=events,
                    universe=universe,
                    aggregation_start=start,
                    aggregation_end=end,
                    frozen_at=now,
                )
                await asyncio.to_thread(manifests.create, manifest)
            except Exception as exc:
                self.last_error = (
                    f"manifest/{config.strategy_id}: {type(exc).__name__}: {exc}"
                )
                trade_log(
                    "auto_trading",
                    "session_evidence_manifest_error",
                    strategy_id=config.strategy_id,
                    session_date=session_date.isoformat(),
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
                continue
            created += 1
            self.manifest_create_count += 1
        return created

    async def _reconcile_symbol(
        self,
        provider: AlpacaSipResearchProvider,
        *,
        instrument_id: str,
        session_date: date,
    ) -> tuple[dict[str, object], tuple[object, ...]]:
        trades = await asyncio.to_thread(
            provider.regular_session_trade_events,
            instrument_id,
            session_date,
        )
        bars = await asyncio.to_thread(
            provider.regular_session_5m_bars,
            instrument_id,
            session_date,
        )
        coverage = _complete_sip_5m_certificate(
            bars,
            trades,
            instrument_id=instrument_id,
            session_date=session_date,
        )
        if coverage.status != "VALID":
            raise ValueError(
                "formal_sip_5m_session_incomplete:"
                + ",".join(coverage.reason_codes)
            )
        prices = select_analysis_session_prices(
            trades,
            session_date=session_date,
            outcome_state="FINAL",
        )
        measurements, labels = build_formal_outcome_labels(
            prices=prices,
            bars=bars,
        )
        trade_input = provider_evidence_input(
            source_id=f"alpaca_sip:trades:{instrument_id}:{session_date}",
            payload=[item.model_dump(mode="json") for item in trades],
            record_count=len(trades),
            start_time=trades[0].event_timestamp if trades else None,
            end_time=trades[-1].event_timestamp if trades else None,
        )
        bar_input = provider_evidence_input(
            source_id=f"alpaca_sip:5m:{instrument_id}:{session_date}",
            payload=[item.model_dump(mode="json") for item in bars],
            record_count=len(bars),
            start_time=bars[0].start_time if bars else None,
            end_time=bars[-1].end_time if bars else None,
        )
        outcome = _serializable_outcome(
            prices=prices,
            measurements=measurements,
            labels=labels,
            coverage_certificate=coverage,
        )
        return outcome, (trade_input, bar_input)

    async def _attempt_manifest(
        self,
        repository: TradingStrategyRepository,
        manifests: SessionEvidenceRepository,
        manifest: SessionEvidenceManifest,
        *,
        now: datetime,
    ) -> None:
        started = begin_reconciliation(manifest, observed_at=now)
        started = await asyncio.to_thread(
            manifests.save_transition,
            manifest,
            started,
        )
        self.attempt_count += 1

        try:
            config = await asyncio.to_thread(
                repository.get_config,
                started.strategy_id,
            )
            universe = await asyncio.to_thread(
                resolve_v2_evidence_archive_for_session,
                config,
                repository,
                session_date=started.frozen_scope.session_date,
            )
            if universe is None:
                raise ValueError("frozen_session_universe_unavailable")

            frozen_universe_ids = set(started.frozen_scope.universe_ids)
            if universe.universe_id not in frozen_universe_ids:
                raise ValueError(
                    "reconciliation_universe_not_in_frozen_manifest:"
                    + str(universe.universe_id)
                )
            provider = self.sip_provider_factory()
            outcomes: dict[str, object] = {}
            evidence = []
            errors: dict[str, str] = {}
            for candidate in universe.candidates:
                try:
                    outcome, inputs = await self._reconcile_symbol(
                        provider,
                        instrument_id=candidate.instrument_id,
                        session_date=started.frozen_scope.session_date,
                    )
                    outcomes[candidate.instrument_id] = outcome
                    evidence.extend(inputs)
                except Exception as exc:
                    errors[candidate.instrument_id] = (
                        f"{type(exc).__name__}: {exc}"
                    )

            payload: dict[str, object] = {
                "authority": {
                    "prices": "consolidated_sip_trade_events",
                    "bars": "single_provider_raw_finalized_sip_5m",
                    "provider": "alpaca_sip",
                    "web_fallback_allowed": False,
                    "iex_fallback_allowed": False,
                },
                "expected_candidate_count": started.frozen_scope.expected_candidate_count,
                "scored_candidate_count": len(outcomes),
                "outcomes": outcomes,
                "reconciliation_evidence": [
                    item.model_dump(mode="json") for item in evidence
                ],
                "errors": errors,
            }
            if not errors and len(outcomes) == len(universe.candidates):
                final = finalize_reconciliation(
                    started,
                    observed_at=now,
                    payload=payload,
                )
                await asyncio.to_thread(
                    manifests.save_transition,
                    started,
                    final,
                )
                self.final_count += 1
                trade_log(
                    "auto_trading",
                    "session_evidence_reconciliation_final",
                    strategy_id=started.strategy_id,
                    session_date=started.frozen_scope.session_date.isoformat(),
                    manifest_id=started.manifest_id,
                    scored_candidate_count=len(outcomes),
                    execution_authority=False,
                )
                return

            age = now.astimezone(_ET).date() - started.frozen_scope.session_date
            if age.days >= _max_age_days():
                closed = permanently_unscorable(
                    started,
                    observed_at=now,
                    payload=payload,
                )
                await asyncio.to_thread(
                    manifests.save_transition,
                    started,
                    closed,
                )
                self.permanently_unscorable_count += 1
                return

            deferred = defer_reconciliation(
                started,
                observed_at=now,
                next_retry_at=now + timedelta(minutes=_retry_minutes()),
                payload=payload,
            )
            await asyncio.to_thread(
                manifests.save_transition,
                started,
                deferred,
            )
            self.deferred_count += 1
        except Exception as exc:
            self.last_error = (
                f"reconcile/{started.strategy_id}/{started.frozen_scope.session_date}: "
                f"{type(exc).__name__}: {exc}"
            )
            payload = {
                "authority": {
                    "prices": "consolidated_sip_trade_events",
                    "bars": "single_provider_raw_finalized_sip_5m",
                    "web_fallback_allowed": False,
                    "iex_fallback_allowed": False,
                },
                "errors": {
                    "__session__": f"{type(exc).__name__}: {exc}",
                },
            }
            age = now.astimezone(_ET).date() - started.frozen_scope.session_date
            if age.days >= _max_age_days():
                updated = permanently_unscorable(
                    started,
                    observed_at=now,
                    payload=payload,
                )
                self.permanently_unscorable_count += 1
            else:
                updated = defer_reconciliation(
                    started,
                    observed_at=now,
                    next_retry_at=now + timedelta(minutes=_retry_minutes()),
                    payload=payload,
                )
                self.deferred_count += 1
            await asyncio.to_thread(
                manifests.save_transition,
                started,
                updated,
            )

    async def run_once(self) -> int:
        now = self.now_factory()
        if now.tzinfo is None:
            raise ValueError("session reconciliation clock must be timezone-aware")
        repository = self.strategy_repository_factory()
        manifests = self.manifest_repository_factory()

        await self._create_current_manifests(
            repository,
            manifests,
            now=now,
        )
        pending = await asyncio.to_thread(
            manifests.pending,
            as_of=now,
            limit=20,
        )
        for manifest in pending:
            try:
                await self._attempt_manifest(
                    repository,
                    manifests,
                    manifest,
                    now=now,
                )
            except Exception as exc:
                self.last_error = (
                    f"{manifest.manifest_id}: {type(exc).__name__}: {exc}"
                )
        self.last_run_at = now
        return len(pending)

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": session_reconciliation_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "retry_minutes": _retry_minutes(),
            "maximum_pending_age_days": _max_age_days(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "manifest_create_count": self.manifest_create_count,
            "attempt_count": self.attempt_count,
            "final_count": self.final_count,
            "deferred_count": self.deferred_count,
            "permanently_unscorable_count": self.permanently_unscorable_count,
            "authoritative_price_source": "consolidated_sip_trade_events",
            "authoritative_bar_source": "single_provider_raw_finalized_sip_5m",
            "fallback_substitution_allowed": False,
        }

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.interval_seconds)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def register_trading_session_reconciliation_monitor(
    gateway: FastAPI,
) -> TradingSessionReconciliationMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingSessionReconciliationMonitor):
        return existing
    monitor = TradingSessionReconciliationMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if session_reconciliation_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "TradingSessionReconciliationMonitor",
    "register_trading_session_reconciliation_monitor",
    "session_reconciliation_monitor_enabled",
]
