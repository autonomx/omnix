from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import (
    DIALOGUE_MEMORY_LIMIT,
    RETRIEVAL_LIMIT,
    bounded,
    d,
    i,
    l,
    s,
)
from app.rpg.session.turn_memory_rank import memory_score
from app.rpg.session.turn_memory_retrieval_helpers import memory_tokens, memory_visible

_RECALL_TERMS = ("remember", "name", "called", "trail name")


def retrieve_relevant_memories(
    memory: Mapping[str, Any],
    *,
    player_input: str,
    addressed_actor_id: str = "",
    location_id: str = "",
    limit: int = RETRIEVAL_LIMIT,
) -> list[dict[str, Any]]:
    recall = any(term in s(player_input).lower() for term in _RECALL_TERMS)
    tokens = memory_tokens(player_input)
    scored: list[tuple[float, dict[str, Any]]] = []
    memories = bounded(l(d(memory).get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT)
    for entry in memories:
        if not memory_visible(entry, addressed_actor_id):
            continue
        score = memory_score(
            entry,
            tokens=tokens,
            recall=recall,
            actor_id=addressed_actor_id,
            location_id=location_id,
        )
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], -i(item[1].get("tick")), s(item[1].get("id"))))
    return [dict(entry, retrieval_score=round(score, 3)) for score, entry in scored[:limit]]
