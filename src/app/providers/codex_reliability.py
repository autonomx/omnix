from __future__ import annotations

"""Protocol reliability adapters for the ChatGPT Codex app-server provider.

The app-server can emit transient ``error`` notifications with ``willRetry``
while it reconnects. Those notifications are progress, not terminal turn
failures. Codex also supports ``outputSchema`` on ``turn/start``; projecting
Omnix response-format contracts there is substantially stronger than prompt-only
JSON instructions.

This module patches only those two protocol seams. The provider remains the
owner of process lifecycle, thread identity, tool bridging, tracing and timeout
handling.
"""

import threading
import time
from collections.abc import Iterator
from typing import Any

from .chatgpt_codex_provider import ChatGPTCodexProvider


_INSTALLED = False
_ORIGINAL_CHAT_COMPLETION = ChatGPTCodexProvider.chat_completion
_ORIGINAL_NEXT_EVENT = ChatGPTCodexProvider._next_event
_ORIGINAL_REQUEST = ChatGPTCodexProvider._request
_SCHEMA_CONTEXT = threading.local()


def _schema_from_response_format(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    response_type = str(value.get("type") or "").strip().casefold()
    if response_type == "json_schema":
        wrapper = value.get("json_schema")
        if isinstance(wrapper, dict) and isinstance(wrapper.get("schema"), dict):
            return dict(wrapper["schema"])
        return None
    if response_type == "json_object":
        return {"type": "object"}
    return None


def _will_retry(event: dict[str, Any]) -> bool:
    if str(event.get("method") or "") != "error":
        return False
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    candidates = (
        params.get("willRetry"),
        params.get("will_retry"),
        (params.get("error") or {}).get("willRetry")
        if isinstance(params.get("error"), dict)
        else None,
        (params.get("error") or {}).get("will_retry")
        if isinstance(params.get("error"), dict)
        else None,
    )
    return any(value is True for value in candidates)


def _patched_next_event(self, timeout: float, *args, **kwargs):
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Preserve the provider's canonical timeout/error formatting.
            return _ORIGINAL_NEXT_EVENT(self, 0.0, *args, **kwargs)
        event = _ORIGINAL_NEXT_EVENT(self, remaining, *args, **kwargs)
        if _will_retry(event):
            continue
        return event


def _patched_request(self, method: str, params: dict[str, Any], *args, **kwargs):
    if method == "turn/start":
        output_schema = getattr(_SCHEMA_CONTEXT, "output_schema", None)
        if isinstance(output_schema, dict) and output_schema:
            params = dict(params)
            params.setdefault("outputSchema", output_schema)
    return _ORIGINAL_REQUEST(self, method, params, *args, **kwargs)


def _set_schema(schema: dict[str, Any] | None):
    sentinel = object()
    previous = getattr(_SCHEMA_CONTEXT, "output_schema", sentinel)
    _SCHEMA_CONTEXT.output_schema = schema
    return sentinel, previous


def _restore_schema(sentinel, previous) -> None:
    if previous is sentinel:
        with suppress_attribute_error():
            delattr(_SCHEMA_CONTEXT, "output_schema")
    else:
        _SCHEMA_CONTEXT.output_schema = previous


class suppress_attribute_error:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, _tb):
        return exc_type is AttributeError


def _patched_chat_completion(self, messages, model=None, stream=False, **kwargs):
    output_schema = _schema_from_response_format(kwargs.get("response_format"))
    if not stream:
        sentinel, previous = _set_schema(output_schema)
        try:
            return _ORIGINAL_CHAT_COMPLETION(
                self,
                messages,
                model=model,
                stream=False,
                **kwargs,
            )
        finally:
            _restore_schema(sentinel, previous)

    def traced_schema_stream() -> Iterator:
        sentinel, previous = _set_schema(output_schema)
        try:
            inner = _ORIGINAL_CHAT_COMPLETION(
                self,
                messages,
                model=model,
                stream=True,
                **kwargs,
            )
            yield from inner
        finally:
            _restore_schema(sentinel, previous)

    return traced_schema_stream()


def install_codex_reliability() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ChatGPTCodexProvider._next_event = _patched_next_event
    ChatGPTCodexProvider._request = _patched_request
    ChatGPTCodexProvider.chat_completion = _patched_chat_completion
    _INSTALLED = True


__all__ = ["install_codex_reliability"]
