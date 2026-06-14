from __future__ import annotations

import re
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import l, s

_STOP_WORDS = {
    "the", "and", "you", "your", "what", "about", "tell", "me", "do", "did", "can", "i", "a", "an", "is", "are"
}


def query_tokens(player_input: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", s(player_input).lower())
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def visible_to(entry: Mapping[str, Any], addressed_actor_id: str) -> bool:
    if s(entry.get("visibility")) != "private" or not addressed_actor_id:
        return True
    allowed = {s(value) for value in l(entry.get("listener_ids")) if s(value)} | {s(entry.get("speaker_id"))}
    return addressed_actor_id in allowed


def memory_haystack(entry: Mapping[str, Any]) -> str:
    return " ".join(
        [
            s(entry.get("player_text")),
            s(entry.get("summary")),
            s(entry.get("npc_line")),
            " ".join(s(tag) for tag in l(entry.get("topic_tags"))),
            " ".join(s(fact.get("value")) for fact in l(entry.get("facts")) if isinstance(fact, Mapping)),
        ]
    ).lower()
