"""Configure server-sent event responses for immediate incremental delivery."""
from __future__ import annotations

import os
from collections.abc import AsyncIterable, Iterable
from typing import Any

from starlette.responses import StreamingResponse

_HOOK_SENTINEL = "_omnix_live_sse_transport_installed"
_DEFAULT_PREAMBLE_BYTES = 2_048
_MAX_PREAMBLE_BYTES = 8_192
_ORIGINAL_STREAMING_RESPONSE_INIT = StreamingResponse.__init__


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


def _event_stream_headers(headers: dict[str, str] | None) -> dict[str, str]:
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
        if isinstance(content, AsyncIterable):
            content = _prepend_async(content, preamble)
        else:
            content = _prepend_sync(content, preamble)
        headers = _event_stream_headers(headers)
    _ORIGINAL_STREAMING_RESPONSE_INIT(
        self,
        content,
        status_code=status_code,
        headers=headers,
        media_type=media_type,
        background=background,
    )


def install_live_sse_transport_hook() -> None:
    """Install one bounded flush prelude for every SSE response."""
    if getattr(StreamingResponse, _HOOK_SENTINEL, False):
        return
    StreamingResponse.__init__ = _patched_streaming_response_init
    setattr(StreamingResponse, _HOOK_SENTINEL, True)


__all__ = ["install_live_sse_transport_hook"]
