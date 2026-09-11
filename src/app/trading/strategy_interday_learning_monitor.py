from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .strategy_dynamic_discovery import AttributionEvent, INTERDAY_TRADING_STRATEGY_ID
from .strategy_dynamic_discovery_learning import build_daily_discovery_report
from .strategy_dynamic_discovery_repository import (
    DynamicDiscoveryEventRepository,
    EVENT_ATTRIBUTION,
)
from .strategy_interday_attribution import bridge_strategy_events
from .strategy_repository import TradingStrategyRepository, default_strategy_repository
from .trade_logging import trade_log

_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_interday_learning_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def interday_learning_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_INTERDAY_LEARNING_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_INTERDAY_LEARNING", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_INTERDAY_LEARNING_INTERVAL_SECONDS", "300"))
    except ValueError:
        value = 300.0
    return max(60.0, value)


def _same_session(event_time: datetime, session_date) -> bool:
    return event_time.astimezone(_ET).date() == session_date


async def run_interday_learning_once(
    *,
    now: datetime | None = None,
    repository: TradingStrategyRepository | None = None,
) -> dict[str, int | bool]:
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    session_date = observed_at.astimezone(_ET).date()
    repo = repository or default_strategy_repository()
    try:
        parent = await asyncio.to_thread(repo.get_config, INTERDAY_TRADING_STRATEGY_ID)
    except ValueError:
        return {"bridged": 0, "reported": False}
    if not parent.enabled or parent.archived_at is not None:
        return {"bridged": 0, "reported": False}

    configs = await asyncio.to_thread(repo.list_configs, active_only=False)
    strategy_ids = {
        item.strategy_id
        for item in configs
        if item.strategy_id == INTERDAY_TRADING_STRATEGY_ID
        or item.parent_strategy_id == INTERDAY_TRADING_STRATEGY_ID
    }
    events_by_strategy = {}
    for strategy_id in sorted(strategy_ids):
        rows = await asyncio.to_thread(repo.recent_events, strategy_id, 10_000)
        events_by_strategy[strategy_id] = [row for row in rows if _same_session(row.observed_at, session_date)]
    bridged = await asyncio.to_thread(
        bridge_strategy_events,
        repo,
        session_date=session_date,
        events_by_strategy=events_by_strategy,
    )

    local_time = observed_at.astimezone(_ET).time().replace(tzinfo=None)
    if local_time < time(16, 10):
        return {"bridged": bridged, "reported": False}

    event_repo = DynamicDiscoveryEventRepository(repo)
    candidates = tuple((await asyncio.to_thread(event_repo.latest_candidates, session_date)).values())
    session_events = await asyncio.to_thread(event_repo.session_events, session_date)
    attribution: list[AttributionEvent] = []
    for event in session_events:
        if event.event_type != EVENT_ATTRIBUTION:
            continue
        try:
            attribution.append(AttributionEvent.model_validate(event.payload))
        except Exception:
            continue
    report = build_daily_discovery_report(
        session_date=session_date,
        generated_at=observed_at,
        candidates=candidates,
        attribution=tuple(attribution),
        outcomes=(),
    )
    reported = await asyncio.to_thread(
        event_repo.persist_report,
        session_date=session_date,
        observed_at=observed_at,
        payload=report.model_dump(mode="json"),
    )
    return {"bridged": bridged, "reported": bool(reported)}


class InterdayLearningMonitor:
    def __init__(self, *, interval_seconds: float | None = None) -> None:
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.bridged_count = 0
        self.report_count = 0

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

    async def run_once(self) -> dict[str, int | bool]:
        result = await run_interday_learning_once()
        self.bridged_count += int(result["bridged"])
        self.report_count += int(bool(result["reported"]))
        self.last_run_at = datetime.now(timezone.utc)
        self.last_error = None
        return result

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "interday_learning_monitor_error",
                    strategy_id=INTERDAY_TRADING_STRATEGY_ID,
                    observed_at=datetime.now(timezone.utc),
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    research_only=True,
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)


def register_interday_learning_monitor(gateway: FastAPI) -> InterdayLearningMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, InterdayLearningMonitor):
        return existing
    monitor = InterdayLearningMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if interday_learning_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "InterdayLearningMonitor",
    "interday_learning_monitor_enabled",
    "register_interday_learning_monitor",
    "run_interday_learning_once",
]
