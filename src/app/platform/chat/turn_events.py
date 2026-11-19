"""Events chat publishes for other modules to react to (ADR-0016, PA-3.4).

Delivered through the outbox after the producing transaction commits; a
consumer may see an event more than once and must be idempotent. The wire
contract is the aggregate type, the event type and the payload's fields.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

CHAT_SESSION_AGGREGATE = "chat_session"
CHAT_TURN_COMPLETED = "chat.turn.completed"
CHAT_SESSION_DELETED = "chat.session.deleted"
CHAT_SCENE_LINE_DELIVERED = "chat.scene_line.delivered"


class ChatTurnCompleted(BaseModel):
    """A chat turn's reply was generated and stored.

    ``memory_writes_allowed`` is the session's policy: a character session
    writes memory unless it was turned off for that session.
    """

    model_config = ConfigDict(extra="ignore")

    session_id: str
    user_message_id: str
    user_id: str
    memory_writes_allowed: bool


class ChatSessionDeleted(BaseModel):
    """A chat was deleted, whichever characters it was talking to over its life."""

    model_config = ConfigDict(extra="ignore")

    session_id: str
    user_id: str


class ChatSceneLineDelivered(BaseModel):
    """A character's line in a call with guests was delivered and stored as a line (companion 6.6).

    The other members present heard it; assistant memory reads the thread it belongs to. ``heard_text`` is the
    part the person heard when the line was cut off (None when it played in full or is unknown).
    """

    model_config = ConfigDict(extra="ignore")

    session_id: str
    message_id: str
    user_id: str
    speaker_id: str
    member_ids: list[str]
    memory_writes_allowed: bool
    heard_text: str | None = None


def scene_line_delivered_event_key(message_id: str) -> str:
    """One event per stored line, however often its delivery is retried."""
    return f"{CHAT_SCENE_LINE_DELIVERED}:{message_id}"


def turn_completed_event_key(user_message_id: str) -> str:
    """One event per user message, however often the turn's completion is retried."""
    return f"{CHAT_TURN_COMPLETED}:{user_message_id}"


__all__ = [
    "CHAT_SCENE_LINE_DELIVERED",
    "CHAT_SESSION_AGGREGATE",
    "CHAT_SESSION_DELETED",
    "CHAT_TURN_COMPLETED",
    "ChatSceneLineDelivered",
    "ChatSessionDeleted",
    "ChatTurnCompleted",
    "scene_line_delivered_event_key",
    "turn_completed_event_key",
]
