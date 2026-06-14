from __future__ import annotations

from typing import Any

from app.rpg.session.turn_memory_rank import memory_score
from app.rpg.session.turn_memory_retrieval_helpers import memory_visible


def collect_scored(
    memories: list[dict[str, Any]],
    *,
    tokens: set[str],
    recall: bool,
    actor_id: str,
    location_id: str,
) -> list[tuple[float, dict[str, Any]]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in memories:
        if not memory_visible(entry, actor_id):
            continue
        score = memory_score(
            entry,
            tokens=tokens,
            recall=recall,
            actor_id=actor_id,
            location_id=location_id,
        )
        if score > 0:
            scored.append((score, entry))
    return scored
