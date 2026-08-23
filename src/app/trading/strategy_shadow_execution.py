from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .indicator_signals import multi_timeframe_indicator_context


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
    """Capture execution and indicator evidence a SHADOW signal sees without trading.

    This module intentionally has no paper repository or order dependency. SHADOW
    may observe quote/book/freshness/halt state plus finalized 1m/5m momentum
    context, but only AUTO PAPER is allowed to create orders or protections.

    Indicator telemetry is supplemental: inability to refresh indicator bars does
    not change execution eligibility or suppress the execution evidence.
    """

    execution = market_service.execution_observation(instrument_id, binding_id)
    payload = {field: getattr(execution, field, None) for field in _EXECUTION_FIELDS}
    try:
        response = market_service.bars(instrument_id, "1m", 240, binding_id)
        finalized = [bar for bar in response.bars if bar.is_final]
        context = multi_timeframe_indicator_context(finalized)
        payload["indicator_context"] = context.model_dump(mode="json")
        payload["indicator_context_error"] = None
    except Exception as exc:  # telemetry must never alter the execution decision
        payload["indicator_context"] = None
        payload["indicator_context_error"] = f"{type(exc).__name__}: {exc}"
    reason: ShadowExecutionReason = (
        "SHADOW_EXECUTION_OBSERVED"
        if execution.execution_eligible
        else "SHADOW_EXECUTION_INELIGIBLE"
    )
    return ShadowExecutionEvidence(reason_code=reason, execution=payload)
