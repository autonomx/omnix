"""Browser diagnostics ingestion for live-call streaming."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

from .content_free_diagnostics import sanitize_content_free_details
from .live_chat_evaluation_routes import register_live_chat_evaluation_routes
from .live_chat_release_gate import (
    LiveChatReleaseGateEvaluationRequest,
    LiveChatReleaseGateReport,
    evaluate_live_chat_release_gate,
)
from .live_voice_release_gate import (
    LiveVoiceReleaseEvent,
    LiveVoiceReleaseGateReport,
    LiveVoiceReleaseThresholds,
    evaluate_live_voice_log,
    evaluate_live_voice_release_gate,
)
from .live_voice_stream_diagnostics import diagnostics_log_path, live_voice_log, normalize_trace_id

_ROUTE_SENTINEL = "_omnix_live_voice_diagnostics_registered"
_HOOK_SENTINEL = "_omnix_live_voice_diagnostics_hook_installed"
LIVE_VOICE_DIAGNOSTICS_PATH = "/api/tts/live-call/diagnostics"
_LOG_ENVELOPE_FIELDS = {
    "event",
    "monotonic_ms",
    "process_id",
    "sequence",
    "source",
    "thread_id",
    "thread_name",
    "timestamp_utc",
    "trace_id",
}


class LiveVoiceDiagnosticEvent(BaseModel):
    source: str = Field(default="browser", max_length=80)
    event: str = Field(min_length=1, max_length=160)
    details: dict[str, Any] = Field(default_factory=dict)


class LiveVoiceDiagnosticBatch(BaseModel):
    trace_id: str = Field(min_length=1, max_length=160)
    events: list[LiveVoiceDiagnosticEvent] = Field(min_length=1, max_length=200)


class LiveVoiceReleaseGateEvaluationRequest(BaseModel):
    events: list[LiveVoiceReleaseEvent] = Field(min_length=1, max_length=100_000)
    thresholds: LiveVoiceReleaseThresholds = Field(default_factory=LiveVoiceReleaseThresholds)


def register_live_voice_diagnostics_routes(gateway: FastAPI) -> None:
    """Register live-call diagnostics ingestion once."""
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.post(LIVE_VOICE_DIAGNOSTICS_PATH, include_in_schema=False)
    async def ingest_live_voice_diagnostics(batch: LiveVoiceDiagnosticBatch) -> dict[str, Any]:
        trace_id = normalize_trace_id(batch.trace_id)
        for item in batch.events:
            details = sanitize_content_free_details(item.details)
            live_voice_log(
                trace_id,
                item.source,
                item.event,
                **{key: value for key, value in details.items() if key not in _LOG_ENVELOPE_FIELDS},
            )
        return {
            "accepted": len(batch.events),
            "trace_id": trace_id,
            "log_path": diagnostics_log_path(),
        }

    @gateway.get(f"{LIVE_VOICE_DIAGNOSTICS_PATH}/status", include_in_schema=False)
    async def live_voice_diagnostics_status() -> dict[str, Any]:
        return {"ready": True, "log_path": diagnostics_log_path()}

    @gateway.get(
        f"{LIVE_VOICE_DIAGNOSTICS_PATH}/release-gate",
        response_model=LiveVoiceReleaseGateReport,
        include_in_schema=False,
    )
    async def live_voice_release_gate(
        hours: int = Query(default=24, ge=1, le=24 * 30),
        minimum_latency_samples: int = Query(default=5, ge=1, le=10_000),
        minimum_quality_trials: int = Query(default=10, ge=1, le=10_000),
    ) -> LiveVoiceReleaseGateReport:
        thresholds = LiveVoiceReleaseThresholds(
            minimum_latency_samples=minimum_latency_samples,
            minimum_quality_trials=minimum_quality_trials,
        )
        return evaluate_live_voice_log(
            diagnostics_log_path(),
            hours=hours,
            thresholds=thresholds,
        )

    @gateway.post(
        f"{LIVE_VOICE_DIAGNOSTICS_PATH}/release-gate/evaluate",
        response_model=LiveVoiceReleaseGateReport,
        include_in_schema=False,
    )
    async def evaluate_live_voice_release_gate_payload(
        request: LiveVoiceReleaseGateEvaluationRequest,
    ) -> LiveVoiceReleaseGateReport:
        return evaluate_live_voice_release_gate(
            request.events,
            thresholds=request.thresholds,
        )

    @gateway.post(
        f"{LIVE_VOICE_DIAGNOSTICS_PATH}/release-gate/v2/evaluate",
        response_model=LiveChatReleaseGateReport,
        include_in_schema=False,
    )
    async def evaluate_live_chat_release_gate_payload(
        request: LiveChatReleaseGateEvaluationRequest,
    ) -> LiveChatReleaseGateReport:
        return evaluate_live_chat_release_gate(
            request.metadata,
            request.events,
            thresholds=request.thresholds,
        )

    register_live_chat_evaluation_routes(gateway)


def install_live_voice_diagnostics_hook() -> None:
    """Install diagnostics registration before the gateway app is built."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_live_voice_diagnostics_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
