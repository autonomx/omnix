from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI

from .alerts import (
    TradingAlert,
    TradingAlertEvaluation,
    TradingAlertRepository,
    default_alert_repository,
)
from .indicators.engine import (
    anchored_volume_weighted_average_price,
    average_true_range,
    bollinger_bands,
    exponential_moving_average,
    moving_average_convergence_divergence,
    relative_strength_index,
    simple_moving_average,
    stochastic_rsi,
)
from .models import MarketBar
from .service import TradingMarketDataService, default_market_data_service


_MONITOR_STATE_KEY = "_omnix_trading_alert_monitor"


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def trading_alert_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _env_flag("OMNIX_TRADING_ALERT_MONITOR_IN_TESTS", "0")
    return _env_flag("OMNIX_TRADING_ALERT_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_ALERT_INTERVAL_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(5.0, value)


def _history_limit(alerts: Sequence[TradingAlert]) -> int:
    required = 2
    for alert in alerts:
        parameters = alert.parameters
        required = max(required, parameters.lookback_bars + 2)
        if alert.condition_type.startswith("indicator_"):
            if parameters.indicator_id == "macd":
                required = max(
                    required,
                    parameters.slow_period + parameters.signal_period + 2,
                )
            elif parameters.indicator_id == "vwap":
                required = max(required, parameters.anchor_bars_ago + 2)
            elif parameters.indicator_id == "stochastic-rsi":
                required = max(
                    required,
                    parameters.period * 2
                    + parameters.fast_period
                    + parameters.signal_period
                    + 2,
                )
            else:
                required = max(required, parameters.period + 2)
    return min(500, required)


def _percent_change(alert: TradingAlert, bars: Sequence[MarketBar]) -> Decimal | None:
    lookback = alert.parameters.lookback_bars
    if len(bars) <= lookback:
        return None
    previous = Decimal(bars[-lookback - 1].close)
    current = Decimal(bars[-1].close)
    if previous == 0:
        return None
    return (current / previous - Decimal("1")) * Decimal("100")


def _indicator_value(alert: TradingAlert, bars: Sequence[MarketBar]) -> Decimal | None:
    parameters = alert.parameters
    indicator_id = parameters.indicator_id
    if indicator_id is None:
        return None
    closes = [Decimal(bar.close) for bar in bars]
    highs = [Decimal(bar.high) for bar in bars]
    lows = [Decimal(bar.low) for bar in bars]
    volumes = [Decimal(bar.volume) for bar in bars]
    if indicator_id == "sma":
        values = simple_moving_average(closes, parameters.period)
        return values[-1] if values else None
    if indicator_id == "ema":
        values = exponential_moving_average(closes, parameters.period)
        return values[-1] if values else None
    if indicator_id == "rsi":
        values = relative_strength_index(closes, parameters.period)
        return values[-1] if values else None
    if indicator_id == "stochastic-rsi":
        stochastic_values = stochastic_rsi(
            closes,
            parameters.period,
            parameters.fast_period,
            parameters.signal_period,
        )
        return stochastic_values[-1][0] if stochastic_values else None
    if indicator_id == "atr":
        values = average_true_range(highs, lows, closes, parameters.period)
        return values[-1] if values else None
    if indicator_id == "bollinger":
        values = bollinger_bands(closes, parameters.period)
        if not values:
            return None
        middle, upper, lower = values[-1]
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
        }.get(parameters.component, middle)
    if indicator_id == "macd":
        values = moving_average_convergence_divergence(
            closes,
            parameters.fast_period,
            parameters.slow_period,
            parameters.signal_period,
        )
        if not values:
            return None
        line, signal, histogram = values[-1]
        return {
            "line": line,
            "signal": signal,
            "histogram": histogram,
        }.get(parameters.component, line)
    anchor_index = max(0, len(bars) - 1 - parameters.anchor_bars_ago)
    values = anchored_volume_weighted_average_price(
        highs,
        lows,
        closes,
        volumes,
        anchor_index=anchor_index,
    )
    return values[-1] if values else None


class TradingAlertMonitor:
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
        self._task: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self.last_run_at: datetime | None = None
        self.evaluation_count = 0
        self.trigger_count = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

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
                latest = bars[-1]
                percent_changes = {
                    alert.alert_id: value
                    for alert in target_alerts
                    if alert.condition_type.startswith("percent_change_")
                    and (value := _percent_change(alert, bars)) is not None
                }
                indicator_values = {
                    alert.alert_id: value
                    for alert in target_alerts
                    if alert.condition_type.startswith("indicator_")
                    and (value := _indicator_value(alert, bars)) is not None
                }
                evaluated_at = datetime.now(timezone.utc)
                triggers = await asyncio.to_thread(
                    repository.evaluate,
                    TradingAlertEvaluation(
                        instrument_id=instrument_id,
                        binding_id=requested_binding_id,
                        resolved_binding_id=response.binding.binding_id,
                        provider=response.binding.provider,
                        interval=interval,
                        observed_price=Decimal(latest.close),
                        observed_volume=Decimal(latest.volume),
                        is_final=latest.is_final,
                        observed_at=latest.end_time,
                        evaluated_at=evaluated_at,
                        percent_changes=percent_changes,
                        indicator_values=indicator_values,
                    ),
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
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "evaluation_count": self.evaluation_count,
            "trigger_count": self.trigger_count,
        }

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.interval_seconds)


def register_trading_alert_monitor(gateway: FastAPI) -> TradingAlertMonitor:
    existing = getattr(gateway.state, _MONITOR_STATE_KEY, None)
    if isinstance(existing, TradingAlertMonitor):
        return existing
    monitor = TradingAlertMonitor()
    setattr(gateway.state, _MONITOR_STATE_KEY, monitor)

    async def startup() -> None:
        if trading_alert_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor
