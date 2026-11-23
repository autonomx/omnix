"""Warn before and during market hours when trading's local model is not the one it needs.

Records a ``local_model_readiness`` event on the interday strategy whenever the answer changes: nothing loaded, another
model loaded than the pinned one, or a context too small for the prompts. Research only; it grants nothing and places
nothing.
"""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import datetime, time, timezone

from app.persistence.runtime import is_legacy_test_persistence
from app.runtime.features import FeatureContext

from .model_route import LocalModelReadiness, local_model_readiness
from .monitor_task import ScheduledTradingMonitor, TradingMonitorTask
from .strategy_managed_finviz_shadow import MANAGED_FINVIZ_SHADOW_STRATEGY_ID
from .strategy_repository import StrategyEvent, TradingStrategyRepository, default_strategy_repository
from .trade_logging import trade_log
from app.apps.trading.us_equity_calendar import EASTERN as _ET
from app.apps.trading.us_equity_calendar import regular_close_time, regular_holidays

_STATE_KEY = "_omnix_trading_local_model_monitor"
_WATCH_START_ET = time(8, 0)


def _watching(moment: datetime) -> bool:
    local = moment.astimezone(_ET)
    return (
        local.weekday() < 5
        and local.date() not in regular_holidays(local.year)
        and _WATCH_START_ET <= local.time() <= regular_close_time(local.date())
    )


class TradingLocalModelMonitor(ScheduledTradingMonitor):
    interval_seconds = 60.0

    def __init__(
        self,
        *,
        strategy_repository_factory: Callable[[], TradingStrategyRepository] = default_strategy_repository,
        readiness: Callable[[], LocalModelReadiness] = local_model_readiness,
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.strategy_repository_factory = strategy_repository_factory
        self.readiness = readiness
        self.now_factory = now_factory
        self._last: tuple[object, ...] | None = None

    async def run_once(self) -> int:
        now = self.now_factory()
        if not _watching(now):
            self._last = None
            return 0
        status = await asyncio.to_thread(self.readiness)
        if not status.applicable:
            self._last = None
            return 0
        current = (status.ready, status.model, status.context_length, status.problems)
        if current == self._last:
            return 0
        self._last = current
        state = "ready" if status.ready else "not_ready"
        trade_log(
            "auto_trading", "local_model_readiness", state=state, model=status.model,
            context_length=status.context_length, problems=list(status.problems), execution_authority=False,
        )
        identity = f"{MANAGED_FINVIZ_SHADOW_STRATEGY_ID}|local_model_readiness|{current}|{now.isoformat()}"
        idempotency_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        await asyncio.to_thread(
            self.strategy_repository_factory().append_event,
            StrategyEvent(
                strategy_id=MANAGED_FINVIZ_SHADOW_STRATEGY_ID,
                event_id=idempotency_key[:32],
                run_id="local-model-readiness",
                instrument_id="__provider__",
                event_type="local_model_readiness",
                state=state,
                reason_code=status.problems[0] if status.problems else "LOCAL_MODEL_READY",
                observed_at=now,
                idempotency_key=idempotency_key,
                payload={
                    "model": status.model,
                    "context_length": status.context_length,
                    "problems": list(status.problems),
                    "research_only": True,
                    "execution_authority": False,
                },
            ),
        )
        return 1


def _enabled() -> bool:
    return not is_legacy_test_persistence()


def create_trading_local_model_monitor_task(context: FeatureContext) -> TradingMonitorTask | None:
    state = context.runtime_state
    if isinstance(getattr(state, _STATE_KEY, None), TradingLocalModelMonitor):
        return None
    monitor = TradingLocalModelMonitor()
    setattr(state, _STATE_KEY, monitor)
    return TradingMonitorTask(name=__name__, monitor=monitor, enabled=_enabled)


__all__ = ["TradingLocalModelMonitor", "create_trading_local_model_monitor_task"]
