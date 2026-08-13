"""Keep persistence and synchronous generation work off the gateway asyncio thread.

The live-call latency watchdog showed that several browser handlers synchronously
enter PostgreSQL, migration discovery, or local provider HTTP calls while a TTS
phrase is active. FastAPI only moves ordinary ``def`` handlers to its worker
pool; these legacy handlers are declared ``async def`` even though their work is
synchronous. This module replaces the already-built route dependant call with a
small async bridge that executes the original handler on a worker thread and
therefore keeps WebSocket frame delivery responsive.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import time
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_blocking_route_offload_hook_installed"
_ROUTE_SENTINEL = "_omnix_blocking_route_offload_registered"
_CALL_SENTINEL = "_omnix_blocking_route_offloaded"
_DEFAULT_LOG_THRESHOLD_MS = 25.0

# Exact method/path pairs observed doing synchronous persistence or provider work
# on the asyncio thread. Keep this allow-list narrow so genuinely asynchronous
# handlers are not moved into one thread per request without evidence.
BLOCKING_ROUTE_METHODS: dict[str, frozenset[str]] = {
    "/api/assistant/research/status": frozenset({"GET"}),
    "/api/chat/sessions": frozenset({"GET"}),
    "/api/chat/sessions/{session_id}": frozenset({"GET"}),
    "/api/chat/sessions/{session_id}/interaction": frozenset({"GET"}),
    "/api/chat/sessions/{session_id}/live-call/runtime": frozenset({"GET"}),
    "/api/chat/sessions/{session_id}/live-conversation/profile": frozenset({"GET"}),
    "/api/chat/sessions/{session_id}/messages": frozenset({"POST"}),
    "/api/settings": frozenset({"GET"}),
}
BLOCKING_ROUTE_PATHS = frozenset(BLOCKING_ROUTE_METHODS)


def _log_threshold_ms() -> float:
    try:
        value = float(
            os.environ.get(
                "OMNIX_BLOCKING_ROUTE_OFFLOAD_LOG_THRESHOLD_MS",
                str(_DEFAULT_LOG_THRESHOLD_MS),
            )
            or _DEFAULT_LOG_THRESHOLD_MS
        )
    except (TypeError, ValueError):
        value = _DEFAULT_LOG_THRESHOLD_MS
    return max(0.0, value)


def _invoke_endpoint(endpoint: Callable[..., Any], values: dict[str, Any]) -> Any:
    """Execute an async-style endpoint to completion on a worker thread."""
    result = endpoint(**values)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def _offloaded_call(
    endpoint: Callable[..., Any],
    *,
    route_path: str,
    route_name: str,
    methods: tuple[str, ...],
) -> Callable[..., Any]:
    @wraps(endpoint)
    async def call(**values: Any) -> Any:
        started_at = time.perf_counter()
        try:
            return await run_in_threadpool(_invoke_endpoint, endpoint, values)
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            if elapsed_ms >= _log_threshold_ms():
                stream_log(
                    "gateway-blocking-route-offload",
                    "runtime",
                    "blocking_route_offload_completed",
                    route_path=route_path,
                    route_name=route_name,
                    methods=methods,
                    elapsed_ms=round(elapsed_ms, 3),
                )

    setattr(call, _CALL_SENTINEL, True)
    return call


def offload_blocking_gateway_routes(gateway: FastAPI) -> list[str]:
    """Move measured synchronous handlers to the worker pool."""
    patched: list[str] = []
    for route in gateway.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = tuple(sorted(route.methods or ()))
        allowed_methods = BLOCKING_ROUTE_METHODS.get(route.path)
        if allowed_methods is None or not allowed_methods.intersection(methods):
            continue
        endpoint = route.dependant.call
        if endpoint is None or not inspect.iscoroutinefunction(endpoint):
            continue
        if getattr(endpoint, _CALL_SENTINEL, False):
            continue

        replacement = _offloaded_call(
            endpoint,
            route_path=route.path,
            route_name=route.name,
            methods=methods,
        )
        # The request-handler closure retains the Dependant object, so replacing
        # its call target is sufficient even though the route app was built
        # earlier. Updating endpoint keeps route introspection consistent.
        route.dependant.call = replacement
        route.endpoint = replacement
        patched.append(route.path)

    stream_log(
        "gateway-blocking-route-offload",
        "runtime",
        "blocking_route_offload_installed",
        patched_route_count=len(patched),
        patched_routes=sorted(patched),
    )
    return patched


def register_blocking_route_offload(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    async def startup() -> None:
        offload_blocking_gateway_routes(gateway)

    gateway.router.add_event_handler("startup", startup)


def install_blocking_route_offload_hook() -> None:
    """Register the offload scan for the composed Omnix gateway."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        is_gateway = kwargs.get("title") == "Omnix Web Gateway"
        if is_gateway or (args and args[0] == "Omnix Web Gateway"):
            register_blocking_route_offload(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
