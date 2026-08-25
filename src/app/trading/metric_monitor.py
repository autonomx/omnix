from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from .catalog import INSTRUMENTS, bindings_for_instrument
from .metric_data import TradingMetricDataService, default_metric_data_service


_MONITOR_STATE_KEY = "_omnix_trading_metric_monitor"


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def trading_liquidation_collector_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _env_flag("OMNIX_TRADING_LIQUIDATION_COLLECTOR_IN_TESTS", "0")
    return _env_flag("OMNIX_TRADING_LIQUIDATION_COLLECTOR", "1")


def _binance_symbols() -> tuple[str, ...]:
    symbols: set[str] = set()
    for instrument in INSTRUMENTS:
        if instrument.venue != "BINANCE":
            continue
        binding = next(
            (item for item in bindings_for_instrument(instrument.instrument_id) if item.provider == "binance"),
            None,
        )
        if binding is not None:
            symbols.add(binding.provider_symbol.upper())
    return tuple(sorted(symbols))


class TradingMetricMonitor:
    """Starts bounded runtime collectors needed by stream-only chart metrics."""

    def __init__(self, service: TradingMetricDataService | None = None) -> None:
        self.service = service
        self.started_symbols: tuple[str, ...] = ()

    def start(self) -> None:
        service = self.service or default_metric_data_service()
        self.service = service
        symbols = _binance_symbols()
        for symbol in symbols:
            service.binance.liquidation_buffer.ensure_started(symbol)
        self.started_symbols = symbols

    def diagnostics(self) -> dict[str, Any]:
        service = self.service
        return {
            "enabled": trading_liquidation_collector_enabled(),
            "started_symbols": list(self.started_symbols),
            "collecting": {
                symbol: bool(
                    service
                    and service.binance.liquidation_buffer.is_collecting(symbol)
                )
                for symbol in self.started_symbols
            },
        }


def register_trading_metric_monitor(gateway: FastAPI) -> TradingMetricMonitor:
    existing = getattr(gateway.state, _MONITOR_STATE_KEY, None)
    if isinstance(existing, TradingMetricMonitor):
        return existing
    monitor = TradingMetricMonitor()
    setattr(gateway.state, _MONITOR_STATE_KEY, monitor)

    async def startup() -> None:
        if trading_liquidation_collector_enabled():
            monitor.start()

    gateway.router.add_event_handler("startup", startup)
    return monitor
