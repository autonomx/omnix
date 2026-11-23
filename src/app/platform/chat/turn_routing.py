"""Chat asks the agent runtime about a typed turn here, and records what it decided on the user's message.

The agent runtime contributes the router (``TYPED_TURN_ROUTER``); without it chat answers every turn itself. Chat
owns the turn's deadline, the reference context the router may read, and the routing metadata it keeps.
"""
from __future__ import annotations

from typing import Any

from app.platform.chat.routing_deadline import provider_turn_deadline

# What routing writes on the user's message and chat keeps with the turn.
ROUTING_METADATA_KEYS = (
    "omnix_chat_routed",
    "omnix_route",
    "semantic_intent",
    "semantic_task",
    "semantic_compilation",
    "routing_decision",
    "request_mode",
    "turn_plan",
    "active_objective",
    "routing_environment",
)


def route_typed_turn(
    store: Any,
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]] | None = None,
    routing_deadline_at: float | None = None,
) -> Any:
    """The router's result when it settles the turn, or None to let chat answer.

    The router may read the store's canonical prompt context (memory, history, summary) through
    ``build_routing_context``, which it builds only when it needs it. The store keeps that prompt for the turn's
    reply; a turn the router settles drops it.
    """
    from app.platform.chat.contracts import route_typed_turn as ask_router

    builder = getattr(store, "build_routing_context", None)
    result = ask_router(
        session,
        user_message,
        provider_id=provider_id,
        model_id=model_id,
        context_items=context_items,
        routing_deadline_at=provider_turn_deadline(
            provider_id,
            session_provider_id=getattr(session, "provider_id", None),
            existing_deadline_at=routing_deadline_at,
        ),
        **(
            {"routing_context_factory": lambda: builder(session, user_message, context_items or [])}
            if callable(builder)
            else {}
        ),
    )
    if result is not None:
        discard = getattr(store, "discard_prompt_context", None)
        if callable(discard):
            discard(session, user_message)
    return result


def patch_user_message_metadata(
    store: Any,
    *,
    session_id: str,
    message_id: str,
    metadata: dict[str, Any],
) -> None:
    """Merge ``metadata`` into one stored user message without rewriting the rest of the session."""
    if store is None or not metadata:
        return
    for name in ("update_user_message_metadata", "update_message_metadata"):
        update = getattr(store, name, None)
        if callable(update):
            update(session_id=session_id, message_id=message_id, metadata=metadata)
            return
    session = store.get_session(session_id)
    if session is None:
        return
    message = next((item for item in session.messages if item.id == message_id and item.role == "user"), None)
    if message is None:
        return
    message.metadata.update(metadata)
    store._save_session(session)


def persist_routing_metadata(store: Any, session: Any, user_message: Any) -> None:
    """Store what routing wrote on the user's message (``ROUTING_METADATA_KEYS``)."""
    patch = {key: user_message.metadata[key] for key in ROUTING_METADATA_KEYS if key in user_message.metadata}
    patch_user_message_metadata(store, session_id=session.id, message_id=user_message.id, metadata=patch)


__all__ = ["ROUTING_METADATA_KEYS", "patch_user_message_metadata", "persist_routing_metadata", "route_typed_turn"]
