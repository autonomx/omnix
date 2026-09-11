from __future__ import annotations

"""Final AI Shadow v2 provider-outage guard.

The roadmap policy records a useful error when a real provider attempt fails.
Once the shared trading-research circuit is open, however, repeatedly invoking
that policy would only create another synthetic alpha-error row every heartbeat.
This final wrapper suppresses those doomed calls until the circuit is eligible
for recovery. A process-wide lock also prevents four v2 arms from concurrently
using the same long-lived Codex app-server process.

Codex already handles retryable ``willRetry`` notifications inside one provider
turn. At this outer trading boundary a terminal transport failure therefore gets
one bounded attempt and then trips the shared 2m/5m/10m circuit; we do not stack
a second 45-second v2 attempt on top of the provider's own recovery behavior.
"""

import threading
import time

from . import ai_shadow_reliability as reliability
from . import strategy_ai_shadow_v2_monitor as monitor
from . import strategy_runtime_reliability_fixes as runtime_fixes
from .strategy_ai_shadow_v2 import AIShadowV2Analyzer

_INSTALLED = False
_ORIGINAL_RUN_ARM = None
_PROVIDER_CALL_LOCK = threading.RLock()


def _serialized_assess(self: AIShadowV2Analyzer, *, arm, rows):
    """Serialize v2 access and trip the shared circuit after one terminal attempt."""

    with _PROVIDER_CALL_LOCK:
        now = time.monotonic()
        circuit = reliability._CIRCUIT
        if circuit.is_open(now):
            raise reliability.AIShadowReliabilityError(
                "ai_shadow_v2_provider_circuit_open",
                f"retry_after_seconds={circuit.retry_after(now)};failure_count={circuit.failure_count}",
            )
        base_assess = runtime_fixes._ORIGINAL_V2_ASSESS
        if base_assess is None:
            raise RuntimeError("ai_shadow_v2_base_assess_not_installed")
        self.provider_factory = reliability.get_trading_research_provider
        try:
            result = base_assess(self, arm=arm, rows=rows)
        except Exception as exc:
            if not reliability._transport_failure(exc):
                raise
            reliability._retire_trading_research_provider()
            delay = circuit.trip(time.monotonic())
            raise reliability.AIShadowReliabilityError(
                "ai_shadow_v2_transport_exhausted",
                f"attempts=1;retry_after_seconds={delay};last={type(exc).__name__}:{exc}",
            ) from exc
        circuit.success()
        return result


async def _run_arm_circuit_guard(self, *, arm, rows, config, repository, events):
    assert _ORIGINAL_RUN_ARM is not None
    now = time.monotonic()
    circuit = reliability._CIRCUIT
    if circuit.is_open(now):
        # The first exhausted transport attempt is already persisted by the
        # roadmap policy. Do not convert a known outage into hundreds of
        # per-symbol/per-heartbeat alpha errors.
        self.last_error = (
            "ai_shadow_v2_provider_circuit_open:"
            f"retry_after_seconds={circuit.retry_after(now)};"
            f"failure_count={circuit.failure_count}"
        )
        return None
    return await _ORIGINAL_RUN_ARM(
        self,
        arm=arm,
        rows=rows,
        config=config,
        repository=repository,
        events=events,
    )


def install_ai_shadow_v2_circuit_guard() -> None:
    global _INSTALLED, _ORIGINAL_RUN_ARM
    if _INSTALLED:
        return
    _ORIGINAL_RUN_ARM = monitor.TradingAIShadowV2Monitor._run_arm
    AIShadowV2Analyzer.assess = _serialized_assess
    monitor.TradingAIShadowV2Monitor._run_arm = _run_arm_circuit_guard
    _INSTALLED = True


__all__ = ["install_ai_shadow_v2_circuit_guard"]
