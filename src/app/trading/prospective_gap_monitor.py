from __future__ import annotations

"""Background orchestration for the prospective-gap runtime.

Once the premarket authority is frozen, Omnix—not the reporting agent—owns
post-open confirmation and deterministic post-close finalization.
"""

import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .prospective_gap_runtime import ProspectiveGapRuntime, default_prospective_gap_runtime
from .us_equity_calendar import early_close_time, regular_holidays


_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_prospective_gap_monitor"
_PREMARKET_HANDOFF_INGEST_START = time(9, 26)
_PREMARKET_HANDOFF_INGEST_END = time(9, 29)


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def prospective_gap_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_PROSPECTIVE_GAP_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_PROSPECTIVE_GAP_MONITOR", "1")


class ProspectiveGapMonitor:
    def __init__(
        self,
        *,
        interval_seconds: float = 60.0,
        runtime_factory=default_prospective_gap_runtime,
    ) -> None:
        self.interval_seconds = max(15.0, float(interval_seconds))
        self.runtime_factory = runtime_factory
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.confirmation_run_count = 0
        self.postclose_finalize_count = 0
        self.no_session_count = 0
        self.scheduler_handoff_ingest_count = 0
        self.scheduler_handoff_error_count = 0

    async def run_once(self, *, now: datetime | None = None) -> int:
        observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        local = observed.astimezone(_ET)
        self.last_run_at = observed
        if local.weekday() >= 5 or local.date() in regular_holidays(local.year):
            return 0

        runtime: ProspectiveGapRuntime = self.runtime_factory()
        ledger = runtime.session_ledger(local.date())
        clock = local.timetz().replace(tzinfo=None)
        if ledger.latest(kind="session_manifest", instrument_id="__session__") is None:
            if _PREMARKET_HANDOFF_INGEST_START <= clock <= _PREMARKET_HANDOFF_INGEST_END:
                try:
                    ingested = await asyncio.to_thread(
                        runtime.try_freeze_scheduler_inbox,
                        local.date(),
                        observed_at=observed,
                    )
                    if ingested is not None:
                        self.scheduler_handoff_ingest_count += 1
                        ledger = runtime.session_ledger(local.date())
                except Exception:
                    self.scheduler_handoff_error_count += 1
                    raise
            if ledger.latest(kind="session_manifest", instrument_id="__session__") is None:
                self.no_session_count += 1
                return 0

        if time(9, 30) <= clock <= time(11, 35):
            await asyncio.to_thread(
                runtime.run_confirmation,
                session_date=local.date(),
                evaluated_at=observed,
            )
            self.confirmation_run_count += 1
            return 1

        regular_close = early_close_time(local.date()) or time(16, 0)
        finalize_after = (
            datetime.combine(local.date(), regular_close, tzinfo=_ET)
            + timedelta(minutes=20)
        ).time()
        if clock >= finalize_after:
            if ledger.latest(kind="daily_scorecard", instrument_id="__scorecard__") is None:
                await asyncio.to_thread(
                    runtime.finalize_postclose,
                    session_date=local.date(),
                    evaluated_at=observed,
                )
                self.postclose_finalize_count += 1
                return 1
        return 0

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
                self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.interval_seconds)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()


def register_prospective_gap_monitor(gateway: FastAPI) -> ProspectiveGapMonitor | None:
    if not prospective_gap_monitor_enabled():
        return None
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, ProspectiveGapMonitor):
        return existing
    monitor = ProspectiveGapMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "ProspectiveGapMonitor",
    "prospective_gap_monitor_enabled",
    "register_prospective_gap_monitor",
]
