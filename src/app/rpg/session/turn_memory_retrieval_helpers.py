from __future__ import annotations

import re
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import l, s

_STOP_WORDS = {
    "the", "and", "you", "your", "what", "about",
    "tell", "me", "did", "can", "are",
}


def memory_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", s(text).lower())
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def memory_visible(entry: Mapping[str, Any], actor_id: str) -> bool:
    if s(entry.get("visibility")) != "private" or not actor_id:
        return True
    listeners = {s(value) for value in l(entry.get("listener_ids"))}
    return actor_id in listeners


def memory_haystack(entry: Mapping[str, Any]) -> str:
    facts = " ".join(
        s(fact.get("value"))
        for fact in l(entry.get("facts"))
        if isinstance(fact, Mapping)
    )
    return " ".join([
        s(entry.get("player_text")),
        s(entry.get("npc_line")),
        facts,
    ]).lower()
