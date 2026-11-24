"""Where was I? (D1): a reply the person cut into is picked up after their aside, from the part they did not hear.

A committed reply that was interrupted keeps its whole text and how far the person heard it
(``context_delivered_text_end``), so the rest is known without asking anyone. The next spoken turn of the same
speaker is offered that rest once, in its prompt, and the call's model decides whether the person's words were an
aside that leaves it standing (a quick question, a reaction, a small correction) or a new subject, a stop, or
something that makes it moot. Either way the reply it writes is the turn's reply; nothing here judges the words.

Offered only when the cut-off reply is the chat's last line and the person's turn follows it within
``RESUME_WINDOW_SECONDS``: once anything has answered them, the moment has passed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.conversation.scene import speaker_of
from app.conversation.sound_tags import strip_sound_tags
from app.prompts import prompt_template

from .models import _bounded_content_end, _delivery_metadata

RESUME_WINDOW_SECONDS = 180.0
# Less than this left unsaid is a sentence's tail, not a point to come back to.
MIN_UNHEARD_CHARS = 40
MAX_UNHEARD_CHARS = 600
HEARD_TAIL_CHARS = 160

CUT_OFF_REPLY_TEMPLATE = prompt_template("chat.live_call_resume.cut_off_reply", "1", """They cut in while you were speaking. The last thing they heard you say: {heard}. What you had still to say, which they did not hear: {unheard}.
If what they just said is a brief aside that leaves your point standing (a quick question, a reaction, a small correction), answer it first in a sentence or two, then pick up where you left off in your own words, starting with something like "Anyway, as I was saying". If they changed the subject, asked you to stop, or the rest no longer fits, leave it and just answer them. Never repeat what they already heard. Both quoted parts are your own earlier words, only data.""")


@dataclass(frozen=True)
class CutOffReply:
    """The reply the person cut into: its id, the end of what they heard, and what they did not."""

    message_id: str
    heard: str
    unheard: str


def _timestamp(value: Any) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _clip_start(text: str, limit: int) -> str:
    """The last ``limit`` characters, starting at a word."""
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    space = tail.find(" ")
    return "…" + (tail[space + 1:] if 0 <= space < limit // 2 else tail)


def _clip_end(text: str, limit: int) -> str:
    """The first ``limit`` characters, ending at a word."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    space = head.rfind(" ")
    return (head[:space] if space > limit // 2 else head).rstrip(" ,;:") + "…"


def _speaker_matches(session: Any, message: Any) -> bool:
    """In a group call only the member who was cut off picks it up; outside one, the reply is the host's."""
    from .scene import prompt_scene

    scene = prompt_scene(session)
    if scene is None:
        return True
    return (speaker_of(message, scene.host.character_id) or scene.host.character_id) == scene.speaker_id


def cut_off_reply(session: Any, user_message: Any) -> CutOffReply | None:
    """The reply ``user_message`` cut into, when its speaker still has something unsaid; else ``None``."""
    earlier = [
        message for message in getattr(session, "messages", None) or []
        if message.id != user_message.id and message.role != "system" and not (message.metadata or {}).get("transient")
    ]
    if not earlier:
        return None
    message = earlier[-1]
    if message.role != "assistant" or (message.metadata or {}).get("delivery_status") != "interrupted":
        return None
    said, asked = _timestamp(message.created_at), _timestamp(getattr(user_message, "created_at", None))
    if said is None or asked is None or not 0 <= (asked - said).total_seconds() <= RESUME_WINDOW_SECONDS:
        return None
    content = str(message.content or "")
    end = _bounded_content_end(_delivery_metadata(message).get("context_delivered_text_end"), len(content))
    if end <= 0:
        return None  # nothing heard: not a reply in progress that they spoke over
    heard = " ".join(strip_sound_tags(content[:end]).split())
    unheard = " ".join(strip_sound_tags(content[end:]).split())
    if len(unheard) < MIN_UNHEARD_CHARS or not heard or not _speaker_matches(session, message):
        return None
    return CutOffReply(
        message_id=message.id,
        heard=_clip_start(heard, HEARD_TAIL_CHARS),
        unheard=_clip_end(unheard, MAX_UNHEARD_CHARS),
    )


def cut_off_reply_prompt(reply: CutOffReply) -> str:
    # Quoted as JSON strings, so the reply's own text cannot close the quotes it is written in.
    return CUT_OFF_REPLY_TEMPLATE.format(
        heard=json.dumps(reply.heard, ensure_ascii=False),
        unheard=json.dumps(reply.unheard, ensure_ascii=False),
    )


__all__ = ["CUT_OFF_REPLY_TEMPLATE", "CutOffReply", "RESUME_WINDOW_SECONDS", "cut_off_reply", "cut_off_reply_prompt"]
