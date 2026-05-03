"""Deterministic RPG spatial scene graph helpers.

The spatial package is simulation-authoritative.  It answers questions such as:

- where is an entity?
- can an entity move between areas?
- can an entity see another entity?
- can an entity hear another entity?

LLM narration may describe these results, but must not invent them.
"""

from app.rpg.spatial.audibility import (
    audible_entities_from,
    can_hear_area,
    can_hear_entity,
)
from app.rpg.spatial.graph import (
    ensure_spatial_graph,
    find_connection,
    get_entity_area,
    get_spatial_graph,
    list_area_connections,
    list_entities_in_area,
    set_entity_area,
)
from app.rpg.spatial.movement import can_move_between, move_entity
from app.rpg.spatial.serialization import normalize_spatial_graph
from app.rpg.spatial.visibility import (
    can_see_area,
    can_see_entity,
    visible_entities_from,
)

__all__ = [
    "audible_entities_from",
    "can_hear_area",
    "can_hear_entity",
    "can_move_between",
    "can_see_area",
    "can_see_entity",
    "ensure_spatial_graph",
    "find_connection",
    "get_entity_area",
    "get_spatial_graph",
    "list_area_connections",
    "list_entities_in_area",
    "move_entity",
    "normalize_spatial_graph",
    "set_entity_area",
    "visible_entities_from",
]