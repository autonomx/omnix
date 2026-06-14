from __future__ import annotations

import re
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import DIALOGUE_MEMORY_LIMIT, RETRIEVAL_LIMIT, bounded, d, i, l, s


def _query_tokens(player_input: str) -> set[str]:
    stop = {
        "the",
        "and",
        "you",
        "your",
        "what",
        "about",
        "tell",
        "me",
        "do",
        "did",
        "can",
        "i",
        "a",
        "an",
        "is",
        "are",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9']+", s(player_input).lower())
        if len(token) >= 3 and token not in stop
    }


def _visible_to(entry: Mapping[str, Any], addressed_actor_id: str) -> bool:
    if s(entry.get("visibility")) != "private" or not addressed_actor_id:
        return True
    allowed = {s(value) for value in l(entry.get("listener_ids")) if s(value)} | {s(entry.get("speaker_id"))}
    return addressed_actor_id in allowed


def _memory_haystack(entry: Mapping[str, Any]) -> str:
    return " ".join(
        [
            s(entry.get("player_text")),
            s(entry.get("summary")),
            s(entry.get("npc_line")),
            " ".join(s(tag) for tag in l(entry.get("topic_tags"))),
            " ".join(s(fact.get("value")) for fact in l(entry.get("facts")) if isinstance(fact, Mapping)),
        ]
    ).lower()


def retrieve_relevant_memories(
    memory: Mapping[str, Any],
    *,
    player_input: str,
    addressed_actor_id: str = "",
    location_id: str = "",
    limit: int = RETRIEVAL_LIMIT,
) -> list[dict[str, Any]]:
    tokens = _query_tokens(player_input)
    recall_terms = ("remember", "name", "called", "trail name", "what did i")
    wants_recall = any(term in s(player_input).lower() for term in recall_terms)
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in bounded(l(d(memory).get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT):
        if not _visible_to(entry, addressed_actor_id):
            continue
        score = float(entry.get("salience") or 0.0)
        score += sum(1 for token in tokens if token in _memory_haystack(entry)) * 0.4
        if wants_recall and l(entry.get("facts")):
            score += 2.0
        if addressed_actor_id and addressed_actor_id in {s(value) for value in l(entry.get("listener_ids"))}:
            score += 1.5
        if location_id and location_id == s(entry.get("location_id")):
            score += 0.5
        if score > 0.0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], -i(item[1].get("tick"), 0), s(item[1].get("id"))))
    return [dict(entry, retrieval_score=round(score, 3)) for score, entry in scored[: max(1, int(limit))]]
