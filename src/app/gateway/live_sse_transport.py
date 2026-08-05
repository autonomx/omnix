"""Configure server-sent event responses for immediate incremental delivery."""
from __future__ import annotations

import inspect
import os
from collections.abc import AsyncIterable, Iterable
from contextvars import ContextVar
from functools import wraps
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from .live_chat_async_sse_bridge import eager_async_sse_stream
from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_sse_transport_installed"
_FASTAPI_HOOK_SENTINEL = "_omnix_live_chat_sse_route_hook_installed"
_ROUTE_SENTINEL = "_omnix_live_chat_sse_route_registered"
_CALL_SENTINEL = "_omnix_live_chat_sse_route_wrapped"
_DEFAULT_PREAMBLE_BYTES = 2_048
_MAX_PREAMBLE_BYTES = 8_192
_TRANSPORT_VERSION = "immediate-v3"
_LIVE_CHAT_STREAM_PATH = "/api/chat/sessions/{session_id}/messages/stream"
_ORIGINAL_STREAMING_RESPONSE_INIT = StreamingResponse.__init__
_LIVE_CHAT_STREAM_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "omnix_live_chat_stream_context",
    default=None,
)


def _configured_preamble_bytes() -> int:
    raw = os.environ.get("OMNIX_SSE_FLUSH_PREAMBLE_BYTES")
    try:
        value = int(raw) if raw is not None else _DEFAULT_PREAMBLE_BYTES
    except (TypeError, ValueError):
        value = _DEFAULT_PREAMBLE_BYTES
    return max(0, min(_MAX_PREAMBLE_BYTES, value))


def _flush_preamble(size: int) -> bytes:
    if size <= 0:
        return b""
    if size <= 3:
        return b":\n\n"[:size]
    return b":" + (b" " * (size - 3)) + b"\n\n"


def _is_event_stream(media_type: str | None, headers: dict[str, str] | None) -> bool:
    if str(media_type or "").lower().startswith("text/event-stream"):
        return True
    for name, value in (headers or {}).items():
        if name.lower() == "content-type" and str(value).lower().startswith("text/event-stream"):
            return True
    return False


def _event_stream_headers(
    headers: dict[str, str] | None,
    *,
    execution_mode: str,
) -> dict[str, str]:
    result = dict(headers or {})
    cache_key = next((name for name in result if name.lower() == "cache-control"), "Cache-Control")
    cache_tokens = {
        token.strip().lower()
        for token in str(result.get(cache_key, "")).split(",")
        if token.strip()
    }
    cache_tokens.update({"no-cache", "no-transform"})
    result[cache_key] = ", ".join(sorted(cache_tokens))
    if not any(name.lower() == "x-accel-buffering" for name in result):
        result["X-Accel-Buffering"] = "no"
    if not any(name.lower() == "connection" for name in result):
        result["Connection"] = "keep-alive"
    result["X-Omnix-SSE-Transport"] = _TRANSPORT_VERSION
    result["X-Omnix-SSE-Execution"] = execution_mode
    return result


async def _prepend_async(content: AsyncIterable[Any], preamble: bytes):
    if preamble:
        yield preamble
    async for chunk in content:
        yield chunk


def _prepend_sync(content: Iterable[Any], preamble: bytes):
    if preamble:
        yield preamble
    yield from content


def _voice_turn_id(request: Any) -> str | None:
    user_turn_id = str(getattr(request, "user_turn_id", "") or "").strip()
    prefix = "voice-user-turn:"
    if not user_turn_id.startswith(prefix):
        return None
    value = user_turn_id[len(prefix):].strip()
    return value or None


def _route_context(values: dict[str, Any]) -> dict[str, Any]:
    request = values.get("request")
    return {
        "route_path": _LIVE_CHAT_STREAM_PATH,
        "session_id": str(values.get("session_id") or "").strip() or None,
        "user_turn_id": str(getattr(request, "user_turn_id", "") or "").strip() or None,
        "speech_segment_id": str(getattr(request, "speech_segment_id", "") or "").strip() or None,
        "voice_turn_id": _voice_turn_id(request),
    }


def _wrap_live_chat_stream_route(route: APIRoute) -> bool:
    endpoint = route.dependant.call
    if endpoint is None or getattr(endpoint, _CALL_SENTINEL, False):
        return False

    @wraps(endpoint)
    async def call(**values: Any) -> Any:
        context = _route_context(values)
        token = _LIVE_CHAT_STREAM_CONTEXT.set(context)
        stream_log(
            "gateway-live-chat-async-sse",
            "runtime",
            "live_chat_sse_route_entered",
            **context,
        )
        try:
            response = endpoint(**values)
            if inspect.isawaitable(response):
                response = await response
            stream_log(
                "gateway-live-chat-async-sse",
                "runtime",
                "live_chat_sse_response_created",
                response_type=type(response).__name__,
                **context,
            )
            return response
        finally:
            _LIVE_CHAT_STREAM_CONTEXT.reset(token)

    setattr(call, _CALL_SENTINEL, True)
    route.dependant.call = call
    route.endpoint = call
    return True


def install_live_chat_sse_route_execution(gateway: FastAPI) -> list[str]:
    """Mark only the accepted chat stream for eager producer execution."""

    patched: list[str] = []
    for route in gateway.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path != _LIVE_CHAT_STREAM_PATH or "POST" not in (route.methods or set()):
            continue
        if _wrap_live_chat_stream_route(route):
            patched.append(route.path)
    stream_log(
        "gateway-live-chat-async-sse",
        "runtime",
        "live_chat_sse_route_execution_installed",
        patched_route_count=len(patched),
        patched_routes=patched,
    )
    return patched


def _register_live_chat_sse_route_execution(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    async def startup() -> None:
        install_live_chat_sse_route_execution(gateway)

    gateway.router.add_event_handler("startup", startup)


def _patched_streaming_response_init(
    self: StreamingResponse,
    content: Any,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    media_type: str | None = None,
    background: Any | None = None,
) -> None:
    if _is_event_stream(media_type, headers):
        preamble = _flush_preamble(_configured_preamble_bytes())
        route_context = _LIVE_CHAT_STREAM_CONTEXT.get()
        if isinstance(content, AsyncIterable):
            content = _prepend_async(content, preamble)
            execution_mode = "async-native"
        elif route_context is not None:
            sync_content = content

            def produce() -> Iterable[Any]:
                return _prepend_sync(sync_content, preamble)

            content = eager_async_sse_stream(
                produce,
                diagnostic_context=route_context,
            )
            execution_mode = "eager-route"
        else:
            content = _prepend_sync(content, preamble)
            execution_mode = "starlette-sync"
        headers = _event_stream_headers(headers, execution_mode=execution_mode)
    _ORIGINAL_STREAMING_RESPONSE_INIT(
        self,
        content,
        status_code=status_code,
        headers=headers,
        media_type=media_type,
        background=background,
    )


def install_live_sse_transport_hook() -> None:
    """Install immediate SSE headers and route-scoped eager chat execution."""

    if not getattr(StreamingResponse, _HOOK_SENTINEL, False):
        StreamingResponse.__init__ = _patched_streaming_response_init
        setattr(StreamingResponse, _HOOK_SENTINEL, True)

    if getattr(FastAPI, _FASTAPI_HOOK_SENTINEL, False):
        return
    original_init = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        title = kwargs.get("title") or (args[0] if args else None)
        if title == "Omnix Web Gateway":
            _register_live_chat_sse_route_execution(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _FASTAPI_HOOK_SENTINEL, True)


__all__ = [
    "install_live_chat_sse_route_execution",
    "install_live_sse_transport_hook",
]
