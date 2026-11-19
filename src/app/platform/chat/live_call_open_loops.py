"""Open loops a quiet live call may raise (companion 3.2).

The speaker's own memory holds what is still open between it and the person: a promise it made, an open loop it
keeps. When social initiative may speak, ``initiative-candidate`` names one as ``open_loop:<key>``; the stream route
checks it again, and its turn id (``open-loop:<key>:<nonce>``) is bound to the initiative lease. The delivery derives
``raised_open_loop_id`` from that turn id and records it on the message, so the loop is not raised again within
``RAISE_WINDOW``. The server has no id for a live call, so the window stands in for "once per call".

Private-transcript chats and chats that may not read memory get none.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from .memory_port import session_open_loops

OPEN_LOOP_REASON_PREFIX = "open_loop:"
OPEN_LOOP_TURN_PREFIX = "open-loop:"
RAISE_WINDOW = timedelta(hours=12)
OPEN_LOOP_TEXT_CHARS = 240
_KEY_CHARS = 24
_HEX = frozenset("0123456789abcdef")


class OpenLoopMaterial(BaseModel):
    """The loop a checked ``open_loop:`` reason names, and the turn id its stream is bound to."""

    key: str
    text: str
    turn_id: str


def open_loop_key(assertion_id: str) -> str:
    """A stable, opaque name for a memory assertion: the call never sees the assertion's id."""
    return hashlib.sha256(assertion_id.encode("utf-8")).hexdigest()[:_KEY_CHARS]


def open_loop_reason(key: str) -> str:
    return f"{OPEN_LOOP_REASON_PREFIX}{key}"


def is_open_loop_reason(reason: str) -> bool:
    return reason.strip().startswith(OPEN_LOOP_REASON_PREFIX)


def raised_open_loop_key(*, reason: str | None = None, turn_id: str | None = None) -> str | None:
    """The loop an ``open_loop:<key>`` reason or an ``open-loop:<key>:<nonce>`` turn id names; otherwise None."""
    key: str | None = None
    if reason is not None and reason.startswith(OPEN_LOOP_REASON_PREFIX):
        key = reason[len(OPEN_LOOP_REASON_PREFIX):]
    elif turn_id is not None and turn_id.startswith(OPEN_LOOP_TURN_PREFIX):
        key = turn_id[len(OPEN_LOOP_TURN_PREFIX):].split(":", 1)[0]
    if key is None or len(key) != _KEY_CHARS or not set(key) <= _HEX:
        return None
    return key


def _when(value: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _recently_raised(session: Any, now: datetime) -> set[str]:
    raised: set[str] = set()
    for message in getattr(session, "messages", None) or []:
        key = (getattr(message, "metadata", None) or {}).get("raised_open_loop_id")
        if not isinstance(key, str):
            continue
        at = _when(getattr(message, "created_at", None))
        # A message whose time cannot be read counts as recent: the loop waits rather than repeats.
        if at is None or now - at < RAISE_WINDOW:
            raised.add(key)
    return raised


def _bounded(text: str) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= OPEN_LOOP_TEXT_CHARS:
        return compact
    return compact[:OPEN_LOOP_TEXT_CHARS].rsplit(" ", 1)[0] + " …"


def _open_loops(session: Any, now: datetime) -> list[tuple[str, str]]:
    if getattr(session, "transcript_policy", "persistent") != "persistent":
        return []
    raised = _recently_raised(session, now)
    found: list[tuple[str, str]] = []
    for loop in session_open_loops(session, now=now):
        key = open_loop_key(str(loop.assertion_id))
        text = _bounded(str(loop.text or ""))
        if text and key not in raised and all(key != seen for seen, _ in found):
            found.append((key, text))
    return found


def open_loop_candidate(session: Any, *, now: datetime | None = None) -> str | None:
    """The newest open loop not raised in this chat within ``RAISE_WINDOW``, as its reason; otherwise None."""
    loops = _open_loops(session, now or datetime.now(timezone.utc))
    return open_loop_reason(loops[0][0]) if loops else None


def open_loop_material(session: Any, reason: str, *, now: datetime | None = None) -> OpenLoopMaterial | None:
    """The loop an ``open_loop:`` reason names, or None unless it is still open, the speaker's own, and not raised."""
    key = raised_open_loop_key(reason=reason.strip())
    if key is None:
        return None
    for found, text in _open_loops(session, now or datetime.now(timezone.utc)):
        if found == key:
            return OpenLoopMaterial(key=key, text=text, turn_id=f"{OPEN_LOOP_TURN_PREFIX}{key}:{uuid.uuid4().hex}")
    return None


__all__ = [
    "OPEN_LOOP_REASON_PREFIX",
    "OPEN_LOOP_TURN_PREFIX",
    "RAISE_WINDOW",
    "OpenLoopMaterial",
    "is_open_loop_reason",
    "open_loop_candidate",
    "open_loop_key",
    "open_loop_material",
    "open_loop_reason",
    "raised_open_loop_key",
]
