from __future__ import annotations

from typing import Any, Dict

COMBAT_J19_J36_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "combat_ui_payload_smoke": {
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
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"]
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15
                    },
                    {
                        "item_id": "item:padded_armor",
                        "definition_id": "def:padded_armor",
                        "name": "padded armor",
                        "aliases": ["armor"]
                    }
                ],
                "equipment": {
                    "main_hand": "item:hunting_bow",
                    "ammo": "item:iron_arrow_stack_a",
                    "body": "item:padded_armor"
                },
                "carry_capacity": 50.0
            },
            "party_state": {
                "max_size": 4,
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern_road",
                        "current_role": "Displaced tavern keeper",
                        "identity_arc": "revenge_after_losing_tavern",
                        "active_motivations": ["revenge"],
                        "loyalty": 35,
                        "inventory": {
                            "items": [
                                {
                                    "item_id": "item:bran_rusty_dagger",
                                    "definition_id": "def:rusty_dagger",
                                    "name": "rusty dagger",
                                    "aliases": ["dagger"]
                                }
                            ],
                            "equipment": {
                                "main_hand": "item:bran_rusty_dagger"
                            },
                            "carry_capacity": 50.0
                        }
                    }
                ]
            }
        },
        "turns": [
            "I attack the bandit.",
            "__manual_resolve_current_combat_actor__",
            "__manual_resolve_current_combat_actor__"
        ]
    },
    "combat_state_initiative_turn_gating": {
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
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"]
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15
                    },
                    {
                        "item_id": "item:padded_armor",
                        "definition_id": "def:padded_armor",
                        "name": "padded armor",
                        "aliases": ["armor"]
                    }
                ],
                "equipment": {
                    "main_hand": "item:hunting_bow",
                    "ammo": "item:iron_arrow_stack_a",
                    "body": "item:padded_armor"
                },
                "carry_capacity": 50.0
            },
            "party_state": {
                "max_size": 4,
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern_road",
                        "current_role": "Displaced tavern keeper",
                        "identity_arc": "revenge_after_losing_tavern",
                        "active_motivations": ["revenge"],
                        "loyalty": 35,
                        "inventory": {
                            "items": [
                                {
                                    "item_id": "item:bran_rusty_dagger",
                                    "definition_id": "def:rusty_dagger",
                                    "name": "rusty dagger",
                                    "aliases": ["dagger"]
                                }
                            ],
                            "equipment": {
                                "main_hand": "item:bran_rusty_dagger"
                            },
                            "carry_capacity": 50.0
                        }
                    }
                ]
            }
        },
        "turns": [
            "I attack the bandit.",
            "I attack the bandit.",
            "__manual_advance_combat_turn__",
            "I attack the bandit."
        ]
    },
    "combat_actions_damage_defeat": {
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
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"]
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15
                    },
                    {
                        "item_id": "item:padded_armor",
                        "definition_id": "def:padded_armor",
                        "name": "padded armor",
                        "aliases": ["armor"]
                    }
                ],
                "equipment": {
                    "main_hand": "item:hunting_bow",
                    "ammo": "item:iron_arrow_stack_a",
                    "body": "item:padded_armor"
                },
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []}
        },
        "turns": [
            "I attack the bandit.",
            "__manual_force_player_combat_turn__",
            "I attack the bandit.",
            "__manual_force_player_combat_turn__",
            "I attack the bandit."
        ]
    },
    "companion_combat_participation": {
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
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"]
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15
                    }
                ],
                "equipment": {
                    "main_hand": "item:hunting_bow",
                    "ammo": "item:iron_arrow_stack_a"
                },
                "carry_capacity": 50.0
            },
            "party_state": {
                "max_size": 4,
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern_road",
                        "current_role": "Displaced tavern keeper",
                        "identity_arc": "revenge_after_losing_tavern",
                        "active_motivations": ["revenge", "protect the party"],
                        "loyalty": 35,
                        "inventory": {
                            "items": [
                                {
                                    "item_id": "item:bran_rusty_dagger",
                                    "definition_id": "def:rusty_dagger",
                                    "name": "rusty dagger",
                                    "aliases": ["dagger"]
                                }
                            ],
                            "equipment": {
                                "main_hand": "item:bran_rusty_dagger"
                            },
                            "carry_capacity": 50.0
                        }
                    }
                ]
            }
        },
        "turns": [
            "I attack the bandit.",
            "__manual_resolve_current_combat_actor__",
            "__manual_resolve_current_combat_actor__",
            "__manual_force_player_combat_turn__",
            "I attack the bandit."
        ]
    },
    "enemy_combat_ai_party_defeat": {
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
                "current_actor_id": "enemy:bandit_1",
                "initiative_order": [
                    {
                        "actor_id": "enemy:bandit_1",
                        "initiative": 20,
                        "roll": 20,
                        "bonus": 0
                    },
                    {
                        "actor_id": "player",
                        "initiative": 1,
                        "roll": 1,
                        "bonus": 0
                    }
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
                "source": "manual_enemy_combat_test"
            }
        },
        "turns": [
            "I attack the bandit."
        ]
    },
    "combat_llm_attack_narration": {
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
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"]
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15
                    }
                ],
                "equipment": {
                    "main_hand": "item:hunting_bow",
                    "ammo": "item:iron_arrow_stack_a"
                },
                "carry_capacity": 50.0
            },
            "party_state": {"max_size": 4, "companions": []}
        },
        "turns": [
            "I attack the bandit.",
            "__manual_force_player_combat_turn__",
            "I attack the bandit."
        ]
    },
    "combat_llm_defeat_narration": {
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
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"]
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15
                    }
                ],
                "equipment": {
                    "main_hand": "item:hunting_bow",
                    "ammo": "item:iron_arrow_stack_a"
                },
                "carry_capacity": 50.0
            },
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
                        "hp": 2,
                        "max_hp": 8,
                        "armor": 0,
                        "defense": 10,
                        "initiative_bonus": 0,
                        "status": "active",
                        "loot_table_id": "loot:bandit_common"
                    }
                },
                "combat_log": [],
                "source": "manual_combat_llm_defeat_test"
            },
            "party_state": {"max_size": 4, "companions": []}
        },
        "turns": [
            "I attack the bandit."
        ]
    },
    "combat_llm_party_defeat_narration": {
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
                "source": "manual_combat_llm_party_defeat_test"
            }
        },
        "turns": [
            "I attack the bandit."
        ]
    },
}
