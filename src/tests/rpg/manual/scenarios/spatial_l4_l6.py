from __future__ import annotations

from typing import Any, Dict


SPATIAL_L4_L6_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "spatial_room_graph_basic_navigation": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I look around the tavern and check the exits"],
        "checks": [
            {
                "type": "spatial_visible_entities",
                "viewer": "player",
                "mode": "contains",
                "expected_entity_ids": ["bran", "mira", "bandit"],
            }
        ],
    },
    "spatial_closed_door_blocks_movement": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I try to walk into the private room"],
        "checks": [
            {
                "type": "spatial_can_move",
                "from_area_id": "tavern_common_room",
                "to_area_id": "private_room",
                "expected_ok": False,
                "expected_reason": "closed",
            }
        ],
    },
    "spatial_open_door_allows_movement": {
        "setup_spatial_graph": "tavern_fixture_private_door_open",
        "turns": ["I walk into the private room"],
        "checks": [
            {
                "type": "spatial_can_move",
                "from_area_id": "tavern_common_room",
                "to_area_id": "private_room",
                "expected_ok": True,
                "expected_reason": "passable",
            }
        ],
    },
    "spatial_locked_door_blocks_movement": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I try to open the locked trapdoor to the cellar"],
        "checks": [
            {
                "type": "spatial_can_move",
                "from_area_id": "tavern_common_room",
                "to_area_id": "cellar",
                "expected_ok": False,
                "expected_reason": "locked",
            }
        ],
    },
    "spatial_same_room_visibility": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I look at Bran"],
        "checks": [
            {
                "type": "spatial_visibility",
                "viewer": "player",
                "target": "bran",
                "expected_ok": True,
                "expected_reason": "same_area",
            }
        ],
    },
    "spatial_closed_door_blocks_visibility": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I look through the closed private room door"],
        "checks": [
            {
                "type": "spatial_visibility",
                "viewer": "player",
                "target": "guest_private",
                "expected_ok": False,
                "expected_reason": "blocked_by_barrier",
            }
        ],
    },
    "spatial_open_door_allows_visibility": {
        "setup_spatial_graph": "tavern_fixture_private_door_open",
        "turns": ["I look into the private room through the open door"],
        "checks": [
            {
                "type": "spatial_visibility",
                "viewer": "player",
                "target": "guest_private",
                "expected_ok": True,
                "expected_reason": "visible_connection",
            }
        ],
    },
    "spatial_wall_blocks_visibility": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I try to look through the stone wall"],
        "checks": [
            {
                "type": "spatial_visibility",
                "viewer": "player",
                "target": "sealed_guard",
                "expected_ok": False,
                "expected_reason": "blocked_by_barrier",
            }
        ],
    },
    "spatial_same_room_audibility": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I listen to Bran speaking"],
        "checks": [
            {
                "type": "spatial_audibility",
                "listener": "player",
                "source": "bran",
                "expected_ok": True,
                "expected_reason": "same_area",
            }
        ],
    },
    "spatial_closed_door_muffles_audibility": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I listen at the closed private room door"],
        "checks": [
            {
                "type": "spatial_audibility",
                "listener": "player",
                "source": "spy",
                "expected_ok": True,
                "expected_reason": "muffled_by_barrier",
            }
        ],
    },
    "spatial_wall_blocks_audibility": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I listen through the stone wall"],
        "checks": [
            {
                "type": "spatial_audibility",
                "listener": "player",
                "source": "sealed_guard",
                "expected_ok": False,
                "expected_reason": "blocked_by_barrier",
            }
        ],
    },
    "spatial_hidden_npc_not_visible": {
        "setup_spatial_graph": "tavern_fixture_private_door_open",
        "turns": ["I look into the private room"],
        "checks": [
            {
                "type": "spatial_visibility",
                "viewer": "player",
                "target": "spy",
                "expected_ok": False,
                "expected_reason": "hidden",
            }
        ],
    },
    "spatial_visible_present_npcs_only": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I look around the tavern"],
        "checks": [
            {
                "type": "spatial_visible_entities",
                "viewer": "player",
                "mode": "contains",
                "expected_entity_ids": ["bran", "mira", "bandit"],
            }
        ],
    },
    "spatial_move_updates_current_area": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I walk out through the front door into the street"],
        "checks": [
            {
                "type": "spatial_can_move",
                "from_area_id": "tavern_common_room",
                "to_area_id": "street",
                "expected_ok": True,
                "expected_reason": "passable",
            },
            {
                "type": "spatial_current_area",
                "entity": "player",
                "expected_area_id": "tavern_common_room",
            }
        ],
    },
    "spatial_scene_graph_save_load_stability": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I look around to check the tavern layout"],
        "checks": [
            {
                "type": "spatial_can_move",
                "from_area_id": "tavern_common_room",
                "to_area_id": "street",
                "expected_ok": True,
                "expected_reason": "passable",
            }
        ],
    },
}