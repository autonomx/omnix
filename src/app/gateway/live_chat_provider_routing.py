"""Resolve implicit chat providers before retry and metrics hooks run."""

from __future__ import annotations

from functools import wraps
from typing import Any, Iterator

from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.chat.store import _provider_key

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_provider_routing_installed"


def resolve_effective_provider_id(provider_id: str | None) -> str | None:
    """Preserve explicit routing and concretize the configured default provider."""

    explicit = str(provider_id or "").strip()
    if explicit:
        return explicit

    from app import shared

    configured = str(shared.load_settings().get("provider") or "").strip()
    return configured or "lmstudio"


def resolve_provider_route(provider_id: str | None) -> tuple[str | None, Any]:
    """Return the concrete provider ID and the provider instance it resolves to."""

    from app import shared

    effective_provider_id = resolve_effective_provider_id(provider_id)
    provider = shared.get_provider(_provider_key(effective_provider_id))
    return effective_provider_id, provider


def _provider_name(provider: Any) -> str | None:
    value = str(getattr(provider, "provider_name", "") or "").strip().lower()
    return value or None


def _log_route(
    *,
    provider_id: str | None,
    effective_provider_id: str | None,
    provider: Any,
    stream: bool,
) -> None:
    effective_provider_name = _provider_name(provider)
    stream_log(
        "gateway-live-chat-first-token",
        "runtime",
        "live_chat_provider_route_resolved",
        requested_provider_id=provider_id,
        effective_provider_id=effective_provider_id,
        effective_provider_name=effective_provider_name,
        provider_class=(
            f"{provider.__class__.__module__}.{provider.__class__.__name__}"
            if provider is not None
            else None
        ),
        lmstudio_metrics_path_expected=effective_provider_name == "lmstudio",
        stream=stream,
    )


def install_live_chat_provider_routing_hook() -> None:
    """Resolve default routing once before retry and provider-specific hooks."""

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
        effective_provider_id, provider = resolve_provider_route(provider_id)
        _log_route(
            provider_id=provider_id,
            effective_provider_id=effective_provider_id,
            provider=provider,
            stream=False,
        )
        return original_generate(
            self,
            session,
            user_message,
            provider_id=effective_provider_id,
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
        effective_provider_id, provider = resolve_provider_route(provider_id)
        _log_route(
            provider_id=provider_id,
            effective_provider_id=effective_provider_id,
            provider=provider,
            stream=True,
        )
        yield from original_stream(
            self,
            session,
            user_message,
            provider_id=effective_provider_id,
            model_id=model_id,
            context_items=context_items,
        )

    PromptChatSessionStore._generate_provider_reply = patched_generate
    PromptChatSessionStore.stream_provider_reply_chunks = patched_stream
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
