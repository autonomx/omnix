from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_collect import collect_scored
from app.rpg.session.turn_memory_common import (
    DIALOGUE_MEMORY_LIMIT,
    RETRIEVAL_LIMIT,
    bounded,
    d,
    l,
    s,
)
from app.rpg.session.turn_memory_order import memory_order
from app.rpg.session.turn_memory_retrieval_helpers import memory_tokens

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
    memories = bounded(l(d(memory).get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT)
    scored = collect_scored(
        memories,
        tokens=memory_tokens(player_input),
        recall=recall,
        actor_id=addressed_actor_id,
        location_id=location_id,
    )
    scored.sort(key=memory_order)
    return [dict(entry, retrieval_score=round(score, 3)) for score, entry in scored[:limit]]
