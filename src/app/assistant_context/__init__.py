"""Assistant knowledge, visual context, Chat memory, and Character routes."""
from __future__ import annotations

from typing import Any

from app.assistant_memory.routes import register_assistant_memory_routes
from app.characters.api import register_character_routes
from app.characters.avatar_api import register_character_avatar_routes

from .models import AssistantContextChatRequest, AssistantContextItem
from .routes import register_assistant_context_routes as _register_assistant_context_routes
from .service import AssistantContextService, default_assistant_context_service


def register_assistant_context_routes(app, **kwargs: Any) -> None:
    """Register context routes and shared Chat-adjacent lifecycle APIs."""

    _register_assistant_context_routes(app, **kwargs)
    memory_kwargs: dict[str, Any] = {}
    if "chat_store_factory" in kwargs:
        memory_kwargs["chat_store_factory"] = kwargs["chat_store_factory"]
    register_assistant_memory_routes(app, **memory_kwargs)
    register_character_routes(
        app,
        chat_store_factory=kwargs.get("chat_store_factory"),
    )
    register_character_avatar_routes(app)


__all__ = [
    "AssistantContextChatRequest",
    "AssistantContextItem",
    "AssistantContextService",
    "default_assistant_context_service",
    "register_assistant_context_routes",
]
