from __future__ import annotations

from typing import Any, Dict

COMBAT_J19_J36_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "combat_victory_grants_xp_once": {
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
            "player_inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "encounter_id": "enc:bandit_ambush",
                "round": 1,
                "turn_index": 0,
                "current_actor_id": "player",
                "initiative_order": [
                    {"actor_id": "player", "initiative": 20, "roll": 20, "bonus": 0},
                    {"actor_id": "enemy:bandit_1", "initiative": 1, "roll": 1, "bonus": 0}
                ],
                "participants": {
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 20,
                        "max_hp": 20,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active"
                    },
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 1,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active",
                        "loot_table_id": "loot:bandit_common"
                    }
                },
                "combat_log": [],
                "source": "manual_combat_victory_test"
            }
        },
        "turns": [
            "I attack the bandit."
        ]
    },
    "combat_flee_grants_no_loot_or_xp": {
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
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "encounter_id": "enc:bandit_ambush",
                "round": 1,
                "turn_index": 1,
                "current_actor_id": "player",
                "initiative_order": [
                    {"actor_id": "enemy:bandit_1", "initiative": 20, "roll": 20, "bonus": 0},
                    {"actor_id": "player", "initiative": 1, "roll": 1, "bonus": 0}
                ],
                "participants": {
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 8,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "damage_min": 3,
                        "damage_max": 4,
                        "accuracy_bonus": 5,
                        "initiative_bonus": 0,
                        "status": "active",
                        "loot_table_id": "loot:bandit_common"
                    },
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 5,
                        "max_hp": 20,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active"
                    }
                },
                "combat_log": [
                    {
                        "kind": "attack",
                        "round": 1,
                        "turn_index": 0,
                        "actor_id": "enemy:bandit_1",
                        "target_id": "player",
                        "attack_roll": 12,
                        "attack_total": 17,
                        "equipment_accuracy_bonus": 5,
                        "morale_accuracy_bonus": 0,
                        "target_defense": 10,
                        "hit": True,
                        "damage_roll": 3,
                        "morale_damage_bonus": 0,
                        "armor_reduction": 0,
                        "damage_applied": 3,
                        "target_hp_before": 8,
                        "target_hp_after": 5,
                        "defeated": False,
                        "tick": 1
                    }
                ],
                "source": "manual_combat_flee_test"
            }
        },
        "turns": [
            "I try to flee from combat."
        ]
    },
    "combat_post_victory_returns_to_world_actions": {
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
            "player_inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": False,
                "encounter_id": "enc:bandit_ambush",
                "round": 1,
                "turn_index": 1,
                "current_actor_id": "",
                "exit_reason": "victory",
                "winner_ids": ["player"],
                "loser_ids": ["enemy:bandit_1"],
                "initiative_order": [
                    {"actor_id": "enemy:bandit_1", "initiative": 20, "roll": 20, "bonus": 0},
                    {"actor_id": "player", "initiative": 1, "roll": 1, "bonus": 0}
                ],
                "participants": {
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 0,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "damage_min": 3,
                        "damage_max": 4,
                        "accuracy_bonus": 5,
                        "initiative_bonus": 0,
                        "status": "downed",
                        "loot_table_id": "loot:bandit_common"
                    },
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 20,
                        "max_hp": 20,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active"
                    }
                },
                "combat_log": [
                    {
                        "kind": "attack",
                        "round": 1,
                        "turn_index": 0,
                        "actor_id": "player",
                        "target_id": "enemy:bandit_1",
                        "attack_roll": 15,
                        "attack_total": 20,
                        "equipment_accuracy_bonus": 0,
                        "morale_accuracy_bonus": 0,
                        "target_defense": 10,
                        "hit": True,
                        "damage_roll": 5,
                        "morale_damage_bonus": 0,
                        "armor_reduction": 0,
                        "damage_applied": 5,
                        "target_hp_before": 5,
                        "target_hp_after": 0,
                        "defeated": True,
                        "tick": 1
                    }
                ],
                "pending_npc_turn": False,
                "defense_modifiers": {},
                "source": "manual_combat_post_victory_test"
            }
        },
        "turns": [
            "I look around."
        ]
    },
    "combat_post_combat_clears_temporary_modifiers": {
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
            "player_inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": False,
                "encounter_id": "enc:bandit_ambush",
                "round": 1,
                "turn_index": 1,
                "current_actor_id": "",
                "exit_reason": "victory",
                "winner_ids": ["player"],
                "loser_ids": ["enemy:bandit_1"],
                "initiative_order": [
                    {"actor_id": "enemy:bandit_1", "initiative": 20, "roll": 20, "bonus": 0},
                    {"actor_id": "player", "initiative": 1, "roll": 1, "bonus": 0}
                ],
                "participants": {
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 0,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "damage_min": 3,
                        "damage_max": 4,
                        "accuracy_bonus": 5,
                        "initiative_bonus": 0,
                        "status": "downed",
                        "loot_table_id": "loot:bandit_common"
                    },
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 20,
                        "max_hp": 20,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active"
                    }
                },
                "combat_log": [
                    {
                        "kind": "attack",
                        "round": 1,
                        "turn_index": 0,
                        "actor_id": "player",
                        "target_id": "enemy:bandit_1",
                        "attack_roll": 15,
                        "attack_total": 20,
                        "equipment_accuracy_bonus": 0,
                        "morale_accuracy_bonus": 0,
                        "target_defense": 10,
                        "hit": True,
                        "damage_roll": 5,
                        "morale_damage_bonus": 0,
                        "armor_reduction": 0,
                        "damage_applied": 5,
                        "target_hp_before": 5,
                        "target_hp_after": 0,
                        "defeated": True,
                        "tick": 1
                    }
                ],
                "pending_npc_turn": False,
                "defense_modifiers": {},
                "source": "manual_combat_cleanup_test"
            }
        },
        "turns": [
            "I check my status."
        ]
    },
    "combat_victory_generates_loot_once": {
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
            "player_inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "encounter_id": "enc:bandit_ambush",
                "round": 1,
                "turn_index": 0,
                "current_actor_id": "player",
                "initiative_order": [
                    {"actor_id": "player", "initiative": 20, "roll": 20, "bonus": 0},
                    {"actor_id": "enemy:bandit_1", "initiative": 1, "roll": 1, "bonus": 0}
                ],
                "participants": {
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 20,
                        "max_hp": 20,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active"
                    },
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 1,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active",
                        "loot_table_id": "loot:bandit_common"
                    }
                },
                "combat_log": [],
                "source": "manual_combat_loot_test"
            }
        },
        "turns": [
            "I attack the bandit."
        ]
    },
    "combat_party_defeat_grants_no_player_loot": {
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
            "player_hp": 3,
            "player_max_hp": 20,
            "player_inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "encounter_id": "enc:bandit_ambush",
                "round": 1,
                "turn_index": 0,
                "current_actor_id": "player",
                "initiative_order": [
                    {"actor_id": "player", "initiative": 20, "roll": 20, "bonus": 0},
                    {"actor_id": "enemy:bandit_1", "initiative": 1, "roll": 1, "bonus": 0}
                ],
                "participants": {
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 8,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "damage_min": 3,
                        "damage_max": 4,
                        "accuracy_bonus": 5,
                        "initiative_bonus": 0,
                        "status": "active",
                        "loot_table_id": "loot:bandit_common"
                    },
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 3,
                        "max_hp": 20,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active"
                    }
                },
                "combat_log": [],
                "source": "manual_combat_party_defeat_test"
            }
        },
        "turns": [
            "I attack the bandit."
        ]
    },
    "manual_party_defeat_text_artifact_has_body": {
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
            "player_hp": 3,
            "player_max_hp": 20,
            "player_inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "encounter_id": "enc:bandit_ambush",
                "round": 1,
                "turn_index": 0,
                "current_actor_id": "player",
                "initiative_order": [
                    {"actor_id": "player", "initiative": 20, "roll": 20, "bonus": 0},
                    {"actor_id": "enemy:bandit_1", "initiative": 1, "roll": 1, "bonus": 0}
                ],
                "participants": {
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 8,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "damage_min": 3,
                        "damage_max": 4,
                        "accuracy_bonus": 5,
                        "initiative_bonus": 0,
                        "status": "active",
                        "loot_table_id": "loot:bandit_common"
                    },
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 3,
                        "max_hp": 20,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active"
                    }
                },
                "combat_log": [],
                "source": "manual_combat_party_defeat_artifact_test"
            }
        },
        "turns": [
            "I attack the bandit."
        ]
    },
}
