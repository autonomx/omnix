"""Emit provider text with immediate typed-chat and lexical voice delivery.

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
from app.chat.prompt_store import route_typed_stream_boundary
from app.chat.routing_deadline import provider_turn_deadline, remaining_turn_seconds
from app.chat.store import _model_key, _provider_key

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_low_latency_stream_installed"
_FIRST_TEXT_MAX_CHARS = 48
_STEADY_TEXT_TARGET_CHARS = 32
_STEADY_TEXT_MAX_CHARS = 96
_SENTENCE_BOUNDARIES = frozenset(".!?。！？\n")


class LowLatencyTextChunker:
    """Keep spoken fragments lexical while allowing typed chat to paint instantly."""

    def __init__(self, *, emit_initial_fragment: bool = False) -> None:
        self._pending = ""
        self._emitted = False
        self._emit_initial_fragment = emit_initial_fragment

    def push(self, text: str) -> list[str]:
        if text:
            self._pending += text
        ready: list[str] = []
        while self._pending:
            if self._emit_initial_fragment and not self._emitted:
                chunk = self._pending
                self._pending = ""
                if not chunk.strip():
                    continue
                ready.append(chunk)
                self._emitted = True
                continue
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


def _is_live_voice_turn(user_message: Any) -> bool:
    metadata = getattr(user_message, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    if str(metadata.get("speech_segment_id") or "").strip():
        return True
    return str(metadata.get("user_turn_id") or "").startswith("voice-user-turn:")


def _json_safe_provider_value(value: Any) -> Any:
    """Convert provider metadata into plain values safe for SSE JSON encoding."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe_provider_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_provider_value(item) for item in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _json_safe_provider_value(model_dump(mode="json"))
        except TypeError:
            return _json_safe_provider_value(model_dump())

    dictionary = getattr(value, "dict", None)
    if callable(dictionary):
        return _json_safe_provider_value(dictionary())

    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        return {
            str(key): _json_safe_provider_value(item)
            for key, item in attributes.items()
            if not str(key).startswith("_")
        }
    return str(value)


def _stream_low_latency_reply(
    self: PromptChatSessionStore,
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]] | None,
    routing_deadline_at: float | None = None,
) -> Iterator[dict[str, Any]]:
    from app import shared
    from app.providers import ChatMessage as ProviderMessage

    started = time.perf_counter()
    provider_name = _provider_key(provider_id)
    provider = shared.get_provider(provider_name)
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
    completion_kwargs: dict[str, Any] = {}
    if provider_name == "chatgpt_codex":
        conversation_id = str(getattr(session, "id", "") or "").strip()
        if conversation_id:
            completion_kwargs["conversation_id"] = conversation_id
    routing_deadline_at = provider_turn_deadline(
        provider_id,
        session_provider_id=getattr(session, "provider_id", None),
        existing_deadline_at=routing_deadline_at,
    )
    remaining = remaining_turn_seconds(routing_deadline_at)
    if remaining is not None:
        if remaining <= 0:
            from app.providers.structured.errors import ProviderTimeout

            raise ProviderTimeout("chat turn deadline has expired")
        completion_kwargs["request_timeout_seconds"] = remaining
    response = provider.chat_completion(
        messages=messages,
        model=model_name,
        stream=True,
        **completion_kwargs,
    )
    chunker = LowLatencyTextChunker(
        emit_initial_fragment=not _is_live_voice_turn(user_message),
    )
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

    completion_log_started = time.perf_counter()
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
    completion_log_ms = (time.perf_counter() - completion_log_started) * 1000.0

    terminal_metadata_started = time.perf_counter()
    usage_payload = _json_safe_provider_value(usage)
    memory_metadata = self._active_memory_metadata(assembly, rendered)
    history_metadata = self._active_history_metadata(assembly)
    terminal_metadata_ms = (time.perf_counter() - terminal_metadata_started) * 1000.0
    yield {
        "type": "complete",
        "content": full_text.strip(),
        "diagnostics": {
            "provider_completion_log_ms": round(completion_log_ms, 3),
            "terminal_metadata_ms": round(terminal_metadata_ms, 3),
        },
        "metadata": {
            "generation_status": "completed",
            "provider_id": provider_id,
            "model_id": model_id,
            "resolved_model": resolved_model,
            **memory_metadata,
            **history_metadata,
            **({"usage": usage_payload} if usage_payload is not None else {}),
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
        routing_deadline_at: float | None = None,
    ) -> Iterator[dict[str, Any]]:
        if parse_memory_command(user_message.content) is not None:
            yield from original_stream(
                self,
                session,
                user_message,
                provider_id=provider_id,
                model_id=model_id,
                context_items=context_items,
                routing_deadline_at=routing_deadline_at,
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
        yield from _stream_low_latency_reply(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
            routing_deadline_at=routing_deadline_at,
        )

    PromptChatSessionStore.stream_provider_reply_chunks = patched_stream
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
