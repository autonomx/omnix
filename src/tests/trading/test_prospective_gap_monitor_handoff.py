from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from app.trading.prospective_gap_monitor import ProspectiveGapMonitor


class _EmptyLedger:
    def latest(self, *, kind: str, instrument_id: str):
        return None


class _Runtime:
    def __init__(self) -> None:
        self.ingest_calls: list[tuple[date, datetime]] = []

    def session_ledger(self, session_date: date):
        return _EmptyLedger()

    def try_freeze_scheduler_inbox(
        self,
        session_date: date,
        *,
        received_at: datetime,
    ):
        self.ingest_calls.append((session_date, received_at))
        return None


def test_monitor_waits_for_late_premarket_before_ingesting_scheduler_handoff() -> None:
    runtime = _Runtime()
    monitor = ProspectiveGapMonitor(runtime_factory=lambda: runtime)

    before_window = datetime(2026, 9, 23, 13, 25, 30, tzinfo=timezone.utc)
    asyncio.run(monitor.run_once(now=before_window))
    assert runtime.ingest_calls == []

    inside_window = datetime(2026, 9, 23, 13, 26, 30, tzinfo=timezone.utc)
    asyncio.run(monitor.run_once(now=inside_window))
    assert runtime.ingest_calls == [(date(2026, 9, 23), inside_window)]


def test_monitor_does_not_retroactively_ingest_after_0929_et() -> None:
    runtime = _Runtime()
    monitor = ProspectiveGapMonitor(runtime_factory=lambda: runtime)

    after_cutoff = datetime(2026, 9, 23, 13, 29, 5, tzinfo=timezone.utc)
    asyncio.run(monitor.run_once(now=after_cutoff))

    assert runtime.ingest_calls == []
