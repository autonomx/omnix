from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import l, s
from app.rpg.session.turn_memory_retrieval_helpers import memory_haystack


def memory_score(
    entry: Mapping[str, Any],
    *,
    tokens: set[str],
    recall: bool,
    actor_id: str,
    location_id: str,
) -> float:
    score = float(entry.get("salience") or 0.0)
    haystack = memory_haystack(entry)
    score += sum(1 for token in tokens if token in haystack) * 0.4
    if recall and l(entry.get("facts")):
        score += 2.0
    listener_ids = {s(value) for value in l(entry.get("listener_ids"))}
    if actor_id and actor_id in listener_ids:
        score += 1.5
    if location_id and location_id == s(entry.get("location_id")):
        score += 0.5
    return score
