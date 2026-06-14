from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import l, s


def score_memory_entry(
    entry: Mapping[str, Any],
    *,
    tokens: set[str],
    haystack: str,
    wants_recall: bool,
    addressed_actor_id: str,
    location_id: str,
) -> float:
    score = float(entry.get("salience") or 0.0)
    score += sum(1 for token in tokens if token in haystack) * 0.4
    if wants_recall and l(entry.get("facts")):
        score += 2.0
    listener_ids = {s(value) for value in l(entry.get("listener_ids"))}
    if addressed_actor_id and addressed_actor_id in listener_ids:
        score += 1.5
    if location_id and location_id == s(entry.get("location_id")):
        score += 0.5
    return score
