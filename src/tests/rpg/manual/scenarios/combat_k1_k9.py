from __future__ import annotations

from typing import Any, Dict

COMBAT_K1_K9_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "combat_defend_reduces_next_incoming_attack": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
            "allow_player_invited": False,
            "player_inclusion_chance_percent": 0,
            "npc_file_profiles_enabled": True,
            "npc_evolution_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0
        },
        "setup_interaction_state": {
            "scene_items": [],
            "scene_objects": [],
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []}
        },
        "turns": [
            "I attack the bandit.",
            "__manual_force_player_combat_turn__",
            "I defend."
        ]
    },
    "combat_use_item_consumes_turn_and_applies_effect": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
            "allow_player_invited": False,
            "player_inclusion_chance_percent": 0,
            "npc_file_profiles_enabled": True,
            "npc_evolution_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0
        },
        "setup_interaction_state": {
            "scene_items": [],
            "scene_objects": [],
            "player_location_id": "loc_tavern_road",
            "player_hp": 5,
            "player_max_hp": 20,
            "player_inventory": {
                "items": [
                    {
                        "item_id": "item:minor_healing_potion",
                        "definition_id": "item:minor_healing_potion",
                        "name": "minor healing potion",
                        "aliases": ["potion", "healing potion"],
                        "qty": 1,
                        "quantity": 1
                    }
                ],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []}
        },
        "turns": [
            "I attack the bandit.",
            "__manual_force_player_combat_turn__",
            "I drink the healing potion."
        ]
    },
}