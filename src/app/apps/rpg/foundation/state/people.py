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


__all__ = ["world_people"]
