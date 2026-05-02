from __future__ import annotations

from typing import Any, Dict

INTERACTION_L1_L3_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "interaction_open_unlocked_chest": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_cellar",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "world_objects": {
                "object:old_chest": {
                    "object_id": "object:old_chest",
                    "name": "Old Chest",
                    "kind": "container",
                    "location_id": "loc_tavern_cellar",
                    "area_id": "cellar",
                    "locked": False,
                    "open": False,
                    "reachable": True,
                    "visible": True,
                    "contents": [{"item_id": "item:copper_coin", "name": "Copper coin", "quantity": 12}],
                }
            },
        },
        "turns": ["I open the chest."],
    },

    "interaction_unlock_chest_with_key": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_cellar",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {
                "items": [{"item_id": "item:iron_key", "name": "Iron key", "quantity": 1}],
                "equipment": {},
                "carry_capacity": 50.0,
            },
            "world_objects": {
                "object:old_chest": {
                    "object_id": "object:old_chest",
                    "name": "Old Chest",
                    "kind": "container",
                    "location_id": "loc_tavern_cellar",
                    "area_id": "cellar",
                    "locked": True,
                    "open": False,
                    "required_key_id": "item:iron_key",
                    "reachable": True,
                    "visible": True,
                    "contents": [{"item_id": "item:copper_coin", "name": "Copper coin", "quantity": 12}],
                }
            },
        },
        "turns": ["I use the iron key to unlock the chest."],
    },

    "interaction_unlock_chest_without_key_fails": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_cellar",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "world_objects": {
                "object:old_chest": {
                    "object_id": "object:old_chest",
                    "name": "Old Chest",
                    "kind": "container",
                    "location_id": "loc_tavern_cellar",
                    "area_id": "cellar",
                    "locked": True,
                    "open": False,
                    "required_key_id": "item:iron_key",
                    "reachable": True,
                    "visible": True,
                    "contents": [{"item_id": "item:copper_coin", "name": "Copper coin", "quantity": 12}],
                }
            },
        },
        "turns": ["I use the iron key to unlock the chest."],
    },

    "interaction_open_locked_chest_fails": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_cellar",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "world_objects": {
                "object:old_chest": {
                    "object_id": "object:old_chest",
                    "name": "Old Chest",
                    "kind": "container",
                    "location_id": "loc_tavern_cellar",
                    "area_id": "cellar",
                    "locked": True,
                    "open": False,
                    "required_key_id": "item:iron_key",
                    "reachable": True,
                    "visible": True,
                    "contents": [{"item_id": "item:copper_coin", "name": "Copper coin", "quantity": 12}],
                }
            },
        },
        "turns": ["I open the chest."],
    },

    "interaction_take_item_from_closed_chest_fails": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_cellar",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "world_objects": {
                "object:old_chest": {
                    "object_id": "object:old_chest",
                    "name": "Old Chest",
                    "kind": "container",
                    "location_id": "loc_tavern_cellar",
                    "area_id": "cellar",
                    "locked": False,
                    "open": False,
                    "reachable": True,
                    "visible": True,
                    "contents": [{"item_id": "item:copper_coin", "name": "Copper coin", "quantity": 12}],
                }
            },
        },
        "turns": ["I take the coins from the chest."],
    },

    "interaction_take_item_from_open_chest_succeeds": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_cellar",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "world_objects": {
                "object:old_chest": {
                    "object_id": "object:old_chest",
                    "name": "Old Chest",
                    "kind": "container",
                    "location_id": "loc_tavern_cellar",
                    "area_id": "cellar",
                    "locked": False,
                    "open": True,
                    "reachable": True,
                    "visible": True,
                    "contents": [{"item_id": "item:copper_coin", "name": "Copper coin", "quantity": 12}],
                }
            },
        },
        "turns": ["I take the coins from the chest."],
    },

    "interaction_unlock_door_with_key": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_rusty_flagon",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {
                "items": [{"item_id": "item:cellar_key", "name": "Cellar key", "quantity": 1}],
                "equipment": {},
                "carry_capacity": 50.0,
            },
            "world_objects": {
                "object:cellar_door": {
                    "object_id": "object:cellar_door",
                    "name": "Cellar Door",
                    "kind": "door",
                    "location_id": "loc_rusty_flagon",
                    "area_id": "common_room",
                    "locked": True,
                    "open": False,
                    "required_key_id": "item:cellar_key",
                    "reachable": True,
                    "visible": True,
                    "blocks_movement": True,
                }
            },
        },
        "turns": ["I use the cellar key to unlock the door."],
    },

    "interaction_unlock_door_without_key_fails": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_rusty_flagon",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "world_objects": {
                "object:cellar_door": {
                    "object_id": "object:cellar_door",
                    "name": "Cellar Door",
                    "kind": "door",
                    "location_id": "loc_rusty_flagon",
                    "area_id": "common_room",
                    "locked": True,
                    "open": False,
                    "required_key_id": "item:cellar_key",
                    "reachable": True,
                    "visible": True,
                    "blocks_movement": True,
                }
            },
        },
        "turns": ["I use the cellar key to unlock the door."],
    },
}