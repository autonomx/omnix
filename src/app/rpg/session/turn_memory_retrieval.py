from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import DIALOGUE_MEMORY_LIMIT, RETRIEVAL_LIMIT, bounded, d, i, l, s
from app.rpg.session.turn_memory_retrieval_helpers import memory_haystack, query_tokens, visible_to


def _score_entry(
    entry: Mapping[str, Any],
    *,
    tokens: set[str],
    wants_recall: bool,
    addressed_actor_id: str,
    location_id: str,
) -> float:
    score = float(entry.get("salience") or 0.0)
    score += sum(1 for token in tokens if token in memory_haystack(entry)) * 0.4
    if wants_recall and l(entry.get("facts")):
        score += 2.0
    if addressed_actor_id and addressed_actor_id in {s(value) for value in l(entry.get("listener_ids"))}:
        score += 1.5
    if location_id and location_id == s(entry.get("location_id")):
        score += 0.5
    return score


def retrieve_relevant_memories(
    memory: Mapping[str, Any],
    *,
    player_input: str,
    addressed_actor_id: str = "",
    location_id: str = "",
    limit: int = RETRIEVAL_LIMIT,
) -> list[dict[str, Any]]:
    recall_terms = ("remember", "name", "called", "trail name", "what did i")
    wants_recall = any(term in s(player_input).lower() for term in recall_terms)
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in bounded(l(d(memory).get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT):
        if not visible_to(entry, addressed_actor_id):
            continue
        score = _score_entry(
            entry,
            tokens=query_tokens(player_input),
            wants_recall=wants_recall,
            addressed_actor_id=addressed_actor_id,
            location_id=location_id,
        )
        if score > 0.0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], -i(item[1].get("tick"), 0), s(item[1].get("id"))))
    return [dict(entry, retrieval_score=round(score, 3)) for score, entry in scored[: max(1, int(limit))]]
