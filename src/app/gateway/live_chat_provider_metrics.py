"""Persist LM Studio usage and generation statistics on assistant messages."""
from __future__ import annotations

from functools import wraps
from typing import Any, Iterator

from app.chat.memory_commands import parse_memory_command
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.chat.provider_metrics import merge_provider_response_metrics
from app.chat.store import _model_key, _pop_ready_sentences, _provider_key

_HOOK_SENTINEL = "_omnix_live_chat_provider_metrics_installed"


def _is_lmstudio(provider_id: str | None) -> bool:
    from app import shared

    provider = shared.get_provider(_provider_key(provider_id))
    return str(getattr(provider, "provider_name", "")).strip().lower() == "lmstudio"


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
) -> dict[str, Any]:
    from app import shared
    from app.providers import ChatMessage as ProviderMessage

    provider = shared.get_provider(_provider_key(provider_id))
    if provider is None:
        raise RuntimeError("Chat provider is not available")
    assembly, rendered = self.build_provider_prompt(session, user_message, context_items)
    messages = [
        ProviderMessage(role=message.role, content=message.content)
        for message in rendered.messages
    ]
    model_name = _model_key(model_id)
    response = provider.chat_completion(
        messages=messages,
        model=model_name,
        stream=False,
        include_metrics=True,
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
) -> Iterator[dict[str, Any]]:
    from app import shared
    from app.providers import ChatMessage as ProviderMessage

    provider = shared.get_provider(_provider_key(provider_id))
    if provider is None:
        raise RuntimeError("Chat provider is not available")
    assembly, rendered = self.build_provider_prompt(
        session,
        user_message,
        context_items or [],
    )
    messages = [
        ProviderMessage(role=message.role, content=message.content)
        for message in rendered.messages
    ]
    model_name = _model_key(model_id)
    response = provider.chat_completion(
        messages=messages,
        model=model_name,
        stream=True,
        include_metrics=True,
    )
    pending = ""
    full_text = ""
    resolved_model = model_name
    usage = None
    provider_metrics: dict[str, Any] = {}

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
        full_text += text
        pending += text
        ready, pending = _pop_ready_sentences(pending)
        for sentence in ready:
            yield {"type": "text_chunk", "text": sentence}

    if pending.strip():
        yield {"type": "text_chunk", "text": pending.strip()}
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
    ) -> dict[str, Any]:
        if not _is_lmstudio(provider_id):
            return original_generate(
                self,
                session,
                user_message,
                provider_id=provider_id,
                model_id=model_id,
                context_items=context_items,
            )
        return _generate_lmstudio_reply(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
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
    ) -> Iterator[dict[str, Any]]:
        if not _is_lmstudio(provider_id) or parse_memory_command(user_message.content) is not None:
            yield from original_stream(
                self,
                session,
                user_message,
                provider_id=provider_id,
                model_id=model_id,
                context_items=context_items,
            )
            return
        yield from _stream_lmstudio_reply(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
        )

    PromptChatSessionStore._generate_provider_reply = patched_generate
    PromptChatSessionStore.stream_provider_reply_chunks = patched_stream
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
