"""Gateway routes and startup hook for TTS runtime readiness."""
from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from app.shared import get_tts_provider

from .tts_runtime_actions import unload_tts_runtime, warm_tts_runtime
from .tts_runtime_state import STATE, STATE_LOCK, WARMUP_STREAM_ID, snapshot, startup_warmup_enabled
from .tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_tts_runtime_routes_registered"
_HOOK_SENTINEL = "_omnix_tts_runtime_routes_hook_installed"


def register_tts_runtime_routes(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    async def startup() -> None:
        if not startup_warmup_enabled():
            with STATE_LOCK:
                STATE.update(status="disabled", trigger="startup")
            stream_log(WARMUP_STREAM_ID, "lifecycle", "startup_warmup_disabled")
            return
        await asyncio.to_thread(warm_tts_runtime, "startup")

    gateway.add_event_handler("startup", startup)

    @gateway.get("/api/tts/runtime/status", include_in_schema=False)
    async def status() -> dict[str, Any]:
        try:
            return snapshot(get_tts_provider())
        except Exception:
            return snapshot()

    @gateway.post("/api/tts/runtime/warmup", include_in_schema=False)
    async def warmup() -> dict[str, Any]:
        return await asyncio.to_thread(warm_tts_runtime, "api")

    @gateway.post("/api/tts/runtime/unload", include_in_schema=False)
    async def unload() -> dict[str, Any]:
        return await asyncio.to_thread(unload_tts_runtime, "api")


def install_tts_runtime_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_tts_runtime_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
