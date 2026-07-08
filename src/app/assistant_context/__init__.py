"""Assistant knowledge, visual context, and Chat memory route enrichment."""
from __future__ import annotations

from typing import Any

from app.assistant_memory.routes import register_assistant_memory_routes

from .models import AssistantContextChatRequest, AssistantContextItem
from .routes import register_assistant_context_routes as _register_assistant_context_routes
from .service import AssistantContextService, default_assistant_context_service


def register_assistant_context_routes(app, **kwargs: Any) -> None:
    """Register context routes plus the shared per-session memory lifecycle routes."""

    _register_assistant_context_routes(app, **kwargs)
    memory_kwargs: dict[str, Any] = {}
    if "chat_store_factory" in kwargs:
        memory_kwargs["chat_store_factory"] = kwargs["chat_store_factory"]
    register_assistant_memory_routes(app, **memory_kwargs)


__all__ = [
    "AssistantContextChatRequest",
    "AssistantContextItem",
    "AssistantContextService",
    "default_assistant_context_service",
    "register_assistant_context_routes",
]
