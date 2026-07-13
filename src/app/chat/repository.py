"""Chat repository contract and provider-free test double.

PostgreSQL is installed as the production repository by the explicit Omnix
startup boundary. This module contains no SQLite implementation or schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.chat.models import ChatSession
from app.testing.in_memory_chat_repository import InMemoryChatRepository

from .repository_models import ChatImportState


class ChatRepository(Protocol):
    def load_sessions(self) -> list[ChatSession]: ...

    def save_sessions(self, sessions: list[ChatSession]) -> None: ...


def default_chat_db_path() -> Path:
    """Return a stable test-double namespace, not a database path."""

    return Path(":memory:chat-default")


# Transitional historical symbol; the implementation is in-memory only.
SQLiteChatRepository = InMemoryChatRepository


__all__ = [
    "ChatImportState",
    "ChatRepository",
    "InMemoryChatRepository",
    "SQLiteChatRepository",
    "default_chat_db_path",
]
