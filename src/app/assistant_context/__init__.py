"""Assistant knowledge and visual context enrichment."""

from .models import AssistantContextChatRequest, AssistantContextItem
from .routes import register_assistant_context_routes
from .service import AssistantContextService, default_assistant_context_service

__all__ = [
    "AssistantContextChatRequest",
    "AssistantContextItem",
    "AssistantContextService",
    "default_assistant_context_service",
    "register_assistant_context_routes",
]
