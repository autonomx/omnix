from __future__ import annotations

from typing import Any, Dict


STORY_M1_M3_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "lore_entry_can_be_revealed_to_player": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "kind": "faction",
                "truth_status": "true",
                "known_by": ["bran"],
                "tags": ["bandits", "local-threat"],
                "summary": "A road gang known for red cloth tied around their arms.",
            },
            {"action": "reveal_to_player", "lore_id": "lore:red_sashes"},
        ],
        "turns": ["I ask Bran about the Red Sashes."],
        "checks": [
            {
                "type": "lore_entry",
                "lore_id": "lore:red_sashes",
                "expected": {
                    "revealed_to_player": True,
                    "truth_status": "true",
                },
            }
        ],
    },
    "lore_secret_not_available_until_revealed": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:bran_hidden_debt",
                "title": "Bran's Hidden Debt",
                "kind": "secret",
                "truth_status": "secret",
                "known_by": ["bran"],
                "tags": ["secret", "debt"],
            }
        ],
        "turns": ["I ask about Bran's hidden debt."],
        "checks": [
            {
                "type": "lore_condition",
                "condition": {
                    "type": "lore_revealed_to_player",
                    "lore_id": "lore:bran_hidden_debt",
                },
                "expected_ok": False,
            }
        ],
    },
    "lore_npc_knows_role_based_lore": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:tavern_cellar",
                "title": "The Tavern Cellar",
                "kind": "place",
                "truth_status": "true",
                "known_by": ["bran"],
                "tags": ["tavern", "cellar"],
            }
        ],
        "turns": ["I ask Bran about the cellar."],
        "checks": [
            {
                "type": "lore_condition",
                "condition": {
                    "type": "lore_known_by",
                    "lore_id": "lore:tavern_cellar",
                    "entity_id": "bran",
                },
                "expected_ok": True,
            }
        ],
    },
    "lore_rumor_not_promoted_to_truth": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:dragon_owns_tavern",
                "title": "Dragon Owns the Tavern",
                "kind": "rumor",
                "truth_status": "rumor",
                "tags": ["rumor", "dragon"],
            },
            {"action": "reveal_to_player", "lore_id": "lore:dragon_owns_tavern"},
        ],
        "turns": ["I ask whether a dragon owns the tavern."],
        "checks": [
            {
                "type": "lore_entry",
                "lore_id": "lore:dragon_owns_tavern",
                "expected": {
                    "truth_status": "rumor",
                    "revealed_to_player": True,
                },
            }
        ],
    },
    "story_arc_start_sets_active_stage": {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "stage": "rumors",
                "pressure": 20,
                "links": {
                    "entity": ["bran", "mira"],
                    "location": ["tavern_common_room", "street"],
                },
            }
        ],
        "turns": ["I listen for rumors about bandits."],
        "checks": [
            {
                "type": "story_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {
                    "status": "active",
                    "stage": "rumors",
                    "pressure": 20,
                },
            }
        ],
    },
    "story_arc_pressure_increases_from_event": {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "stage": "rumors",
                "pressure": 20,
            },
            {
                "action": "pressure_delta",
                "arc_id": "arc:bandit_pressure",
                "delta": 25,
            },
        ],
        "turns": ["I ignore the growing bandit rumors."],
        "checks": [
            {
                "type": "story_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"pressure": 45},
            }
        ],
    },
    "story_arc_stage_advances_when_pressure_threshold_met": {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "stage": "rumors",
                "pressure": 60,
            },
            {
                "action": "set_stage",
                "arc_id": "arc:bandit_pressure",
                "stage": "threat",
                "conditions": [
                    {
                        "type": "arc_pressure_at_least",
                        "arc_id": "arc:bandit_pressure",
                        "minimum": 50,
                    }
                ],
            },
        ],
        "turns": ["The bandit rumors become threats."],
        "checks": [
            {
                "type": "story_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "threat"},
            }
        ],
    },
    "story_arc_links_to_quest_state": {
        "setup_quest_transitions": [
            {
                "action": "start",
                "quest_id": "quest:stop_red_sashes",
                "stage": "investigate",
            }
        ],
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "stage": "rumors",
                "links": {"quest": ["quest:stop_red_sashes"]},
            },
            {
                "action": "set_flag",
                "arc_id": "arc:bandit_pressure",
                "flag": "quest_linked",
                "value": True,
                "conditions": [
                    {
                        "type": "quest_stage",
                        "quest_id": "quest:stop_red_sashes",
                        "stage": "investigate",
                    }
                ],
            },
        ],
        "turns": ["I check whether the bandit arc is linked to the quest."],
        "checks": [
            {
                "type": "story_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"flags": {"quest_linked": True}},
            }
        ],
    },
    "story_arc_links_to_lore_reveal": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "true",
            }
        ],
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "stage": "rumors",
                "links": {"lore": ["lore:red_sashes"]},
            },
            {
                "action": "reveal_lore",
                "arc_id": "arc:bandit_pressure",
                "lore_id": "lore:red_sashes",
            },
        ],
        "turns": ["The bandit arc reveals the Red Sashes lore."],
        "checks": [
            {
                "type": "lore_condition",
                "condition": {
                    "type": "lore_revealed_to_player",
                    "lore_id": "lore:red_sashes",
                },
                "expected_ok": True,
            }
        ],
    },
    "story_arc_condition_requires_npc_memory": {
        "setup_told_memories": [
            {
                "subject_id": "bran",
                "speaker_id": "player",
                "event_id": "evt:bandits",
                "summary": "The player told Bran about bandits.",
                "facts": {"actor_id": "bandits"},
                "tags": ["bandit"],
                "verified": True,
            }
        ],
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "stage": "rumors",
            },
            {
                "action": "set_flag",
                "arc_id": "arc:bandit_pressure",
                "flag": "bran_warned",
                "value": True,
                "conditions": [
                    {
                        "type": "npc_knows_memory",
                        "npc_id": "bran",
                        "event_id": "evt:bandits",
                        "tags": ["bandit"],
                    }
                ],
            },
        ],
        "turns": ["I check whether Bran remembers my warning."],
        "checks": [
            {
                "type": "story_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"flags": {"bran_warned": True}},
            }
        ],
    },
    "story_arc_save_load_preserves_pressure_and_stage": {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "stage": "rumors",
                "pressure": 20,
            },
            {
                "action": "pressure_delta",
                "arc_id": "arc:bandit_pressure",
                "delta": 30,
            },
            {
                "action": "set_stage",
                "arc_id": "arc:bandit_pressure",
                "stage": "threat",
                "conditions": [
                    {
                        "type": "arc_pressure_at_least",
                        "arc_id": "arc:bandit_pressure",
                        "minimum": 50,
                    }
                ],
            },
        ],
        "turns": ["I check the current bandit arc state."],
        "checks": [
            {
                "type": "story_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {
                    "stage": "threat",
                    "pressure": 50,
                },
            }
        ],
    },
    "story_arc_debug_payload_is_bounded": {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "stage": "rumors",
                "pressure": 20,
                "links": {
                    "lore": ["lore:red_sashes"],
                    "entity": ["bran", "mira", "bandit"],
                    "location": ["tavern_common_room", "street"],
                    "quest": ["quest:stop_red_sashes"],
                    "puzzle": ["puzzle:cellar_runes"],
                },
            }
        ],
        "turns": ["I inspect the story arc debug payload."],
        "checks": [
            {
                "type": "story_arc_debug_bounded",
                "arc_id": "arc:bandit_pressure",
                "max_link_count": 20,
            }
        ],
    },
}