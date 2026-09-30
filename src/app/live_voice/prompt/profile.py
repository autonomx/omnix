"""Define the live voice latency budget and provider stream context."""
from __future__ import annotations
from app.config.env import env_str as _env_str

import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Iterator

from app.chat.context_budget import PromptBudget, prompt_budget_from_env
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.chat.provider_metrics import merge_provider_response_metrics
from app.providers.lmstudio_provider import LMStudioProvider

from app.observability.tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_live_voice_profile_installed"
_LMSTUDIO_SENTINEL = "_omnix_live_voice_thinking_policy_installed"
_LIVE_VOICE_TURN: ContextVar[bool] = ContextVar("omnix_live_voice_turn", default=False)

_DEFAULT_RECENT_MESSAGE_LIMIT = 12
_DEFAULT_INPUT_TOKEN_BUDGET = 12_288
_DEFAULT_OUTPUT_TOKEN_RESERVE = 1_024
_DEFAULT_MEMORY_TOKEN_BUDGET = 1_000
_DEFAULT_SUMMARY_TOKEN_BUDGET = 2_000
_DEFAULT_EXTERNAL_CONTEXT_TOKEN_BUDGET = 2_048


def _integer_setting(name: str, fallback: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int((_env_str(name) or fallback)))
    except (TypeError, ValueError):
        return max(minimum, fallback)


def _is_live_voice_message(user_message: Any) -> bool:
    metadata = getattr(user_message, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    speech_segment_id = str(metadata.get("speech_segment_id") or "").strip()
    user_turn_id = str(metadata.get("user_turn_id") or "").strip()
    return bool(speech_segment_id or user_turn_id.startswith("voice-user-turn:"))


def _live_voice_recent_message_limit() -> int:
    return _integer_setting(
        "OMNIX_LIVE_VOICE_RECENT_MESSAGE_LIMIT",
        _DEFAULT_RECENT_MESSAGE_LIMIT,
        minimum=2,
    )


def _live_voice_prompt_budget() -> PromptBudget:
    base = prompt_budget_from_env()
    input_budget = min(
        base.max_input_tokens,
        _integer_setting(
            "OMNIX_LIVE_VOICE_INPUT_TOKEN_BUDGET",
            _DEFAULT_INPUT_TOKEN_BUDGET,
            minimum=1,
        ),
    )
    output_reserve = min(
        max(0, input_budget - 1),
        base.reserved_output_tokens,
        _integer_setting(
            "OMNIX_LIVE_VOICE_OUTPUT_TOKEN_RESERVE",
            _DEFAULT_OUTPUT_TOKEN_RESERVE,
        ),
    )
    return base.model_copy(
        update={
            "max_input_tokens": input_budget,
            "reserved_output_tokens": output_reserve,
            "memory_tokens": min(
                base.memory_tokens,
                _integer_setting(
                    "OMNIX_LIVE_VOICE_MEMORY_TOKEN_BUDGET",
                    _DEFAULT_MEMORY_TOKEN_BUDGET,
                ),
            ),
            "summary_tokens": min(
                base.summary_tokens,
                _integer_setting(
                    "OMNIX_LIVE_VOICE_SUMMARY_TOKEN_BUDGET",
                    _DEFAULT_SUMMARY_TOKEN_BUDGET,
                ),
            ),
            "history_tokens": 0,
            "external_context_tokens": min(
                base.external_context_tokens,
                _integer_setting(
                    "OMNIX_LIVE_VOICE_EXTERNAL_CONTEXT_TOKEN_BUDGET",
                    _DEFAULT_EXTERNAL_CONTEXT_TOKEN_BUDGET,
                ),
            ),
        }
    )


def _install_lmstudio_thinking_policy() -> None:
    if getattr(LMStudioProvider, _LMSTUDIO_SENTINEL, False):
        return
    original_chat_completion = LMStudioProvider.chat_completion

    @wraps(original_chat_completion)
    def patched_chat_completion(
        self: LMStudioProvider,
        messages,
        model=None,
        stream: bool = False,
        **kwargs,
    ):
        if _LIVE_VOICE_TURN.get():
            configured = kwargs.get("chat_template_kwargs")
            template_kwargs = dict(configured) if isinstance(configured, dict) else {}
            template_kwargs["enable_thinking"] = False
            kwargs["chat_template_kwargs"] = template_kwargs
            # Native LM Studio metrics expose prompt/input tokens, TTFT and
            # speculative-decoding stats. The provider transparently falls back
            # to the OpenAI-compatible endpoint if the native metrics endpoint is
            # unavailable, so this stays safe for older local servers.
            kwargs["include_metrics"] = True
        return original_chat_completion(
            self,
            messages,
            model=model,
            stream=stream,
            **kwargs,
        )

    LMStudioProvider.chat_completion = patched_chat_completion
    setattr(LMStudioProvider, _LMSTUDIO_SENTINEL, True)


def _stream_with_live_voice_context(
    stream: Iterator[Any],
    *,
    is_live_voice: bool,
) -> Iterator[Any]:
    """Advance a stream without carrying ContextVar tokens across yields.

    Starlette may advance a synchronous response iterator in a different copied
    context for each chunk. A token created before ``yield`` therefore cannot be
    reset reliably after the caller asks for the next chunk. Keep each token
    entirely inside the single iterator advance that created it.

    Raw LM Studio streams (notably side-effect-free speculative generations) are
    also summarized here because they bypass the normal chat provider-metrics
    persistence hook. Dict-shaped chat events simply produce no provider metrics,
    so normal accepted chat does not get double-counted.
    """

    iterator = iter(stream)
    stream_started = time.perf_counter()
    first_provider_text_ms: float | None = None
    provider_metrics: dict[str, Any] = {}
    completed = False
    try:
        while True:
            token = _LIVE_VOICE_TURN.set(is_live_voice)
            try:
                try:
                    item = next(iterator)
                except StopIteration:
                    completed = True
                    return
            finally:
                _LIVE_VOICE_TURN.reset(token)

            if is_live_voice:
                provider_metrics = merge_provider_response_metrics(
                    provider_metrics,
                    item,
                    provider_id=None,
                )
                if first_provider_text_ms is None:
                    text = getattr(item, "content", "") or ""
                    if text:
                        first_provider_text_ms = (
                            time.perf_counter() - stream_started
                        ) * 1000.0
            yield item
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            token = _LIVE_VOICE_TURN.set(is_live_voice)
            try:
                close()
            finally:
                _LIVE_VOICE_TURN.reset(token)

        if is_live_voice and (provider_metrics or first_provider_text_ms is not None):
            native_ttft = provider_metrics.get("time_to_first_token_seconds")
            stream_log(
                "gateway-live-chat-first-token",
                "runtime",
                "live_voice_raw_provider_stream_metrics",
                stream_completed=completed,
                first_provider_text_ms=(
                    round(first_provider_text_ms, 3)
                    if first_provider_text_ms is not None
                    else None
                ),
                native_ttft_ms=(
                    round(float(native_ttft) * 1000.0, 3)
                    if isinstance(native_ttft, (int, float))
                    else None
                ),
                input_tokens=provider_metrics.get("input_tokens"),
                cached_input_tokens=provider_metrics.get("cached_input_tokens"),
                uncached_input_tokens=provider_metrics.get("uncached_input_tokens"),
                prompt_cache_hit_ratio=provider_metrics.get("prompt_cache_hit_ratio"),
                output_tokens=provider_metrics.get("output_tokens"),
                tokens_per_second=provider_metrics.get("tokens_per_second"),
                draft_model=provider_metrics.get("draft_model"),
                total_draft_tokens=provider_metrics.get("total_draft_tokens"),
                accepted_draft_tokens=provider_metrics.get("accepted_draft_tokens"),
                rejected_draft_tokens=provider_metrics.get("rejected_draft_tokens"),
                ignored_draft_tokens=provider_metrics.get("ignored_draft_tokens"),
                draft_acceptance_ratio=provider_metrics.get("draft_acceptance_ratio"),
                total_ms=round((time.perf_counter() - stream_started) * 1000.0, 3),
            )


def install_live_chat_live_voice_profile_hook() -> None:
    """Install the live-only prompt and provider policy after routing wrappers."""

    if getattr(PromptChatSessionStore, _HOOK_SENTINEL, False):
        return

    original_stream = PromptChatSessionStore.stream_provider_reply_chunks
    original_generate = PromptChatSessionStore._generate_provider_reply

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
        stream_kwargs: dict[str, Any] = {
            "provider_id": provider_id,
            "model_id": model_id,
            "context_items": context_items,
        }
        if routing_deadline_at is not None:
            stream_kwargs["routing_deadline_at"] = routing_deadline_at
        yield from _stream_with_live_voice_context(
            original_stream(
                self,
                session,
                user_message,
                **stream_kwargs,
            ),
            is_live_voice=_is_live_voice_message(user_message),
        )

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
        token = _LIVE_VOICE_TURN.set(_is_live_voice_message(user_message))
        try:
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
        finally:
            _LIVE_VOICE_TURN.reset(token)

    PromptChatSessionStore.stream_provider_reply_chunks = patched_stream
    PromptChatSessionStore._generate_provider_reply = patched_generate
    _install_lmstudio_thinking_policy()
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
