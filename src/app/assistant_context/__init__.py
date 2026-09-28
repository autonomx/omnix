"""Assistant knowledge, visual context, Chat memory, and Character routes."""
from __future__ import annotations

from typing import Any

from .models import AssistantContextChatRequest, AssistantContextItem
from .routes import register_assistant_context_routes as _register_assistant_context_routes
from .service import AssistantContextService, default_assistant_context_service


def register_assistant_context_routes(app, **kwargs: Any) -> None:
    """Register context routes and shared Chat-adjacent lifecycle APIs."""

    # Import route helpers lazily. Importing gateway or Desktop Companion routes at package
    # load can create cycles through assistant-context vision/preflight dependencies.
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



__all__ = [
    "AssistantContextChatRequest",
    "AssistantContextItem",
    "AssistantContextService",
    "default_assistant_context_service",
    "register_assistant_context_routes",
]
