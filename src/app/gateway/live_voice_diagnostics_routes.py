"""Browser diagnostics ingestion for live-call streaming."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .live_voice_stream_diagnostics import diagnostics_log_path, live_voice_log, normalize_trace_id

_ROUTE_SENTINEL = "_omnix_live_voice_diagnostics_registered"
_HOOK_SENTINEL = "_omnix_live_voice_diagnostics_hook_installed"
LIVE_VOICE_DIAGNOSTICS_PATH = "/api/tts/live-call/diagnostics"


class LiveVoiceDiagnosticEvent(BaseModel):
    source: str = Field(default="browser", max_length=80)
    event: str = Field(min_length=1, max_length=160)
    details: dict[str, Any] = Field(default_factory=dict)


class LiveVoiceDiagnosticBatch(BaseModel):
    trace_id: str = Field(min_length=1, max_length=160)
    events: list[LiveVoiceDiagnosticEvent] = Field(min_length=1, max_length=200)


def register_live_voice_diagnostics_routes(gateway: FastAPI) -> None:
    """Register live-call diagnostics ingestion once."""
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.post(LIVE_VOICE_DIAGNOSTICS_PATH, include_in_schema=False)
    async def ingest_live_voice_diagnostics(batch: LiveVoiceDiagnosticBatch) -> dict[str, Any]:
        trace_id = normalize_trace_id(batch.trace_id)
        for item in batch.events:
            live_voice_log(trace_id, item.source, item.event, **item.details)
        return {
            "accepted": len(batch.events),
            "trace_id": trace_id,
            "log_path": diagnostics_log_path(),
        }

    @gateway.get(f"{LIVE_VOICE_DIAGNOSTICS_PATH}/status", include_in_schema=False)
    async def live_voice_diagnostics_status() -> dict[str, Any]:
        return {"ready": True, "log_path": diagnostics_log_path()}


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
