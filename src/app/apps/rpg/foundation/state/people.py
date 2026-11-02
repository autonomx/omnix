"""The world's people as a campaign's simulation state holds them: its world model's rows (``world_model.npcs``, as
a published world's setup builds them), with what the session's own index adds about each (``npc_index``)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def world_people(simulation_state: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The world's people by id; the world model's row wins over the index's for what both say."""
    simulation = _mapping(simulation_state)
    people = {str(npc_id): _mapping(row) for npc_id, row in _mapping(_mapping(simulation.get("world_model")).get("npcs")).items()}
    for npc_id, row in _mapping(simulation.get("npc_index")).items():
        people[str(npc_id)] = {**_mapping(row), **people.get(str(npc_id), {})}
    return people


# What a name may open with that is no name: a rank, a calling, a station (the playtest: "Princess Seraphine
# Valecourt" was "Princess" in passing).
TITLES = frozenset({"dr", "doctor", "inspector", "captain", "sergeant", "commander", "general", "lieutenant", "lady",
                    "lord", "sir", "dame", "master", "mistress", "brother", "sister", "father", "mother", "elder",
                    "magister", "princess", "prince", "queen", "king", "archon", "saint", "professor", "mr", "mrs",
                    "ms", "madam", "high", "grand"})


def called(name: str) -> str:
    """What someone goes by in passing: the first word of their name after any title ("Dr. Selene Kade": Selene;
    "Princess Seraphine Valecourt": Seraphine)."""
    words = [word for word in str(name or "").split() if word]
    while len(words) > 1 and words[0].casefold().rstrip(".") in TITLES:
        words = words[1:]
    return words[0] if words else ""


__all__ = ["TITLES", "called", "world_people"]
