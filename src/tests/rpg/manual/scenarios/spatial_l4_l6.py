from __future__ import annotations

from typing import Any, Dict

SPATIAL_L4_L6_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "combat_melee_cannot_attack_far_target": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {"enabled": True, "autonomous_ticks_enabled": False, "frequency": "never", "conversation_chance_percent": 0},
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "current_actor_id": "player",
                "initiative_order": [{"actor_id": "player", "initiative": 20}, {"actor_id": "enemy:archer_1", "initiative": 1}],
                "participants": {
                    "player": {"actor_id": "player", "side": "party", "name": "You", "hp": 20, "max_hp": 20, "status": "active", "position": {"zone": "frontline", "range_band": "near", "engaged_with": []}},
                    "enemy:archer_1": {"actor_id": "enemy:archer_1", "side": "enemy", "name": "Archer", "hp": 8, "max_hp": 8, "status": "active", "position": {"zone": "backline", "range_band": "far", "engaged_with": []}},
                },
            },
        },
        "turns": ["I attack the archer."],
    },
    "combat_reposition_moves_actor_near": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {"enabled": True, "autonomous_ticks_enabled": False, "frequency": "never", "conversation_chance_percent": 0},
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "current_actor_id": "player",
                "participants": {
                    "player": {"actor_id": "player", "side": "party", "name": "You", "hp": 20, "max_hp": 20, "status": "active", "position": {"zone": "backline", "range_band": "far"}},
                    "enemy:bandit_1": {"actor_id": "enemy:bandit_1", "side": "enemy", "name": "Bandit", "hp": 8, "max_hp": 8, "status": "active", "position": {"zone": "frontline", "range_band": "near"}},
                },
            },
        },
        "turns": ["I move closer."],
    },
    "combat_ranged_enemy_attacks_from_backline": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {"enabled": True, "autonomous_ticks_enabled": False, "frequency": "never", "conversation_chance_percent": 0},
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "current_actor_id": "enemy:archer_1",
                "initiative_order": [{"actor_id": "enemy:archer_1", "initiative": 20}, {"actor_id": "player", "initiative": 1}],
                "participants": {
                    "enemy:archer_1": {"actor_id": "enemy:archer_1", "side": "enemy", "name": "Archer", "hp": 8, "max_hp": 8, "status": "active", "tags": ["ranged", "archer"], "position": {"zone": "backline", "range_band": "far", "engaged_with": []}},
                    "player": {"actor_id": "player", "side": "party", "name": "You", "hp": 20, "max_hp": 20, "status": "active", "position": {"zone": "frontline", "range_band": "near", "engaged_with": []}},
                },
            },
        },
        "turns": ["__manual_resolve_current_combat_actor__"],
    },
    "combat_victory_emits_world_event_once": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {"enabled": True, "autonomous_ticks_enabled": False, "frequency": "never", "conversation_chance_percent": 0},
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "combat_id": "combat:world_event_bandit",
                "current_actor_id": "player",
                "initiative_order": [{"actor_id": "player", "initiative": 20}, {"actor_id": "enemy:bandit_1", "initiative": 1}],
                "participants": {
                    "player": {"actor_id": "player", "side": "party", "name": "You", "hp": 20, "max_hp": 20, "damage_min": 1, "status": "active"},
                    "enemy:bandit_1": {"actor_id": "enemy:bandit_1", "side": "enemy", "name": "Bandit", "hp": 1, "max_hp": 8, "status": "active", "tags": ["bandit"], "loot_table_id": "loot:bandit_common"},
                },
            },
        },
        "turns": ["__manual_force_next_attack_roll__:20", "__manual_force_next_damage__:1", "I attack the bandit."],
    },
    "combat_flee_emits_no_victory_world_event": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {"enabled": True, "autonomous_ticks_enabled": False, "frequency": "never", "conversation_chance_percent": 0},
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": False,
                "exit_reason": "fled",
            },
        },
        "turns": ["I flee."],
    },
    "combat_bandit_victory_lowers_bandit_pressure": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {"enabled": True, "autonomous_ticks_enabled": False, "frequency": "never", "conversation_chance_percent": 0},
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "current_actor_id": "player",
                "initiative_order": [{"actor_id": "player", "initiative": 20}],
                "participants": {
                    "player": {"actor_id": "player", "side": "party", "name": "You", "hp": 20, "max_hp": 20, "damage_min": 1, "status": "active"},
                    "enemy:bandit_1": {"actor_id": "enemy:bandit_1", "side": "enemy", "name": "Bandit", "hp": 1, "max_hp": 8, "status": "active", "tags": ["bandit"], "loot_table_id": "loot:bandit_common"},
                },
            },
        },
        "turns": ["__manual_force_next_attack_roll__:20", "__manual_force_next_damage__:1", "I attack the bandit."],
    },
}