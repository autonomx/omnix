"""Emit provider text after the first complete lexical unit.

The legacy chat stream waited for sentence-ending punctuation before yielding any
text. That made a fast provider look slow and delayed live-call TTS. This hook is
installed before provider-specific wrappers so every ordinary provider gets the
same boundary-safe first-text policy while LM Studio retains its richer metrics
path.
"""
from __future__ import annotations

import time
from functools import wraps
from typing import Any, Iterator

from app.chat.memory_commands import parse_memory_command
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.chat.store import _model_key, _provider_key

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_low_latency_stream_installed"
_FIRST_TEXT_MAX_CHARS = 48
_STEADY_TEXT_TARGET_CHARS = 32
_STEADY_TEXT_MAX_CHARS = 96
_SENTENCE_BOUNDARIES = frozenset(".!?。！？\n")


class LowLatencyTextChunker:
    """Keep split words intact while releasing the first lexical unit early."""

    def __init__(self) -> None:
        self._pending = ""
        self._emitted = False

    def push(self, text: str) -> list[str]:
        if text:
            self._pending += text
        ready: list[str] = []
        while self._pending:
            cut = self._next_cut()
            if cut is None:
                break
            chunk = self._pending[:cut]
            self._pending = self._pending[cut:]
            if not chunk.strip():
                continue
            ready.append(chunk)
            self._emitted = True
        return ready

    def flush(self) -> str:
        pending = self._pending
        self._pending = ""
        return pending

    def _next_cut(self) -> int | None:
        sentence_cut = _first_sentence_cut(self._pending)
        if not self._emitted:
            lexical_cut = _first_lexical_cut(self._pending)
            candidates = [cut for cut in (sentence_cut, lexical_cut) if cut is not None]
            if candidates:
                return min(candidates)
            if len(self._pending) >= _FIRST_TEXT_MAX_CHARS:
                return _FIRST_TEXT_MAX_CHARS
            return None

        if sentence_cut is not None:
            return sentence_cut
        if len(self._pending) < _STEADY_TEXT_TARGET_CHARS:
            return None
        boundary_cut = _last_whitespace_cut(
            self._pending,
            minimum=_STEADY_TEXT_TARGET_CHARS,
            maximum=_STEADY_TEXT_MAX_CHARS,
        )
        if boundary_cut is not None:
            return boundary_cut
        if len(self._pending) >= _STEADY_TEXT_MAX_CHARS:
            return _STEADY_TEXT_MAX_CHARS
        return None


def _first_lexical_cut(text: str) -> int | None:
    saw_text = False
    for index, character in enumerate(text):
        if character.isspace():
            if saw_text:
                end = index + 1
                while end < len(text) and text[end].isspace():
                    end += 1
                return end
            continue
        saw_text = True
    return None


def _first_sentence_cut(text: str) -> int | None:
    for index, character in enumerate(text):
        if character not in _SENTENCE_BOUNDARIES:
            continue
        end = index + 1
        while end < len(text) and text[end].isspace():
            end += 1
        return end
    return None


def _last_whitespace_cut(text: str, *, minimum: int, maximum: int) -> int | None:
    upper = min(len(text), maximum)
    cut: int | None = None
    for index in range(minimum, upper):
        if text[index].isspace():
            cut = index + 1
    return cut


def _stream_low_latency_reply(
    self: PromptChatSessionStore,
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]] | None,
) -> Iterator[dict[str, Any]]:
    from app import shared
    from app.providers import ChatMessage as ProviderMessage

    started = time.perf_counter()
    provider = shared.get_provider(_provider_key(provider_id))
    if provider is None:
        raise RuntimeError("Chat provider is not available")

    prompt_started = time.perf_counter()
    assembly, rendered = self.build_provider_prompt(
        session,
        user_message,
        context_items or [],
    )
    prompt_build_ms = (time.perf_counter() - prompt_started) * 1000.0
    messages = [
        ProviderMessage(role=message.role, content=message.content)
        for message in rendered.messages
    ]
    model_name = _model_key(model_id)
    response = provider.chat_completion(messages=messages, model=model_name, stream=True)
    chunker = LowLatencyTextChunker()
    full_text = ""
    resolved_model = model_name
    usage = None
    provider_iteration_started = time.perf_counter()
    first_provider_text_ms: float | None = None
    first_client_chunk_ms: float | None = None

    for chunk in response:
        resolved_model = getattr(chunk, "model", None) or resolved_model
        usage = getattr(chunk, "usage", None) or usage
        text = getattr(chunk, "content", "") or ""
        if not text:
            continue
        if first_provider_text_ms is None:
            first_provider_text_ms = (time.perf_counter() - provider_iteration_started) * 1000.0
            stream_log(
                "gateway-live-chat-first-token",
                "runtime",
                "live_chat_first_provider_text",
                provider_id=provider_id,
                prompt_build_ms=round(prompt_build_ms, 3),
                provider_first_text_ms=round(first_provider_text_ms, 3),
            )
        full_text += text
        for ready in chunker.push(text):
            if first_client_chunk_ms is None:
                first_client_chunk_ms = (time.perf_counter() - started) * 1000.0
                stream_log(
                    "gateway-live-chat-first-token",
                    "runtime",
                    "live_chat_first_client_chunk",
                    provider_id=provider_id,
                    first_client_chunk_ms=round(first_client_chunk_ms, 3),
                    prompt_build_ms=round(prompt_build_ms, 3),
                    provider_first_text_ms=(
                        round(first_provider_text_ms, 3)
                        if first_provider_text_ms is not None
                        else None
                    ),
                    text_chars=len(ready),
                )
            yield {"type": "text_chunk", "text": ready}

    remaining = chunker.flush()
    if remaining:
        if first_client_chunk_ms is None:
            first_client_chunk_ms = (time.perf_counter() - started) * 1000.0
        yield {"type": "text_chunk", "text": remaining}

    stream_log(
        "gateway-live-chat-first-token",
        "runtime",
        "live_chat_provider_stream_completed",
        provider_id=provider_id,
        prompt_build_ms=round(prompt_build_ms, 3),
        provider_first_text_ms=(
            round(first_provider_text_ms, 3) if first_provider_text_ms is not None else None
        ),
        first_client_chunk_ms=(
            round(first_client_chunk_ms, 3) if first_client_chunk_ms is not None else None
        ),
        total_ms=round((time.perf_counter() - started) * 1000.0, 3),
    )
    yield {
        "type": "complete",
        "content": full_text.strip(),
        "metadata": {
            "generation_status": "completed",
            "provider_id": provider_id,
            "model_id": model_id,
            "resolved_model": resolved_model,
            **self._active_memory_metadata(assembly, rendered),
            **self._active_history_metadata(assembly),
            **({"usage": usage} if usage else {}),
        },
    }


def install_live_chat_low_latency_stream_hook() -> None:
    """Replace sentence-buffered ordinary provider streaming once."""

    if getattr(PromptChatSessionStore, _HOOK_SENTINEL, False):
        return
    original_stream = PromptChatSessionStore.stream_provider_reply_chunks

    @wraps(original_stream)
    def patched_stream(
        self: PromptChatSessionStore,
        session: Any,
        user_message: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        if parse_memory_command(user_message.content) is not None:
            yield from original_stream(
                self,
                session,
                user_message,
                provider_id=provider_id,
                model_id=model_id,
                context_items=context_items,
            )
            return
        yield from _stream_low_latency_reply(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
        )

    PromptChatSessionStore.stream_provider_reply_chunks = patched_stream
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
