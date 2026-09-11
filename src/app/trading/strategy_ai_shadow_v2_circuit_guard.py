from __future__ import annotations

"""Final AI Shadow v2 provider-outage guard.

The roadmap policy records a useful error when a real provider attempt fails.
Once the shared trading-research circuit is open, however, repeatedly invoking
that policy would only create another synthetic alpha-error row every heartbeat.
This final wrapper suppresses those doomed calls until the circuit is eligible
for recovery. A process-wide lock also prevents four v2 arms from concurrently
using the same long-lived Codex app-server process.
"""

import threading
import time

from . import ai_shadow_reliability as reliability
from . import strategy_ai_shadow_v2_monitor as monitor
from .strategy_ai_shadow_v2 import AIShadowV2Analyzer

_INSTALLED = False
_ORIGINAL_RUN_ARM = None
_ORIGINAL_ASSESS = None
_PROVIDER_CALL_LOCK = threading.RLock()


def _serialized_assess(self: AIShadowV2Analyzer, *, arm, rows):
    assert _ORIGINAL_ASSESS is not None
    with _PROVIDER_CALL_LOCK:
        return _ORIGINAL_ASSESS(self, arm=arm, rows=rows)


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
    global _INSTALLED, _ORIGINAL_RUN_ARM, _ORIGINAL_ASSESS
    if _INSTALLED:
        return
    _ORIGINAL_RUN_ARM = monitor.TradingAIShadowV2Monitor._run_arm
    _ORIGINAL_ASSESS = AIShadowV2Analyzer.assess
    AIShadowV2Analyzer.assess = _serialized_assess
    monitor.TradingAIShadowV2Monitor._run_arm = _run_arm_circuit_guard
    _INSTALLED = True


__all__ = ["install_ai_shadow_v2_circuit_guard"]
