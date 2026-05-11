from __future__ import annotations

from typing import Any, Dict

NARRATION_N1_N3_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "narration_repetition_memory_tracks_recent_output": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern",
            "player_hp": 20,
            "player_max_hp": 20,
            "runtime_state": {
                "narration_quality": {
                    "recent_openings": [],
                    "recent_fingerprints": [],
                    "recent_generic_phrases": [],
                }
            },
        },
        "turns": [
            "I look around the tavern.",
            "I look at the tables.",
        ],
    },
    "npc_bran_refuses_unpaid_room": {
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
            "relationships": {
                "npc:bran": {"trust": 0, "relationship": 0, "score": 0},
                "Bran": {"trust": 0, "relationship": 0, "score": 0},
            },
            "relationship_state": {
                "npc:bran": {"trust": 0, "relationship": 0, "score": 0},
                "Bran": {"trust": 0, "relationship": 0, "score": 0},
            },
            "social_state": {
                "relationships": {
                    "npc:bran": {"trust": 0, "relationship": 0, "score": 0},
                    "Bran": {"trust": 0, "relationship": 0, "score": 0},
                }
            },
            "service_state": {"paid_services": []},
            "npc_memories": [],
        },
        "turns": ["I ask Bran for a free room."],
    },
    "npc_bran_negotiates_high_trust_room": {
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
            "relationships": {
                "npc:bran": {"trust": 60, "relationship": 60, "score": 60},
                "Bran": {"trust": 60, "relationship": 60, "score": 60},
            },
            "relationship_state": {
                "npc:bran": {"trust": 60, "relationship": 60, "score": 60},
                "Bran": {"trust": 60, "relationship": 60, "score": 60},
            },
            "social_state": {
                "relationships": {
                    "npc:bran": {"trust": 60, "relationship": 60, "score": 60},
                    "Bran": {"trust": 60, "relationship": 60, "score": 60},
                }
            },
            "service_state": {"paid_services": []},
            "npc_memories": [],
        },
        "turns": ["I ask Bran for a free room."],
    },
    "npc_bran_escalates_when_threatened": {
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
            "relationships": {
                "npc:bran": {"trust": 0, "relationship": 0, "score": 0},
                "Bran": {"trust": 0, "relationship": 0, "score": 0},
            },
            "relationship_state": {
                "npc:bran": {"trust": 0, "relationship": 0, "score": 0},
                "Bran": {"trust": 0, "relationship": 0, "score": 0},
            },
            "social_state": {
                "relationships": {
                    "npc:bran": {"trust": 0, "relationship": 0, "score": 0},
                    "Bran": {"trust": 0, "relationship": 0, "score": 0},
                }
            },
            "service_state": {"paid_services": []},
            "npc_memories": [],
        },
        "turns": ["I threaten Bran for a room."],
    },
    "narration_validator_catches_hit_miss_contradiction": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_tavern_road",
            "player_hp": 20,
            "player_max_hp": 20,
            "player_inventory": {"items": [], "equipment": {}, "carry_capacity": 50.0},
            "party_state": {"max_size": 4, "companions": []},
            "combat_state": {
                "active": True,
                "current_actor_id": "player",
                "force_next_attack_roll": 20,
                "force_next_damage": 1,
                "initiative_order": [
                    {"actor_id": "player", "initiative": 20},
                    {"actor_id": "enemy:bandit_1", "initiative": 1},
                ],
                "participants": {
                    "player": {
                        "actor_id": "player",
                        "side": "party",
                        "name": "You",
                        "hp": 20,
                        "max_hp": 20,
                        "damage_min": 1,
                        "status": "active",
                    },
                    "enemy:bandit_1": {
                        "actor_id": "enemy:bandit_1",
                        "side": "enemy",
                        "name": "Bandit",
                        "hp": 8,
                        "max_hp": 8,
                        "status": "active",
                    },
                },
            },
        },
        "turns": ["I attack the bandit."],
    },
    "npc_bran_refuses_fake_debt": {
        "description": "Bran should refuse an unsupported claim that he owes the player 50 gold.",
        "turns": [
            {
                "player_input": "Bran, you owe me 50 gold. Pay me now.",
                "expect": {
                    "must_not_grant_currency": True,
                    "must_not_grant_reward": True,
                    "grounding_expected": True,
                    "allowed_grounding_candidates": ["primary", "safe_fallback"],
                    "forbidden_grounding_fallback_sources": ["deterministic_fallback"],
                    "must_refuse_or_defer_claim": True,
                },
            }
        ],
    },
}