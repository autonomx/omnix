"""Chat session platform contract.

Exports load on first use, so importing one submodule (``declarations``) does not
load the package (ADR-0016, PA-2.2).
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "ChatImportState": ("app.chat.repository", "ChatImportState"),
    "ChatMessage": ("app.chat.models", "ChatMessage"),
    "ChatRepository": ("app.chat.repository", "ChatRepository"),
    "ChatRoutingContext": ("app.chat.routing_context", "ChatRoutingContext"),
    "ChatSession": ("app.chat.models", "ChatSession"),
    "ChatSessionListResponse": ("app.chat.models", "ChatSessionListResponse"),
    "ChatSessionStore": ("app.chat.character_store", "ChatSessionStore"),
    "ChatSessionSummary": ("app.chat.models", "ChatSessionSummary"),
    "ChatTextAttachment": ("app.chat.models", "ChatTextAttachment"),
    "CreateChatSessionRequest": ("app.chat.models", "CreateChatSessionRequest"),
    "DeleteChatSessionResponse": ("app.chat.models", "DeleteChatSessionResponse"),
    "InMemoryChatRepository": ("app.chat.repository", "InMemoryChatRepository"),
    "InMemoryChatSessionStore": ("app.chat.character_store", "InMemoryChatSessionStore"),
    "PromptAssembly": ("app.chat.prompt_assembly", "PromptAssembly"),
    "RenderedPrompt": ("app.chat.prompt_rendering", "RenderedPrompt"),
    "SendChatMessageRequest": ("app.chat.models", "SendChatMessageRequest"),
    "SendChatMessageResponse": ("app.chat.models", "SendChatMessageResponse"),
    "UpdateChatResearchModeRequest": ("app.chat.models", "UpdateChatResearchModeRequest"),
    "build_chat_routing_context": ("app.chat.routing_context", "build_chat_routing_context"),
    "build_prompt_assembly": ("app.chat.prompt_assembly", "build_prompt_assembly"),
    "chat_sqlite_store_enabled": ("app.chat.prompt_store", "chat_sqlite_store_enabled"),
    "default_chat_store": ("app.chat.character_store", "default_chat_store"),
    "render_prompt_assembly": ("app.chat.prompt_rendering", "render_prompt_assembly"),
}

__all__ = [
    "ChatImportState",
    "ChatMessage",
    "ChatRepository",
    "ChatSession",
    "ChatSessionListResponse",
    "ChatSessionStore",
    "ChatSessionSummary",
    "ChatRoutingContext",
    "ChatTextAttachment",
    "CreateChatSessionRequest",
    "DeleteChatSessionResponse",
    "InMemoryChatRepository",
    "InMemoryChatSessionStore",
    "PromptAssembly",
    "RenderedPrompt",
    "SendChatMessageRequest",
    "SendChatMessageResponse",
    "UpdateChatResearchModeRequest",
    "build_prompt_assembly",
    "build_chat_routing_context",
    "chat_sqlite_store_enabled",
    "default_chat_store",
    "render_prompt_assembly",
]


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(target[0]), target[1])
    globals()[name] = value
    return value
