"""Assistant knowledge, visual context, Chat memory, and Character routes."""
from __future__ import annotations

from typing import Any

from app.assistant_memory.routes import register_assistant_memory_routes
from app.characters.api import register_character_routes
from app.characters.avatar_api import register_character_avatar_routes
from app.characters.avatar_generation_api import register_character_avatar_generation_routes
from app.characters.avatar_viseme_api import register_character_avatar_viseme_routes
from app.characters.live2d_avatar import register_character_live2d_avatar_routes
from app.characters.live_conversation_rendering import register_live_conversation_rendering_routes
from app.desktop_companion.routes import register_desktop_companion_routes
from .models import AssistantContextChatRequest, AssistantContextItem
from .routes import register_assistant_context_routes as _register_assistant_context_routes
from .service import AssistantContextService, default_assistant_context_service


def register_assistant_context_routes(app, **kwargs: Any) -> None:
    """Register context routes and shared Chat-adjacent lifecycle APIs."""

    # Import gateway-owned route helpers lazily. Importing them at package load
    # initializes app.gateway, whose hook imports this public function.
    from app.gateway.live_call_prewarm import register_live_call_prewarm_routes
    from app.gateway.live_chat_speculation import register_live_chat_speculation_routes
    from app.gateway.live_chat_speculation_handshake import (
        register_live_chat_speculation_handshake_routes,
    )
    from app.gateway.live_chat_speculation_inline_stream import (
        register_live_chat_speculation_inline_stream_routes,
    )
    from app.gateway.tts_live_capabilities import register_tts_live_capability_routes

    _register_assistant_context_routes(app, **kwargs)
    chat_store_kwargs: dict[str, Any] = {}
    if kwargs.get("chat_store_factory") is not None:
        chat_store_kwargs["chat_store_factory"] = kwargs["chat_store_factory"]
    register_live_chat_speculation_routes(app, **chat_store_kwargs)
    register_live_chat_speculation_handshake_routes(app, **chat_store_kwargs)
    register_live_chat_speculation_inline_stream_routes(app, **chat_store_kwargs)
    register_live_call_prewarm_routes(app, **chat_store_kwargs)
    register_tts_live_capability_routes(app)
    register_assistant_memory_routes(app, **chat_store_kwargs)
    register_character_routes(
        app,
        chat_store_factory=kwargs.get("chat_store_factory"),
    )
    register_live_conversation_rendering_routes(
        app,
        chat_store_factory=kwargs.get("chat_store_factory"),
    )
    register_desktop_companion_routes(app)
    register_character_avatar_routes(app)
    register_character_avatar_generation_routes(app)
    register_character_avatar_viseme_routes(app)
    register_character_live2d_avatar_routes(app)


__all__ = [
    "AssistantContextChatRequest",
    "AssistantContextItem",
    "AssistantContextService",
    "default_assistant_context_service",
    "register_assistant_context_routes",
]
