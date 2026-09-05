"""Resolve implicit chat providers before retry and metrics hooks run."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import wraps
from typing import Any, Iterator

from app.chat.models import SendChatMessageRequest
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.chat.store import _provider_key
from app.persistence.chat_runtime_compat import PostgresCharacterChatSessionStore

from .live_voice_execution_lane import resolve_live_voice_chat_route
from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_provider_routing_installed"
_SETTINGS_HOOK_SENTINEL = "_omnix_live_chat_provider_routing_settings_hook_installed"
_ROUTE_LOCK = threading.RLock()
_DEFAULT_PROVIDER_ID: str | None = None
_TURN_ROUTES: dict[str, "_TurnProviderRoute"] = {}


@dataclass(frozen=True)
class _TurnProviderRoute:
    provider_id: str | None
    model_id: str | None
    provider_explicit: bool
    model_explicit: bool
    execution_lane: str = "session"


def _normalized(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _is_live_voice_request(request: SendChatMessageRequest) -> bool:
    user_turn_id = _normalized(request.user_turn_id)
    speech_segment_id = _normalized(request.speech_segment_id)
    return bool(
        speech_segment_id
        or (user_turn_id and user_turn_id.startswith("voice-user-turn:"))
    )


def _invalidate_default_provider_cache() -> None:
    global _DEFAULT_PROVIDER_ID
    with _ROUTE_LOCK:
        _DEFAULT_PROVIDER_ID = None


def _reset_provider_route_state_for_tests() -> None:
    _invalidate_default_provider_cache()
    with _ROUTE_LOCK:
        _TURN_ROUTES.clear()


def resolve_effective_provider_id(provider_id: str | None) -> str | None:
    """Preserve explicit routing and concretize the configured default provider."""

    explicit = _normalized(provider_id)
    if explicit:
        return explicit

    global _DEFAULT_PROVIDER_ID
    with _ROUTE_LOCK:
        if _DEFAULT_PROVIDER_ID is not None:
            return _DEFAULT_PROVIDER_ID

    from app import shared

    configured = _normalized(shared.load_settings().get("provider")) or "lmstudio"
    with _ROUTE_LOCK:
        _DEFAULT_PROVIDER_ID = configured
    return configured


def resolve_provider_route(provider_id: str | None) -> tuple[str | None, Any]:
    """Return the concrete provider ID and the provider instance it resolves to."""

    from app import shared

    effective_provider_id = resolve_effective_provider_id(provider_id)
    provider = shared.get_provider(_provider_key(effective_provider_id))
    return effective_provider_id, provider


def route_chat_request(
    request: SendChatMessageRequest,
    *,
    implicit_provider_id: str | None = None,
    implicit_model_id: str | None = None,
) -> tuple[SendChatMessageRequest, _TurnProviderRoute]:
    """Concretize routing and apply the opt-in dedicated live model lane."""

    provider_explicit = _normalized(request.provider_id) is not None
    model_explicit = _normalized(request.model_id) is not None
    provider_id = resolve_effective_provider_id(
        request.provider_id if provider_explicit else implicit_provider_id
    )
    model_id = (
        request.model_id
        if model_explicit
        else (
            _normalized(implicit_model_id)
            if not provider_explicit
            else None
        )
    )
    execution_lane = "session"
    if _is_live_voice_request(request):
        provider_id, model_id, execution_lane = resolve_live_voice_chat_route(
            provider_id,
            model_id,
        )
    route = _TurnProviderRoute(
        provider_id=provider_id,
        model_id=model_id,
        provider_explicit=provider_explicit,
        model_explicit=model_explicit,
        execution_lane=execution_lane,
    )
    routed_request = request.model_copy(
        update={
            "provider_id": route.provider_id,
            "model_id": route.model_id,
        }
    )
    return routed_request, route


def _live_voice_affinity_for_current_provider(
    session_id: str,
) -> tuple[str | None, str | None] | None:
    """Return prewarm affinity only while it matches the current Settings provider."""

    from .live_call_prewarm import live_call_provider_affinity

    affinity = live_call_provider_affinity(session_id)
    if affinity is None:
        return None
    affinity_provider_id, affinity_model_id = affinity
    configured_provider_id = resolve_effective_provider_id(None)
    if _provider_key(affinity_provider_id) == _provider_key(configured_provider_id):
        return affinity_provider_id, affinity_model_id

    stream_log(
        "gateway-live-chat-first-token",
        "runtime",
        "live_chat_provider_affinity_stale",
        session_id=session_id,
        affinity_provider_id=affinity_provider_id,
        configured_provider_id=configured_provider_id,
        reason="settings_provider_changed",
    )
    return None


def _remember_turn_route(message_id: str, route: _TurnProviderRoute) -> None:
    with _ROUTE_LOCK:
        _TURN_ROUTES[message_id] = route


def _forget_turn_route(message_id: str) -> None:
    with _ROUTE_LOCK:
        _TURN_ROUTES.pop(message_id, None)


def _stream_route(
    user_message: Any,
    provider_id: str | None,
    model_id: str | None,
) -> tuple[str | None, str | None, _TurnProviderRoute | None]:
    message_id = _normalized(getattr(user_message, "id", None))
    with _ROUTE_LOCK:
        turn_route = _TURN_ROUTES.get(message_id or "")
    if turn_route is None:
        return provider_id, model_id, None
    return turn_route.provider_id, turn_route.model_id, turn_route


def _provider_name_from_id(provider_id: str | None) -> str | None:
    return _normalized(_provider_key(provider_id))


def _provider_name(provider: Any, provider_id: str | None = None) -> str | None:
    value = _normalized(getattr(provider, "provider_name", None))
    return value.lower() if value else _provider_name_from_id(provider_id)


def _log_route(
    *,
    provider_id: str | None,
    effective_provider_id: str | None,
    stream: bool,
    turn_route: _TurnProviderRoute | None = None,
    provider: Any = None,
) -> None:
    effective_provider_name = _provider_name(provider, effective_provider_id)
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
        provider_explicit=turn_route.provider_explicit if turn_route is not None else None,
        model_explicit=turn_route.model_explicit if turn_route is not None else None,
        execution_lane=(turn_route.execution_lane if turn_route is not None else "session"),
        effective_model_id=(turn_route.model_id if turn_route is not None else None),
        session_provider_overridden=(
            bool(
                turn_route is not None
                and _provider_key(provider_id) != _provider_key(effective_provider_id)
            )
        ),
        lmstudio_metrics_path_expected=effective_provider_name == "lmstudio",
        stream=stream,
    )


def _install_settings_cache_invalidation() -> None:
    from app.platform import settings_control

    if getattr(settings_control, _SETTINGS_HOOK_SENTINEL, False):
        return
    original_save_settings = settings_control.save_settings

    @wraps(original_save_settings)
    def patched_save_settings(settings: Any) -> Any:
        try:
            return original_save_settings(settings)
        finally:
            _invalidate_default_provider_cache()

    settings_control.save_settings = patched_save_settings
    setattr(settings_control, _SETTINGS_HOOK_SENTINEL, True)


def install_live_chat_provider_routing_hook() -> None:
    """Resolve default routing once before retry and provider-specific hooks."""

    if getattr(PromptChatSessionStore, _HOOK_SENTINEL, False):
        return

    original_generate_reply = PromptChatSessionStore._generate_reply
    original_generate = PromptChatSessionStore._generate_provider_reply
    original_stream = PromptChatSessionStore.stream_provider_reply_chunks
    original_prompt_begin = PromptChatSessionStore.begin_user_message
    original_postgres_begin = PostgresCharacterChatSessionStore.begin_user_message

    @wraps(original_generate_reply)
    def patched_generate_reply(
        self: PromptChatSessionStore,
        session: Any,
        user_message: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
        request: SendChatMessageRequest,
        context_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if _normalized(request.provider_id) is None:
            provider_id = resolve_effective_provider_id(None)
            if _normalized(request.model_id) is None:
                model_id = None
        return original_generate_reply(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            request=request,
            context_items=context_items,
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
        effective_provider_id = resolve_effective_provider_id(provider_id)
        _log_route(
            provider_id=provider_id,
            effective_provider_id=effective_provider_id,
            stream=False,
        )
        generate_kwargs: dict[str, Any] = {
            "provider_id": effective_provider_id,
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
        routed_provider_id, routed_model_id, turn_route = _stream_route(
            user_message,
            provider_id,
            model_id,
        )
        effective_provider_id = resolve_effective_provider_id(routed_provider_id)
        _log_route(
            provider_id=provider_id,
            effective_provider_id=effective_provider_id,
            stream=True,
            turn_route=turn_route,
        )
        try:
            stream_kwargs: dict[str, Any] = {
                "provider_id": effective_provider_id,
                "model_id": routed_model_id,
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
        finally:
            message_id = _normalized(getattr(user_message, "id", None))
            if message_id:
                _forget_turn_route(message_id)

    def wrap_begin(original_begin):
        @wraps(original_begin)
        def patched_begin(
            self,
            session_id: str,
            request: SendChatMessageRequest,
            *,
            context_items: list[dict[str, Any]] | None = None,
            context_diagnostics: dict[str, Any] | None = None,
        ):
            implicit_provider_id = None
            implicit_model_id = None
            if _is_live_voice_request(request) and _normalized(request.provider_id) is None:
                # Reuse prewarm affinity only while it still matches Settings.
                # Changing the configured provider must take effect immediately,
                # even when this chat session was previously stamped with another
                # provider or an older live-call affinity is still within its TTL.
                affinity = _live_voice_affinity_for_current_provider(session_id)
                if affinity is not None:
                    implicit_provider_id, implicit_model_id = affinity
            routed_request, route = route_chat_request(
                request,
                implicit_provider_id=implicit_provider_id,
                implicit_model_id=implicit_model_id,
            )
            appended = original_begin(
                self,
                session_id,
                routed_request,
                context_items=context_items,
                context_diagnostics=context_diagnostics,
            )
            if appended is None:
                return None
            session, user_message = appended
            _remember_turn_route(user_message.id, route)
            session.provider_id = route.provider_id
            session.model_id = route.model_id
            return session, user_message

        return patched_begin

    PromptChatSessionStore._generate_reply = patched_generate_reply
    PromptChatSessionStore._generate_provider_reply = patched_generate
    PromptChatSessionStore.stream_provider_reply_chunks = patched_stream
    PromptChatSessionStore.begin_user_message = wrap_begin(original_prompt_begin)
    PostgresCharacterChatSessionStore.begin_user_message = wrap_begin(original_postgres_begin)
    _install_settings_cache_invalidation()
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)
