"""Whose names a call's speech recognition listens for (companion review, 2026-11-20).

The speech proxy boosts a call's member names in recognition. The browser names its chat; the gateway, never the
browser, says who is on that chat's call: the ``CALL_ROSTER`` port, contributed by live voice, reads the chat as the
caller's tenant sees it. The proxy also tells the roster a call is open on the chat, which keeps its guest seats
from expiring (``chat.persistence.scene_repository``). Without the port no names are boosted.
"""
from __future__ import annotations

from typing import Protocol

from app.runtime.ports import Port


class CallRoster(Protocol):
    def names(self, chat_session_id: str) -> list[str]:
        """The display names of everyone on the chat's call; empty for a chat that is not the caller's."""

    def note_call(self, chat_session_id: str) -> None:
        """A call is open on the chat: its guests' seats stay."""


CALL_ROSTER: Port[CallRoster] = Port("voice.call_roster", CallRoster, "at_most_one")

__all__ = ["CALL_ROSTER", "CallRoster"]
