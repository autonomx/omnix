"""Recover live chat turns that fail before the first provider token.

Live voice users should not need to repeat an utterance because a provider stream
failed before yielding any text. Retries are deliberately disabled after the
first text chunk so a partially delivered answer can never be duplicated.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from functools import wraps
from typing import Any

from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_stream_retry_installed"
_DEFAULT_STREAM_ATTEMPTS = 3
_MAX_STREAM_ATTEMPTS = 5


class EmptyProviderStreamError(RuntimeError):
    """Raised when a provider completes without delivering assistant text."""


def _stream_attempts() -> int:
    try:
        value = int(
            os.environ.get(
                "OMNIX_LIVE_CHAT_STREAM_ATTEMPTS",
                str(_DEFAULT_STREAM_ATTEMPTS),
            )
            or _DEFAULT_STREAM_ATTEMPTS
        )
    except (TypeError, ValueError):
        value = _DEFAULT_STREAM_ATTEMPTS
    return max(1, min(_MAX_STREAM_ATTEMPTS, value))


def _event_text(event: dict[str, Any]) -> str:
    if event.get("type") == "text_chunk":
        return str(event.get("text") or "").strip()
    if event.get("type") == "complete":
        return str(event.get("content") or "").strip()
    return ""


def retry_provider_stream(
    stream_factory: Callable[[], Iterator[dict[str, Any]]],
    fallback_factory: Callable[[], dict[str, Any]] | None,
    *,
    attempts: int,
) -> Iterator[dict[str, Any]]:
    """Retry failures or empty completion only before any text is delivered."""
    max_attempts = max(1, min(_MAX_STREAM_ATTEMPTS, int(attempts)))
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        delivered_text = False
        saw_completion = False
        try:
            for event in stream_factory():
                event_type = event.get("type")
                text = _event_text(event)
                if event_type == "text_chunk" and text:
                    delivered_text = True
                    yield event
                    continue
                if event_type == "complete":
                    if not text and not delivered_text:
                        raise EmptyProviderStreamError(
                            "Chat provider stream completed without assistant text"
                        )
                    if text and not delivered_text:
                        # Some providers return content only on completion. Preserve
                        # the streaming contract by synthesizing one text chunk.
                        delivered_text = True
                        yield {"type": "text_chunk", "text": text}
                    saw_completion = True
                    yield event
                    break
                yield event
            if saw_completion:
                if attempt > 1:
                    stream_log(
                        "gateway-live-chat-stream",
                        "runtime",
                        "live_chat_stream_retry_recovered",
                        attempt=attempt,
                        max_attempts=max_attempts,
                    )
                return
            raise EmptyProviderStreamError(
                "Chat provider stream closed before completion"
            )
        except GeneratorExit:
            raise
        except Exception as exc:
            last_error = exc
            if delivered_text:
                stream_log(
                    "gateway-live-chat-stream",
                    "runtime",
                    "live_chat_stream_retry_skipped_after_text",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=type(exc).__name__,
                )
                raise
            if attempt < max_attempts:
                stream_log(
                    "gateway-live-chat-stream",
                    "runtime",
                    "live_chat_stream_retry_scheduled",
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    max_attempts=max_attempts,
                    error_type=type(exc).__name__,
                )
                continue

    if fallback_factory is not None:
        try:
            fallback = fallback_factory()
            content = str(fallback.get("content") or "").strip()
            if not content:
                raise EmptyProviderStreamError(
                    "Chat provider fallback completed without assistant text"
                )
            metadata = fallback.get("metadata")
            stream_log(
                "gateway-live-chat-stream",
                "runtime",
                "live_chat_stream_fallback_completed",
                max_attempts=max_attempts,
                response_chars=len(content),
            )
            yield {"type": "text_chunk", "text": content}
            yield {
                "type": "complete",
                "content": content,
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
            return
        except Exception as exc:
            last_error = exc

    stream_log(
        "gateway-live-chat-stream",
        "runtime",
        "live_chat_stream_retry_exhausted",
        max_attempts=max_attempts,
        error_type=type(last_error).__name__ if last_error is not None else "unknown",
    )
    if last_error is not None:
        raise last_error
    raise RuntimeError("Chat provider stream failed without an error")


def install_live_chat_stream_retry_hook() -> None:
    """Wrap PromptAssembly provider streaming once for every chat store."""
    if getattr(PromptChatSessionStore, _HOOK_SENTINEL, False):
        return

    original = PromptChatSessionStore.stream_provider_reply_chunks

    @wraps(original)
    def patched(
        self: PromptChatSessionStore,
        session: Any,
        user_message: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        def stream_factory() -> Iterator[dict[str, Any]]:
            return original(
                self,
                session,
                user_message,
                provider_id=provider_id,
                model_id=model_id,
                context_items=context_items,
            )

        def fallback_factory() -> dict[str, Any]:
            return self._generate_provider_reply(
                session,
                user_message,
                provider_id=provider_id,
                model_id=model_id,
                context_items=context_items or [],
            )

        yield from retry_provider_stream(
            stream_factory,
            fallback_factory,
            attempts=_stream_attempts(),
        )

    PromptChatSessionStore.stream_provider_reply_chunks = patched
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
