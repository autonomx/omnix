"""Live voice's ``CALL_ROSTER`` (``app.platform.voice.call_roster``): a call's names and its seats' keep-alive, read
from the chat the browser named as the caller's tenant sees it."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.platform.live_voice.transport.call_session import load_session


class ChatCallRoster:
    def __init__(self, chat_store_factory: Callable[[], Any]) -> None:
        self._chat_store_factory = chat_store_factory

    def names(self, chat_session_id: str) -> list[str]:
        from app.platform.chat.contracts import call_names

        session = load_session(self._chat_store_factory, chat_session_id) if chat_session_id else None
        return call_names(session) if session is not None else []

    def note_call(self, chat_session_id: str) -> None:
        from app.platform.chat.contracts import note_call

        session = load_session(self._chat_store_factory, chat_session_id) if chat_session_id else None
        if session is not None:
            note_call(session)


__all__ = ["ChatCallRoster"]
