from __future__ import annotations

from app.config.env import environment

import asyncio
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from app.runtime.features import FeatureContext


from .monitor_task import ScheduledTradingMonitor, TradingMonitorTask
from .alerts import (
    AlertEvaluationContext,
    AlertOutcomeRecord,
    TradingAlert,
    TradingAlertRepository,
    default_alert_repository,
)
from .alerts_evaluation import evaluate_conditions, history_limit, required_bars
from .service import TradingMarketDataService, default_market_data_service


_MONITOR_STATE_KEY = "_omnix_trading_alert_monitor"


def _env_flag(name: str, default: str = "1") -> bool:
    return environment().get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def trading_alert_monitor_enabled() -> bool:
    if environment().get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _env_flag("OMNIX_TRADING_ALERT_MONITOR_IN_TESTS", "0")
    return _env_flag("OMNIX_TRADING_ALERT_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(environment().get("OMNIX_TRADING_ALERT_INTERVAL_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(5.0, value)


def _history_limit(alerts: Sequence[TradingAlert]) -> int:
    """Bars to fetch for a group of alerts; see ``alerts_evaluation.history_limit``."""
    return history_limit(max((required_bars(alert.conditions) for alert in alerts), default=1))


def _final_only(alert: TradingAlert) -> bool:
    return alert.frequency == "once_per_bar_close" or not alert.evaluation_policy.allow_partial_bars


def _outcomes(alerts: Sequence[TradingAlert], bars: Sequence[Any]) -> list[AlertOutcomeRecord]:
    records: list[AlertOutcomeRecord] = []
    for alert in alerts:
        outcome = evaluate_conditions(alert.conditions, bars, final_only=_final_only(alert))
        if outcome is not None:
            records.append(AlertOutcomeRecord(alert.alert_id, alert.revision, outcome))
    return records


class TradingAlertMonitor(ScheduledTradingMonitor):
    def __init__(
        self,
        *,
        repository_factory: Callable[[], TradingAlertRepository] = default_alert_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        interval_seconds: float | None = None,
    ) -> None:
        self.repository_factory = repository_factory
        self.market_service_factory = market_service_factory
        self.interval_seconds = interval_seconds or _interval_seconds()
        self.last_error: str | None = None
        self.last_run_at: datetime | None = None
        self.evaluation_count = 0
        self.trigger_count = 0

    async def run_once(self) -> int:
        repository = self.repository_factory()
        alerts = await asyncio.to_thread(repository.list_alerts, 500)
        targets: dict[tuple[str, str | None, str], list[TradingAlert]] = defaultdict(list)
        now = datetime.now(timezone.utc)
        for alert in alerts:
            if alert.enabled and not alert.is_expired(now):
                targets[
                    (
                        alert.instrument_id,
                        alert.binding_id,
                        alert.evaluation_policy.interval,
                    )
                ].append(alert)
        triggered = 0
        service = self.market_service_factory()
        for target in sorted(targets, key=lambda item: (item[0], item[1] or "", item[2])):
            instrument_id, requested_binding_id, interval = target
            target_alerts = targets[target]
            try:
                response = await asyncio.to_thread(
                    service.bars,
                    instrument_id,
                    interval,
                    _history_limit(target_alerts),
                    requested_binding_id,
                )
                if not response.bars:
                    continue
                bars = list(response.bars)
                # Indicator maths is CPU work; keep it off the event loop.
                outcomes = await asyncio.to_thread(_outcomes, target_alerts, bars)
                if not outcomes:
                    continue
                triggers = await asyncio.to_thread(
                    repository.record_outcomes,
                    AlertEvaluationContext(
                        instrument_id=instrument_id,
                        interval=interval,
                        evaluated_at=datetime.now(timezone.utc),
                        binding_id=requested_binding_id,
                        resolved_binding_id=response.binding.binding_id,
                        provider=response.binding.provider,
                    ),
                    outcomes,
                )
                self.evaluation_count += 1
                triggered += len(triggers)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
        self.trigger_count += triggered
        self.last_run_at = datetime.now(timezone.utc)
        return triggered

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": trading_alert_monitor_enabled(),
            "running": self.scheduled,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "evaluation_count": self.evaluation_count,
            "trigger_count": self.trigger_count,
        }


def create_trading_alert_monitor_task(context: FeatureContext) -> TradingMonitorTask | None:
    state = context.runtime_state
    existing = getattr(state, _MONITOR_STATE_KEY, None)
    if isinstance(existing, TradingAlertMonitor):
        return None
    monitor = TradingAlertMonitor()
    setattr(state, _MONITOR_STATE_KEY, monitor)
    return TradingMonitorTask(name=__name__, monitor=monitor, enabled=trading_alert_monitor_enabled)
