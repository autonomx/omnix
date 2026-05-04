from __future__ import annotations

from typing import Any, Dict


def _objective_setup() -> Dict[str, Any]:
    return {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:witness_search",
                "title": "Witness Search",
                "stage": "rumors",
                "pressure": 20,
            }
        ],
        "setup_story_arc_milestones": [
            {
                "arc_id": "arc:witness_search",
                "milestone_id": "milestone:find_witness",
                "title": "Find the witness",
                "objective_text": "Find the witness near the tavern.",
                "quest_id": "quest:witness_search",
                "priority": 80,
            },
            {
                "arc_id": "arc:witness_search",
                "milestone_id": "milestone:inspect_road",
                "title": "Inspect the road",
                "objective_text": "Inspect the road outside town.",
                "quest_id": "quest:witness_search",
                "priority": 40,
            },
        ],
    }


PLAYER_ACTION_CONTEXT_M52_M54_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "player_action_context_includes_active_objectives": {
        **_objective_setup(),
        "turns": ["I inspect my player action context."],
        "checks": [
            {
                "type": "player_action_context_payload",
                "expected_objective_id": "milestone:find_witness",
                "expected_action_category": "objective",
            }
        ],
    },
    "suggested_actions_prioritize_pinned_objective": {
        **_objective_setup(),
        "setup_quest_log_actions": [
            {"action": "pin", "objective_id": "milestone:inspect_road", "turn_index": 2}
        ],
        "turns": ["I inspect suggested actions after pinning an objective."],
        "checks": [
            {
                "type": "suggested_actions",
                "expected_first_objective_id": "milestone:inspect_road",
            },
            {
                "type": "player_action_context_payload",
                "expected_objective_id": "milestone:inspect_road",
                "expected_action_category": "objective",
            },
        ],
    },
    "player_action_context_includes_nearby_npc_social_actions": {
        "setup_scene": {
            "location": "The Rusty Flagon",
            "nearby_npcs": [
                {"npc_id": "npc:bran", "name": "Bran", "role": "innkeeper"}
            ],
        },
        "turns": ["I inspect social suggested actions."],
        "checks": [
            {
                "type": "player_action_context_payload",
                "expected_action_category": "social",
            },
            {
                "type": "suggested_actions",
                "expected_category": "social",
            },
        ],
    },
    "player_action_context_combat_mode_suggests_combat_actions": {
        "setup_combat_state": {"active": True},
        "turns": ["I inspect combat suggested actions."],
        "checks": [
            {
                "type": "player_action_context_payload",
                "expected_mode": "combat",
                "expected_action_category": "combat",
            }
        ],
    },
    "player_action_context_empty_state_has_exploration_fallbacks": {
        "turns": ["I inspect fallback suggested actions."],
        "checks": [
            {
                "type": "player_action_context_payload",
                "expected_mode": "exploration",
                "expected_action_category": "exploration",
            },
            {
                "type": "suggested_actions",
                "expected_category": "exploration",
            },
        ],
    },
    "player_action_context_excludes_unrevealed_secret_lore": {
        **_objective_setup(),
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:secret_debt",
                "title": "Secret Debt",
                "truth_status": "secret",
                "revealed_to_player": False,
                "summary": "Bran secretly owes the Red Sashes.",
            }
        ],
        "turns": ["I inspect action context for leaked secret lore."],
        "checks": [
            {
                "type": "player_action_context_payload",
                "expected_objective_id": "milestone:find_witness",
                "must_not_contain": "Bran secretly owes the Red Sashes",
            }
        ],
    },
    "player_action_context_output_is_bounded": {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bounded_actions",
                "title": "Bounded Actions",
                "stage": "start",
            }
        ],
        "setup_story_arc_milestones": [
            {
                "arc_id": "arc:bounded_actions",
                "milestone_id": f"milestone:{i}",
                "title": f"Objective {i}",
                "priority": i,
            }
            for i in range(50)
        ],
        "turns": ["I inspect bounded action context."],
        "checks": [
            {
                "type": "player_action_context_bounded",
                "limit": 12,
            }
        ],
    },
    "player_action_context_contains_player_agent_schema": {
        "turns": ["I inspect player agent schema."],
        "checks": [
            {
                "type": "player_action_context_payload",
                "expected_mode": "exploration",
                "expected_action_category": "exploration",
            }
        ],
    },
}