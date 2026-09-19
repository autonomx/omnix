from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncio

from app.trading.execution_observation_plane import ExecutionObservationPlane
from app.trading.strategy_ai_shadow_monitor import TradingAIShadowMonitor
from app.trading.execution_observation_monitor import TradingExecutionObservationMonitor


NOW = datetime(2026, 9, 18, 14, 0, tzinfo=timezone.utc)


class FailingMarketService:
    def __init__(self) -> None:
        self.calls = 0

    def execution_observation(self, instrument_id, binding_id):
        self.calls += 1
        raise RuntimeError("429 fixture")


def test_execution_observation_capture_backs_off_after_provider_failure():
    service = FailingMarketService()
    monitor = TradingExecutionObservationMonitor(
        plane=ExecutionObservationPlane(),
        now_factory=lambda: NOW,
        interval_seconds=3,
    )
    candidate = SimpleNamespace(
        instrument_id="equity:NASDAQ:TEST",
        binding_id="alpaca:TEST",
    )

    asyncio.run(monitor._capture_one(service, candidate, now=NOW))
    asyncio.run(
        monitor._capture_one(
            service,
            candidate,
            now=NOW + timedelta(seconds=1),
        )
    )

    assert service.calls == 1
    assert monitor.capture_error_count == 1
    assert monitor.backoff_skip_count == 1


def test_ai_shadow_monitor_uses_shared_execution_plane_dependency():
    plane = ExecutionObservationPlane()
    monitor = TradingAIShadowMonitor(execution_plane=plane, interval_seconds=5)
    assert monitor.execution_plane is plane
