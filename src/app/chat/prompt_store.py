"""Chat store adapter that routes provider generation through PromptAssembly."""
from __future__ import annotations

import os
from typing import Any

from .models import ChatMessage, ChatSession
from .prompt_assembly import PromptAssembly, build_prompt_assembly
from .prompt_rendering import RenderedPrompt, render_prompt_assembly
from .store import ChatSessionStore as JsonChatSessionStore


class ChatSessionStore(JsonChatSessionStore):
    """Compatibility store with one provider prompt path for every generation mode."""

    def build_provider_prompt(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        context_items: list[dict[str, Any]] | None = None,
    ) -> tuple[PromptAssembly, RenderedPrompt]:
        from app import shared

        assembly = build_prompt_assembly(
            session,
            user_message,
            global_system_prompt=shared.get_global_system_prompt(),
            context_items=context_items or [],
        )
        return assembly, render_prompt_assembly(assembly)

    def _provider_messages(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        context_items: list[dict[str, Any]],
    ):
        from app.providers import ChatMessage as ProviderMessage

        _, rendered = self.build_provider_prompt(session, user_message, context_items)
        return [
            ProviderMessage(role=message.role, content=message.content)
            for message in rendered.messages
        ]


def chat_sqlite_store_enabled() -> bool:
    return (os.environ.get("OMNIX_CHAT_SQLITE_STORE_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def default_chat_store() -> ChatSessionStore:
    if chat_sqlite_store_enabled():
        from .sqlite_store import SQLiteChatSessionStore

        return SQLiteChatSessionStore()
    return ChatSessionStore()
