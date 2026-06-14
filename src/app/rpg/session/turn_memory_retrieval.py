from __future__ import annotations

import re
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import DIALOGUE_MEMORY_LIMIT, RETRIEVAL_LIMIT, bounded, d, i, l, s

_STOP_WORDS = {"the", "and", "you", "your", "what", "about", "tell", "me", "did", "can", "are"}


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9']+", s(text).lower()) if len(token) >= 3 and token not in _STOP_WORDS}


def _visible(entry: Mapping[str, Any], actor_id: str) -> bool:
    if s(entry.get("visibility")) != "private" or not actor_id:
        return True
    return actor_id in {s(value) for value in l(entry.get("listener_ids"))}


def _haystack(entry: Mapping[str, Any]) -> str:
    facts = " ".join(s(fact.get("value")) for fact in l(entry.get("facts")) if isinstance(fact, Mapping))
    return " ".join([s(entry.get("player_text")), s(entry.get("npc_line")), facts]).lower()


def _score(entry: Mapping[str, Any], *, tokens: set[str], recall: bool, actor_id: str, location_id: str) -> float:
    score = float(entry.get("salience") or 0.0)
    score += sum(1 for token in tokens if token in _haystack(entry)) * 0.4
    if recall and l(entry.get("facts")):
        score += 2.0
    if actor_id and actor_id in {s(value) for value in l(entry.get("listener_ids"))}:
        score += 1.5
    if location_id and location_id == s(entry.get("location_id")):
        score += 0.5
    return score


def retrieve_relevant_memories(memory: Mapping[str, Any], *, player_input: str, addressed_actor_id: str = "", location_id: str = "", limit: int = RETRIEVAL_LIMIT) -> list[dict[str, Any]]:
    recall = any(term in s(player_input).lower() for term in ("remember", "name", "called", "trail name"))
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in bounded(l(d(memory).get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT):
        if _visible(entry, addressed_actor_id) and (score := _score(entry, tokens=_tokens(player_input), recall=recall, actor_id=addressed_actor_id, location_id=location_id)) > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], -i(item[1].get("tick")), s(item[1].get("id"))))
    return [dict(entry, retrieval_score=round(score, 3)) for score, entry in scored[: max(1, int(limit))]]
