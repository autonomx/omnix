"""Launch current wizard payloads through the Campaign Genesis pipeline."""

from __future__ import annotations

import logging
import time
from typing import Any

from .bootstrap import bootstrap_session_from_compiled_genesis
from .compiler import compile_campaign_genesis
from .legacy_adapter import (
    adapt_genesis_payload_to_new_game_payload,
)
from .pipeline_adapter import create_new_game_session_from_compiled_genesis
from .request_promoter import promote_new_game_request_to_genesis

_logger = logging.getLogger(__name__)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _elapsed_ms(started_at: float) -> int:
    return max(0, int(round((time.perf_counter() - started_at) * 1000)))


def _record_trace_event(events: list[dict[str, Any]], stage: str, status: str, started_at: float) -> None:
    event = {
        "stage": stage,
        "status": status,
        "elapsed_ms": _elapsed_ms(started_at),
    }
    events.append(event)
    _logger.info("[RPG][new-game] %s %s %sms", stage, status, event["elapsed_ms"])


def create_promoted_new_game(payload: dict[str, Any]) -> dict[str, Any]:
    trace_events: list[dict[str, Any]] = []
    overall_started_at = time.perf_counter()

    stage_started_at = time.perf_counter()
    raw = _safe_dict(payload.get("request") or payload)
    contract = promote_new_game_request_to_genesis(raw)
    _record_trace_event(trace_events, "promote_request", "completed", stage_started_at)

    stage_started_at = time.perf_counter()
    legacy = adapt_genesis_payload_to_new_game_payload(
        {"request": {"genesis": contract.model_dump(mode="json")}}
    )
    _record_trace_event(trace_events, "adapt_legacy_payload", "completed", stage_started_at)

    stage_started_at = time.perf_counter()
    compiled = compile_campaign_genesis(contract)
    _record_trace_event(trace_events, "compile_genesis", "completed", stage_started_at)

    stage_started_at = time.perf_counter()
    bootstrap = bootstrap_session_from_compiled_genesis(compiled)
    _record_trace_event(trace_events, "bootstrap_session", "completed", stage_started_at)

    stage_started_at = time.perf_counter()
    result = create_new_game_session_from_compiled_genesis(
        bootstrap=bootstrap,
        compiled=compiled,
        contract=contract,
        legacy=legacy,
    )
    _record_trace_event(trace_events, "create_and_save_session", "completed", stage_started_at)

    return {
        **result,
        "creation_server_trace": {
            "route": "create_promoted_new_game",
            "elapsed_ms": _elapsed_ms(overall_started_at),
            "events": trace_events,
        },
    }
