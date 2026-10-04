from __future__ import annotations

from typing import Any


def _entity_location(entity_id: str, area_id: str, *, hidden: bool, silent: bool) -> dict[str, Any]:
    return {"entity_id": entity_id, "area_id": area_id, "hidden": hidden, "silent": silent}


def tavern_spatial_fixture() -> dict[str, Any]:
    return {
        "graph_id": "tavern_fixture",
        "current_area_id": "tavern_common_room",
        "areas": {
            "tavern_common_room": {
                "area_id": "tavern_common_room",
                "name": "Tavern Common Room",
                "description": "A busy common room with tables, a hearth, and Bran behind the bar.",
            },
            "private_room": {
                "area_id": "private_room",
                "name": "Private Room",
                "description": "A rented room behind a wooden door.",
            },
            "cellar": {
                "area_id": "cellar",
                "name": "Cellar",
                "description": "A locked cellar below the tavern.",
            },
            "street": {
                "area_id": "street",
                "name": "Street",
                "description": "The muddy street outside the tavern.",
            },
            "kitchen": {
                "area_id": "kitchen",
                "name": "Kitchen",
                "description": "A hot kitchen connected by an open archway.",
            },
            "sealed_room": {
                "area_id": "sealed_room",
                "name": "Sealed Room",
                "description": "A room behind a solid wall.",
            },
        },
        "connections": {
            "common_private_door": {
                "connection_id": "common_private_door",
                "from_area_id": "tavern_common_room",
                "to_area_id": "private_room",
                "label": "wooden door",
                "bidirectional": True,
                "barrier_kind": "door",
                "is_open": False,
                "is_locked": False,
                "blocks_movement": False,
                "visibility": "blocked",
                "audibility": "muffled",
            },
            "common_cellar_trapdoor": {
                "connection_id": "common_cellar_trapdoor",
                "from_area_id": "tavern_common_room",
                "to_area_id": "cellar",
                "label": "locked trapdoor",
                "bidirectional": True,
                "barrier_kind": "locked_door",
                "is_open": False,
                "is_locked": True,
                "blocks_movement": False,
                "visibility": "blocked",
                "audibility": "blocked",
            },
            "common_street_front_door": {
                "connection_id": "common_street_front_door",
                "from_area_id": "tavern_common_room",
                "to_area_id": "street",
                "label": "open front door",
                "bidirectional": True,
                "barrier_kind": "door",
                "is_open": True,
                "is_locked": False,
                "blocks_movement": False,
                "visibility": "open",
                "audibility": "open",
            },
            "common_kitchen_archway": {
                "connection_id": "common_kitchen_archway",
                "from_area_id": "tavern_common_room",
                "to_area_id": "kitchen",
                "label": "open archway",
                "bidirectional": True,
                "barrier_kind": "none",
                "is_open": True,
                "is_locked": False,
                "blocks_movement": False,
                "visibility": "open",
                "audibility": "open",
            },
            "common_sealed_wall": {
                "connection_id": "common_sealed_wall",
                "from_area_id": "tavern_common_room",
                "to_area_id": "sealed_room",
                "label": "stone wall",
                "bidirectional": True,
                "barrier_kind": "wall",
                "is_open": False,
                "is_locked": False,
                "blocks_movement": True,
                "visibility": "blocked",
                "audibility": "blocked",
            },
        },
        "entity_locations": {
            entity_id: _entity_location(entity_id, area_id, hidden=hidden, silent=silent)
            for entity_id, area_id, hidden, silent in (
                ("player", "tavern_common_room", False, False),
                ("bran", "tavern_common_room", False, False),
                ("mira", "kitchen", False, False),
                ("spy", "private_room", True, False),
                ("guest_private", "private_room", False, False),
                ("sealed_guard", "sealed_room", False, False),
                ("bandit", "street", False, False),
                ("silent_rat", "tavern_common_room", False, True),
            )
        },
        "metadata": {},
    }


def tavern_spatial_fixture_with_private_door_open() -> dict[str, Any]:
    graph = tavern_spatial_fixture()
    graph["connections"]["common_private_door"]["is_open"] = True
    graph["connections"]["common_private_door"]["visibility"] = "open"
    return graph
