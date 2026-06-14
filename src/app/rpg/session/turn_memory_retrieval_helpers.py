from __future__ import annotations

import re
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import l, s

_STOP_WORDS = {
    "the",
    "and",
    "you",
    "your",
    "what",
    "about",
    "tell",
    "me",
    "did",
    "can",
    "are",
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
    return actor_id in {s(value) for value in l(entry.get("listener_ids"))}


def memory_score(
    entry: Mapping[str, Any],
    *,
    tokens: set[str],
    recall: bool,
    actor_id: str,
    location_id: str,
) -> float:
    facts = " ".join(
        s(fact.get("value")) for fact in l(entry.get("facts")) if isinstance(fact, Mapping)
    )
    haystack = " ".join([s(entry.get("player_text")), s(entry.get("npc_line")), facts]).lower()
    score = float(entry.get("salience") or 0.0)
    score += sum(1 for token in tokens if token in haystack) * 0.4
    if recall and l(entry.get("facts")):
        score += 2.0
    if actor_id and actor_id in {s(value) for value in l(entry.get("listener_ids"))}:
        score += 1.5
    if location_id and location_id == s(entry.get("location_id")):
        score += 0.5
    return score
