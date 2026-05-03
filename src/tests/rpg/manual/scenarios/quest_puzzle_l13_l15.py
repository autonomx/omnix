from __future__ import annotations

from typing import Any, Dict

QUEST_PUZZLE_L13_L15_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "quest_start_sets_active_stage": {
        "setup_quest_transitions": [
            {
                "action": "start",
                "quest_id": "quest:rat_cellar",
                "title": "Rats in the Cellar",
                "stage": "started",
                "objectives": {
                    "talk_to_bran": {"description": "Talk to Bran."}
                },
            }
        ],
        "turns": ["I ask Bran about work in the tavern."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "started",
                "expected_status": "active",
            }
        ],
    },
    "quest_objective_completion_advances_stage": {
        "setup_quest_transitions": [
            {
                "action": "start",
                "quest_id": "quest:rat_cellar",
                "stage": "started",
                "objectives": {
                    "talk_to_bran": {"description": "Talk to Bran."}
                },
            },
            {
                "action": "complete_objective",
                "quest_id": "quest:rat_cellar",
                "objective_id": "talk_to_bran",
            },
            {
                "action": "set_stage",
                "quest_id": "quest:rat_cellar",
                "stage": "investigate_cellar",
            },
        ],
        "turns": ["I agree to investigate the cellar."],
        "checks": [
            {
                "type": "quest_objective",
                "quest_id": "quest:rat_cellar",
                "objective_id": "talk_to_bran",
                "expected_status": "completed",
            },
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "investigate_cellar",
            },
        ],
    },
    "quest_stage_gate_requires_item": {
        "setup_manual_inventory_items": ["cellar_key"],
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:rat_cellar", "stage": "started"},
            {
                "action": "set_stage",
                "quest_id": "quest:rat_cellar",
                "stage": "cellar_unlocked",
                "conditions": [{"type": "has_item", "item_id": "cellar_key"}],
            },
        ],
        "turns": ["I use the cellar key on the locked trapdoor."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "cellar_unlocked",
            }
        ],
    },
    "quest_stage_gate_requires_social_trust": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": 45}},
        },
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:bran_secret", "stage": "rumor"},
            {
                "action": "set_stage",
                "quest_id": "quest:bran_secret",
                "stage": "trusted_disclosure",
                "conditions": [
                    {"type": "social_trust_at_least", "npc_id": "bran", "minimum": 40}
                ],
            },
        ],
        "turns": ["I ask Bran to trust me with the truth."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:bran_secret",
                "expected_stage": "trusted_disclosure",
            }
        ],
    },
    "quest_stage_gate_requires_npc_memory": {
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
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:bandit_warning", "stage": "unverified"},
            {
                "action": "set_stage",
                "quest_id": "quest:bandit_warning",
                "stage": "bran_knows",
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
        "turns": ["I remind Bran that I warned him about the bandits."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:bandit_warning",
                "expected_stage": "bran_knows",
            }
        ],
    },
    "quest_stage_gate_requires_spatial_area": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:rat_cellar", "stage": "started"},
            {
                "action": "set_stage",
                "quest_id": "quest:rat_cellar",
                "stage": "at_tavern",
                "conditions": [
                    {
                        "type": "entity_in_area",
                        "entity_id": "player",
                        "area_id": "tavern_common_room",
                    }
                ],
            },
        ],
        "turns": ["I stand in the tavern common room."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "at_tavern",
            }
        ],
    },
    "quest_completion_produces_reward_payload_once": {
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:rat_cellar", "stage": "return_to_bran"},
            {
                "action": "complete_quest",
                "quest_id": "quest:rat_cellar",
                "rewards": [{"type": "gold", "amount": 10}],
            },
            {
                "action": "complete_quest",
                "quest_id": "quest:rat_cellar",
                "rewards": [{"type": "gold", "amount": 10}],
            },
        ],
        "turns": ["I report the cellar is clear and ask about the reward."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "completed",
                "expected_status": "completed",
            },
            {
                "type": "quest_reward_payload",
                "quest_id": "quest:rat_cellar",
                "expected_count": 1,
                "expected_auto_granted": False,
            },
        ],
    },
    "quest_reward_not_auto_granted_without_apply": {
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:rat_cellar", "stage": "return_to_bran"},
            {
                "action": "complete_quest",
                "quest_id": "quest:rat_cellar",
                "rewards": [{"type": "gold", "amount": 10}],
            },
        ],
        "turns": ["I ask whether the reward was directly granted."],
        "checks": [
            {
                "type": "quest_reward_payload",
                "quest_id": "quest:rat_cellar",
                "expected_count": 1,
                "expected_auto_granted": False,
            }
        ],
    },
    "quest_save_load_preserves_stage_and_objectives": {
        "setup_quest_transitions": [
            {
                "action": "start",
                "quest_id": "quest:rat_cellar",
                "stage": "started",
                "objectives": {"talk_to_bran": {"description": "Talk to Bran."}},
            },
            {
                "action": "complete_objective",
                "quest_id": "quest:rat_cellar",
                "objective_id": "talk_to_bran",
            },
        ],
        "turns": ["I check my quest journal."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "started",
                "expected_status": "active",
            },
            {
                "type": "quest_objective",
                "quest_id": "quest:rat_cellar",
                "objective_id": "talk_to_bran",
                "expected_status": "completed",
            },
        ],
    },
    "puzzle_start_sets_initial_state": {
        "setup_puzzle_transitions": [
            {
                "action": "start",
                "puzzle_id": "puzzle:cellar_runes",
                "title": "Cellar Runes",
                "state": "initial",
            }
        ],
        "turns": ["I inspect the cellar rune puzzle."],
        "checks": [
            {
                "type": "puzzle_state",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_state": "initial",
                "expected_status": "active",
            }
        ],
    },
    "puzzle_wrong_input_does_not_advance": {
        "setup_puzzle_transitions": [
            {"action": "start", "puzzle_id": "puzzle:cellar_runes", "state": "initial"},
            {
                "action": "input",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_input": "moon",
                "input": "sun",
                "next_state": "rune_unlocked",
            },
        ],
        "turns": ["I press the sun rune."],
        "checks": [
            {
                "type": "puzzle_state",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_state": "initial",
                "expected_status": "active",
            }
        ],
    },
    "puzzle_correct_input_advances_state": {
        "setup_puzzle_transitions": [
            {"action": "start", "puzzle_id": "puzzle:cellar_runes", "state": "initial"},
            {
                "action": "input",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_input": "moon",
                "input": "moon",
                "next_state": "rune_unlocked",
                "set_flags": {"rune_unlocked": True},
            },
        ],
        "turns": ["I press the moon rune."],
        "checks": [
            {
                "type": "puzzle_state",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_state": "rune_unlocked",
            },
            {
                "type": "puzzle_flag",
                "puzzle_id": "puzzle:cellar_runes",
                "flag": "rune_unlocked",
                "expected": True,
            },
        ],
    },
    "puzzle_requires_prior_flag": {
        "setup_puzzle_transitions": [
            {"action": "start", "puzzle_id": "puzzle:cellar_runes", "state": "initial"},
            {
                "action": "solve",
                "puzzle_id": "puzzle:cellar_runes",
                "conditions": [
                    {
                        "type": "puzzle_flag",
                        "puzzle_id": "puzzle:cellar_runes",
                        "flag": "rune_unlocked",
                        "expected": True,
                    }
                ],
            },
        ],
        "turns": ["I try to solve the rune puzzle without lighting the rune."],
        "checks": [
            {
                "type": "puzzle_state",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_state": "initial",
                "expected_status": "active",
            }
        ],
    },
    "puzzle_completion_unlocks_quest_gate": {
        "setup_puzzle_transitions": [
            {"action": "start", "puzzle_id": "puzzle:cellar_runes", "state": "initial"},
            {
                "action": "input",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_input": "moon",
                "input": "moon",
                "next_state": "rune_unlocked",
                "set_flags": {"rune_unlocked": True},
            },
        ],
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:rat_cellar", "stage": "blocked_by_runes"},
            {
                "action": "set_stage",
                "quest_id": "quest:rat_cellar",
                "stage": "runes_unlocked",
                "conditions": [
                    {
                        "type": "puzzle_flag",
                        "puzzle_id": "puzzle:cellar_runes",
                        "flag": "rune_unlocked",
                        "expected": True,
                    }
                ],
            },
        ],
        "turns": ["I use the solved rune puzzle to unlock the quest path."],
        "checks": [
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "runes_unlocked",
            }
        ],
    },
    "puzzle_save_load_preserves_flags": {
        "setup_puzzle_transitions": [
            {"action": "start", "puzzle_id": "puzzle:cellar_runes", "state": "initial"},
            {
                "action": "input",
                "puzzle_id": "puzzle:cellar_runes",
                "expected_input": "moon",
                "input": "moon",
                "next_state": "rune_unlocked",
                "set_flags": {"rune_unlocked": True},
            },
        ],
        "turns": ["I check the rune puzzle state after saving."],
        "checks": [
            {
                "type": "puzzle_flag",
                "puzzle_id": "puzzle:cellar_runes",
                "flag": "rune_unlocked",
                "expected": True,
            }
        ],
    },
}