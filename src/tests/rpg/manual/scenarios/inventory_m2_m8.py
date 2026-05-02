from __future__ import annotations

from typing import Any, Dict


INVENTORY_M2_M8_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "general_interaction_runtime": {
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
            "thread_cooldown_ticks": 0,
        },
        "setup_interaction_state": {
            "scene_objects": [
                {
                    "object_id": "obj:broken_cart",
                    "name": "broken cart",
                    "aliases": ["cart", "wagon"],
                    "location_id": "loc_tavern_road",
                    "state": {"condition": "broken"},
                },
                {
                    "object_id": "obj:locked_chest",
                    "name": "locked chest",
                    "aliases": ["chest"],
                    "location_id": "loc_tavern_road",
                    "state": {"locked": True, "open": False},
                },
            ],
            "scene_items": [
                {
                    "item_id": "item:rusty_key",
                    "name": "rusty key",
                    "aliases": ["key"],
                    "location_id": "loc_tavern_road",
                },
                {
                    "item_id": "item:rope",
                    "name": "rope",
                    "aliases": ["length of rope"],
                    "location_id": "loc_tavern_road",
                },
            ],
            "player_location_id": "loc_tavern_road",
        },
        "turns": [
            "I inspect the broken cart.",
            "I open the locked chest.",
            "I pick up the rusty key.",
            "I use the rope on the broken cart.",
            "I repair the broken cart with the rope.",
        ],
    },
    "inventory_item_interaction_runtime": {
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
            "scene_items": [
                {
                    "item_id": "item:rusty_key",
                    "name": "rusty key",
                    "aliases": ["key"],
                    "location_id": "loc_tavern_road",
                    "kind": "key"
                },
                {
                    "item_id": "item:rusty_dagger",
                    "name": "rusty dagger",
                    "aliases": ["dagger"],
                    "location_id": "loc_tavern_road",
                    "kind": "weapon",
                    "slot": "main_hand"
                }
            ],
            "scene_objects": [],
            "player_location_id": "loc_tavern_road",
            "player_inventory": {
                "items": [
                    {
                        "item_id": "item:small_knife",
                        "name": "small knife",
                        "aliases": ["knife"],
                        "kind": "weapon",
                        "slot": "main_hand"
                    }
                ],
                "equipment": {}
            },
            "party_state": {
                "max_size": 3,
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern_road"
                    }
                ]
            }
        },
        "turns": [
            "I pick up the rusty key.",
            "I drop the rusty key.",
            "I pick up the rusty dagger.",
            "I equip the rusty dagger.",
            "I give the small knife to Bran."
        ],
    },
    "inventory_item_model_stacking_weight_encumbrance": {
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
            "scene_items": [
                {
                    "item_id": "item:iron_arrow_stack_a",
                    "definition_id": "def:iron_arrow",
                    "name": "iron arrows",
                    "aliases": ["arrows", "iron arrow"],
                    "quantity": 5,
                    "location_id": "loc_tavern_road"
                },
                {
                    "item_id": "item:iron_arrow_stack_b",
                    "definition_id": "def:iron_arrow",
                    "name": "iron arrows",
                    "aliases": ["arrows", "iron arrow"],
                    "quantity": 10,
                    "location_id": "loc_tavern_road"
                },
                {
                    "item_id": "item:rusty_dagger",
                    "definition_id": "def:rusty_dagger",
                    "name": "rusty dagger",
                    "aliases": ["dagger"],
                    "location_id": "loc_tavern_road"
                },
                {
                    "item_id": "item:heavy_anvil",
                    "definition_id": "def:heavy_anvil",
                    "name": "heavy anvil",
                    "aliases": ["anvil"],
                    "location_id": "loc_tavern_road"
                }
            ],
            "scene_objects": [],
            "player_location_id": "loc_tavern_road",
            "player_inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0
            }
        },
        "turns": [
            "I pick up 5 iron arrows.",
            "I pick up 10 iron arrows.",
            "I pick up the rusty dagger.",
            "I pick up the heavy anvil."
        ]
    },
    "inventory_containers_durability_repair": {
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
            "player_inventory": {
                "items": [
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15
                    },
                    {
                        "item_id": "item:leather_satchel",
                        "definition_id": "def:leather_satchel",
                        "name": "leather satchel",
                        "aliases": ["satchel", "bag"]
                    },
                    {
                        "item_id": "item:rusty_dagger",
                        "definition_id": "def:rusty_dagger",
                        "name": "rusty dagger",
                        "aliases": ["dagger"]
                    },
                    {
                        "item_id": "item:whetstone",
                        "definition_id": "def:whetstone",
                        "name": "whetstone"
                    },
                    {
                        "item_id": "item:torn_cloak",
                        "definition_id": "def:torn_cloak",
                        "name": "torn cloak",
                        "aliases": ["cloak"]
                    },
                    {
                        "item_id": "item:cloth_scraps",
                        "definition_id": "def:cloth_scrap",
                        "name": "cloth scraps",
                        "aliases": ["cloth scrap", "scraps"],
                        "quantity": 4
                    }
                ],
                "equipment": {},
                "carry_capacity": 50.0
            }
        },
        "turns": [
            "I put 15 iron arrows into the leather satchel.",
            "I repair the rusty dagger with the whetstone.",
            "I repair the torn cloak with 2 cloth scraps."
        ]
    },
    "inventory_consumables_ammo_equipment_stats": {
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
            "player_hp": 10,
            "player_max_hp": 20,
            "player_inventory": {
                "items": [
                    {
                        "item_id": "item:minor_healing_potions",
                        "definition_id": "def:minor_healing_potion",
                        "name": "minor healing potion",
                        "aliases": ["healing potion", "potion"],
                        "quantity": 2
                    },
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
                "equipment": {},
                "carry_capacity": 50.0
            }
        },
        "turns": [
            "I drink the minor healing potion.",
            "I equip the hunting bow.",
            "I equip the iron arrows as ammo.",
            "I equip the padded armor.",
            "__manual_consume_equipped_ammo__"
        ]
    },
    "inventory_crafting_recipes_materials": {
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
            "player_inventory": {
                "items": [
                    {
                        "item_id": "item:wooden_sticks",
                        "definition_id": "def:wooden_stick",
                        "name": "wooden sticks",
                        "aliases": ["stick", "sticks"],
                        "quantity": 3
                    },
                    {
                        "item_id": "item:cloth_scraps",
                        "definition_id": "def:cloth_scrap",
                        "name": "cloth scraps",
                        "aliases": ["cloth scrap", "scraps"],
                        "quantity": 3
                    },
                    {
                        "item_id": "item:oil_flasks",
                        "definition_id": "def:oil_flask",
                        "name": "oil flasks",
                        "aliases": ["oil", "flask of oil"],
                        "quantity": 2
                    }
                ],
                "equipment": {},
                "carry_capacity": 50.0
            }
        },
        "turns": [
            "I craft a torch.",
            "I craft iron arrows.",
            "I craft a torch."
        ]
    },
    "inventory_loot_merchant_economy": {
        "currency": {"gold": 1, "silver": 0, "copper": 0},
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
            "player_location_id": "loc_tavern_market",
            "player_inventory": {
                "items": [
                    {
                        "item_id": "item:rusty_dagger",
                        "definition_id": "def:rusty_dagger",
                        "name": "rusty dagger",
                        "aliases": ["dagger"]
                    }
                ],
                "equipment": {},
                "carry_capacity": 50.0
            },
            "merchant_state": {
                "merchants": {
                    "npc:Elara": {
                        "merchant_id": "npc:Elara",
                        "name": "Elara",
                        "buy_price_multiplier": 1.0,
                        "sell_price_multiplier": 0.5,
                        "inventory": {
                            "items": [
                                {
                                    "item_id": "merchant:elara:minor_healing_potion",
                                    "definition_id": "def:minor_healing_potion",
                                    "name": "minor healing potion",
                                    "quantity": 5
                                },
                                {
                                    "item_id": "merchant:elara:oil_flask",
                                    "definition_id": "def:oil_flask",
                                    "name": "oil flask",
                                    "quantity": 3
                                }
                            ],
                            "equipment": {},
                            "carry_capacity": 9999.0
                        }
                    }
                }
            }
        },
        "turns": [
            "__manual_generate_bandit_loot__",
            "I buy a minor healing potion from Elara.",
            "I sell the rusty dagger to Elara.",
            "I buy 2 oil flasks from Elara."
        ]
    },
    "companion_inventory_auto_equip": {
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
            "player_inventory": {
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"]
                    },
                    {
                        "item_id": "item:padded_armor",
                        "definition_id": "def:padded_armor",
                        "name": "padded armor",
                        "aliases": ["armor"]
                    },
                    {
                        "item_id": "item:stolen_ring",
                        "definition_id": "def:stolen_ring",
                        "name": "stolen ring",
                        "aliases": ["ring"]
                    }
                ],
                "equipment": {},
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
                            "items": [],
                            "equipment": {},
                            "carry_capacity": 50.0
                        }
                    },
                    {
                        "npc_id": "npc:Captain_Aldric",
                        "name": "Captain Aldric",
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern_road",
                        "current_role": "Guard captain",
                        "personality": "lawful honorable protective",
                        "morality": "lawful guard justice",
                        "loyalty": 20,
                        "inventory": {
                            "items": [],
                            "equipment": {},
                            "carry_capacity": 50.0
                        }
                    }
                ]
            }
        },
        "turns": [
            "I give the hunting bow to Bran.",
            "I give the padded armor to Bran.",
            "I give the stolen ring to Captain Aldric."
        ]
    },
}