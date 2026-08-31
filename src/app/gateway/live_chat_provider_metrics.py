"""Persist LM Studio usage, statistics, and low-latency text deltas."""
from __future__ import annotations

import time
from functools import wraps
from typing import Any, Iterator

from app.chat.memory_commands import parse_memory_command
from app.chat.prompt_store import (
    ChatSessionStore as PromptChatSessionStore,
    route_typed_stream_boundary,
)
from app.chat.provider_metrics import merge_provider_response_metrics
from app.chat.routing_deadline import provider_turn_deadline, remaining_turn_seconds
from app.chat.store import _model_key, _provider_key

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_provider_metrics_installed"
_FIRST_TEXT_MAX_CHARS = 48
_STEADY_TEXT_TARGET_CHARS = 32
_STEADY_TEXT_MAX_CHARS = 96
_SENTENCE_BOUNDARIES = frozenset(".!?。！？\n")


class _LowLatencyTextChunker:
    """Emit the first complete lexical unit without waiting for a sentence.

    Provider deltas may split a word across multiple chunks. The chunker waits for
    a whitespace or punctuation boundary before the first emission, then groups
    later deltas into modest boundary-safe chunks. This keeps the existing browser
    text-merging contract readable while removing sentence-level first-token delay.
    """

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


def _resolve_provider(provider_id: str | None) -> Any:
    from app import shared

    return shared.get_provider(_provider_key(provider_id))


def _is_lmstudio_provider(provider: Any) -> bool:
    return str(getattr(provider, "provider_name", "")).strip().lower() == "lmstudio"


def _is_lmstudio(provider_id: str | None) -> bool:
    return _is_lmstudio_provider(_resolve_provider(provider_id))


def _metrics_provider_id(provider_id: str | None) -> str:
    return provider_id or "lmstudio"


def _generate_lmstudio_reply(
    self: PromptChatSessionStore,
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]],
    provider: Any | None = None,
    routing_deadline_at: float | None = None,
) -> dict[str, Any]:
    from app.providers import ChatMessage as ProviderMessage

    provider = provider or _resolve_provider(provider_id)
    if provider is None:
        raise RuntimeError("Chat provider is not available")
    assembly, rendered = self.build_provider_prompt(session, user_message, context_items)
    messages = [
        ProviderMessage(role=message.role, content=message.content)
        for message in rendered.messages
    ]
    model_name = _model_key(model_id)
    from app.providers.structured.errors import ProviderTimeout

    deadline = provider_turn_deadline(
        provider_id,
        session_provider_id=getattr(session, "provider_id", None),
        existing_deadline_at=routing_deadline_at,
    )
    remaining = remaining_turn_seconds(deadline)
    if remaining is not None and remaining <= 0:
        raise ProviderTimeout("chat turn deadline has expired")
    completion_kwargs: dict[str, Any] = {"include_metrics": True}
    if remaining is not None:
        completion_kwargs["request_timeout_seconds"] = remaining
    response = provider.chat_completion(
        messages=messages,
        model=model_name,
        stream=False,
        **completion_kwargs,
    )
    content = (getattr(response, "content", "") or "").strip()
    if not content:
        raise RuntimeError("Chat response was empty")

    metadata: dict[str, Any] = {
        "generation_status": "completed",
        "provider_id": provider_id,
        "model_id": model_id,
        "resolved_model": getattr(response, "model", None) or model_name,
        **self._active_memory_metadata(assembly, rendered),
        **self._active_history_metadata(assembly),
    }
    usage = getattr(response, "usage", None)
    if usage:
        metadata["usage"] = usage
    provider_metrics = merge_provider_response_metrics(
        None,
        response,
        provider_id=_metrics_provider_id(provider_id),
    )
    if provider_metrics:
        metadata["provider_metrics"] = provider_metrics
    thinking = getattr(response, "thinking", None) or getattr(response, "reasoning", None)
    if thinking:
        metadata["thinking"] = thinking
    return {"content": content, "metadata": metadata}


def _stream_lmstudio_reply(
    self: PromptChatSessionStore,
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]] | None,
    provider: Any | None = None,
    routing_deadline_at: float | None = None,
) -> Iterator[dict[str, Any]]:
    from app.providers import ChatMessage as ProviderMessage

    started = time.perf_counter()
    provider = provider or _resolve_provider(provider_id)
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
    deadline = provider_turn_deadline(
        provider_id,
        session_provider_id=getattr(session, "provider_id", None),
        existing_deadline_at=routing_deadline_at,
    )
    remaining_budget = remaining_turn_seconds(deadline)
    if remaining_budget is not None and remaining_budget <= 0:
        from app.providers.structured.errors import ProviderTimeout

        raise ProviderTimeout("chat turn deadline has expired")
    completion_kwargs: dict[str, Any] = {"include_metrics": True}
    if remaining_budget is not None:
        completion_kwargs["request_timeout_seconds"] = remaining_budget
    response = provider.chat_completion(
        messages=messages,
        model=model_name,
        stream=True,
        **completion_kwargs,
    )
    chunker = _LowLatencyTextChunker()
    full_text = ""
    resolved_model = model_name
    usage = None
    provider_metrics: dict[str, Any] = {}
    provider_iteration_started = time.perf_counter()
    first_provider_text_ms: float | None = None
    first_client_chunk_ms: float | None = None

    for chunk in response:
        resolved_model = getattr(chunk, "model", None) or resolved_model
        usage = getattr(chunk, "usage", None) or usage
        provider_metrics = merge_provider_response_metrics(
            provider_metrics,
            chunk,
            provider_id=_metrics_provider_id(provider_id),
        )
        text = getattr(chunk, "content", "") or ""
        if not text:
            continue
        if first_provider_text_ms is None:
            first_provider_text_ms = (time.perf_counter() - provider_iteration_started) * 1000.0
            stream_log(
                "gateway-live-chat-first-token",
                "runtime",
                "live_chat_lmstudio_first_provider_text",
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
                    "live_chat_lmstudio_first_client_chunk",
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

    native_ttft = provider_metrics.get("time_to_first_token_seconds")
    native_generation = provider_metrics.get("generation_time_seconds")
    stream_log(
        "gateway-live-chat-first-token",
        "runtime",
        "live_chat_lmstudio_stream_completed",
        prompt_build_ms=round(prompt_build_ms, 3),
        provider_first_text_ms=(
            round(first_provider_text_ms, 3) if first_provider_text_ms is not None else None
        ),
        first_client_chunk_ms=(
            round(first_client_chunk_ms, 3) if first_client_chunk_ms is not None else None
        ),
        native_ttft_ms=(
            round(float(native_ttft) * 1000.0, 3)
            if isinstance(native_ttft, (int, float))
            else None
        ),
        native_generation_ms=(
            round(float(native_generation) * 1000.0, 3)
            if isinstance(native_generation, (int, float))
            else None
        ),
        output_tokens=provider_metrics.get("output_tokens"),
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
            **({"provider_metrics": provider_metrics} if provider_metrics else {}),
        },
    }


def install_live_chat_provider_metrics_hook() -> None:
    """Install LM Studio metric capture before the pre-token retry wrapper."""
    if getattr(PromptChatSessionStore, _HOOK_SENTINEL, False):
        return

    original_generate = PromptChatSessionStore._generate_provider_reply
    original_stream = PromptChatSessionStore.stream_provider_reply_chunks

    @wraps(original_generate)
    def patched_generate(
        self: PromptChatSessionStore,
        session: Any,
        user_message: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]],
        routing_deadline_at: float | None = None,
    ) -> dict[str, Any]:
        provider = _resolve_provider(provider_id)
        if not _is_lmstudio_provider(provider):
            generate_kwargs: dict[str, Any] = {
                "provider_id": provider_id,
                "model_id": model_id,
                "context_items": context_items,
            }
            if routing_deadline_at is not None:
                generate_kwargs["routing_deadline_at"] = routing_deadline_at
            return original_generate(
                self,
                session,
                user_message,
                **generate_kwargs,
            )
        return _generate_lmstudio_reply(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
            provider=provider,
            routing_deadline_at=routing_deadline_at,
        )

    @wraps(original_stream)
    def patched_stream(
        self: PromptChatSessionStore,
        session: Any,
        user_message: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]] | None = None,
        routing_deadline_at: float | None = None,
    ) -> Iterator[dict[str, Any]]:
        provider = _resolve_provider(provider_id)
        if parse_memory_command(user_message.content) is not None:
            stream_kwargs: dict[str, Any] = {
                "provider_id": provider_id,
                "model_id": model_id,
                "context_items": context_items,
            }
            if routing_deadline_at is not None:
                stream_kwargs["routing_deadline_at"] = routing_deadline_at
            yield from original_stream(
                self,
                session,
                user_message,
                **stream_kwargs,
            )
            return
        routing_deadline_at = provider_turn_deadline(
            provider_id,
            session_provider_id=getattr(session, "provider_id", None),
            existing_deadline_at=routing_deadline_at,
        )
        boundary_events = route_typed_stream_boundary(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
            routing_deadline_at=routing_deadline_at,
        )
        if boundary_events is not None:
            yield from boundary_events
            return
        if not _is_lmstudio_provider(provider):
            stream_kwargs = {
                "provider_id": provider_id,
                "model_id": model_id,
                "context_items": context_items,
            }
            if routing_deadline_at is not None:
                stream_kwargs["routing_deadline_at"] = routing_deadline_at
            yield from original_stream(self, session, user_message, **stream_kwargs)
            return
        yield from _stream_lmstudio_reply(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
            provider=provider,
            routing_deadline_at=routing_deadline_at,
        )

    PromptChatSessionStore._generate_provider_reply = patched_generate
    PromptChatSessionStore.stream_provider_reply_chunks = patched_stream
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
