from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ShadowExecutionReason = Literal[
    "SHADOW_EXECUTION_OBSERVED",
    "SHADOW_EXECUTION_INELIGIBLE",
]


_EXECUTION_FIELDS = (
    "instrument_id",
    "binding_id",
    "provider",
    "last",
    "bid",
    "ask",
    "bid_size",
    "ask_size",
    "high",
    "low",
    "bar_volume",
    "bar_start_time",
    "source_time",
    "spread_bps",
    "execution_eligible",
    "freshness_mode",
    "rejection_reasons",
    "halted",
)


@dataclass(frozen=True)
class ShadowExecutionEvidence:
    reason_code: ShadowExecutionReason
    execution: dict[str, object]


def observe_shadow_execution(
    market_service,
    *,
    instrument_id: str,
    binding_id: str | None,
) -> ShadowExecutionEvidence:
    """Capture the execution evidence a strategy signal sees without trading.

    This module intentionally has no paper repository or order dependency. SHADOW
    may observe quote/book/freshness/halt state, but only AUTO PAPER is allowed to
    create orders or protections.
    """

    execution = market_service.execution_observation(instrument_id, binding_id)
    payload = {field: getattr(execution, field, None) for field in _EXECUTION_FIELDS}
    reason: ShadowExecutionReason = (
        "SHADOW_EXECUTION_OBSERVED"
        if execution.execution_eligible
        else "SHADOW_EXECUTION_INELIGIBLE"
    )
    return ShadowExecutionEvidence(reason_code=reason, execution=payload)
