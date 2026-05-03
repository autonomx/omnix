from __future__ import annotations

from typing import Any, Dict


def tavern_spatial_fixture() -> Dict[str, Any]:
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
            "player": {
                "entity_id": "player",
                "area_id": "tavern_common_room",
                "hidden": False,
                "silent": False,
            },
            "bran": {
                "entity_id": "bran",
                "area_id": "tavern_common_room",
                "hidden": False,
                "silent": False,
            },
            "mira": {
                "entity_id": "mira",
                "area_id": "kitchen",
                "hidden": False,
                "silent": False,
            },
            "spy": {
                "entity_id": "spy",
                "area_id": "private_room",
                "hidden": True,
                "silent": False,
            },
            "guest_private": {
                "entity_id": "guest_private",
                "area_id": "private_room",
                "hidden": False,
                "silent": False,
            },
            "sealed_guard": {
                "entity_id": "sealed_guard",
                "area_id": "sealed_room",
                "hidden": False,
                "silent": False,
            },
            "bandit": {
                "entity_id": "bandit",
                "area_id": "street",
                "hidden": False,
                "silent": False,
            },
            "silent_rat": {
                "entity_id": "silent_rat",
                "area_id": "tavern_common_room",
                "hidden": False,
                "silent": True,
            },
        },
        "metadata": {},
    }


def tavern_spatial_fixture_with_private_door_open() -> Dict[str, Any]:
    graph = tavern_spatial_fixture()
    graph["connections"]["common_private_door"]["is_open"] = True
    graph["connections"]["common_private_door"]["visibility"] = "open"
    return graph