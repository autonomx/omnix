"""Gateway routes and startup hook for TTS runtime readiness."""
from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Callable

from fastapi import APIRouter

from app.providers.service import get_tts_provider

from .tts_runtime_actions import unload_tts_runtime, warm_tts_runtime
from .tts_runtime_state import STATE, STATE_LOCK, WARMUP_STREAM_ID, snapshot, startup_warmup_enabled
from app.observability.tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_tts_runtime_routes_registered"


def register_tts_runtime_routes(router: APIRouter, state: Any) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    async def startup() -> None:
        from app.runtime.config import get_runtime_config
        config = getattr(state, 'runtime_config', None) or get_runtime_config()
        if not (config.allow_local_tts or config.use_remote_tts):
            return
        if not startup_warmup_enabled():
            with STATE_LOCK:
                STATE.update(status="disabled", trigger="startup")
            stream_log(WARMUP_STREAM_ID, "lifecycle", "startup_warmup_disabled")
            return
        task = asyncio.create_task(asyncio.to_thread(warm_tts_runtime, "startup"))
        setattr(state, "_omnix_tts_startup_warmup_task", task)


    async def shutdown() -> None:
        task = getattr(state, "_omnix_tts_startup_warmup_task", None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            state._omnix_tts_startup_warmup_task = None

    router.add_event_handler("startup", startup)
    router.add_event_handler("shutdown", shutdown)

    @router.get("/api/tts/runtime/status")
    def status() -> dict[str, Any]:
        try:
            return snapshot(get_tts_provider())
        except Exception:
            return snapshot()

    @router.post("/api/tts/runtime/warmup")
    async def warmup() -> dict[str, Any]:
        return await asyncio.to_thread(warm_tts_runtime, "api")

    @router.post("/api/tts/runtime/unload")
    async def unload() -> dict[str, Any]:
        return await asyncio.to_thread(unload_tts_runtime, "api")
