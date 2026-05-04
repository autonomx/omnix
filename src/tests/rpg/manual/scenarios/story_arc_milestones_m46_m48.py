from __future__ import annotations

from typing import Any, Dict


def _arc_setup() -> Dict[str, Any]:
    return {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:witness_search",
                "title": "Witness Search",
                "stage": "rumors",
                "pressure": 20,
            }
        ]
    }


STORY_ARC_MILESTONES_M46_M48_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_arc_milestone_adds_active_objective": {
        **_arc_setup(),
        "turns": ["I inspect the new story arc objective."],
        "checks": [
            {
                "type": "story_arc_milestone_add",
                "arc_id": "arc:witness_search",
                "milestone_id": "milestone:find_witness",
                "title": "Find the witness",
                "objective_text": "Find the witness near the tavern.",
                "turn_index": 1,
                "expected_ok": True,
            },
            {
                "type": "story_arc_milestone_status",
                "milestone_id": "milestone:find_witness",
                "expected_status": "active",
            },
            {
                "type": "story_objective_projection",
                "expected_objective_id": "milestone:find_witness",
            },
        ],
    },
    "story_arc_milestone_completion_is_idempotent": {
        **_arc_setup(),
        "setup_story_arc_milestones": [
            {
                "arc_id": "arc:witness_search",
                "milestone_id": "milestone:find_witness",
                "title": "Find the witness",
            }
        ],
        "turns": ["I complete the same story milestone twice."],
        "checks": [
            {
                "type": "story_arc_milestone_complete",
                "milestone_id": "milestone:find_witness",
                "turn_index": 2,
                "expected_ok": True,
                "expected_reason": "completed",
            },
            {
                "type": "story_arc_milestone_complete",
                "milestone_id": "milestone:find_witness",
                "turn_index": 3,
                "expected_ok": True,
                "expected_reason": "already_completed",
            },
            {
                "type": "story_arc_milestone_status",
                "milestone_id": "milestone:find_witness",
                "expected_status": "completed",
            },
        ],
    },
    "story_event_adds_milestone_objective": {
        **_arc_setup(),
        "turns": ["I let a story event add a milestone objective."],
        "checks": [
            {
                "type": "story_event_apply_for_milestone",
                "turn_index": 2,
                "expected_ok": True,
                "event": {
                    "event_id": "event:witness_hint",
                    "arc_id": "arc:witness_search",
                    "summary": "A witness clue emerges.",
                    "effects": [
                        {
                            "type": "milestone_add",
                            "arc_id": "arc:witness_search",
                            "milestone_id": "milestone:find_witness",
                            "title": "Find the witness",
                            "objective_text": "Find the witness near the tavern.",
                        }
                    ],
                },
            },
            {
                "type": "story_objective_projection",
                "expected_objective_id": "milestone:find_witness",
            },
        ],
    },
    "story_event_completes_milestone_and_records_journal": {
        **_arc_setup(),
        "setup_story_arc_milestones": [
            {
                "arc_id": "arc:witness_search",
                "milestone_id": "milestone:find_witness",
                "title": "Find the witness",
                "journal_on_complete": "The witness was found near the tavern.",
            }
        ],
        "turns": ["I let a story event complete a milestone objective."],
        "checks": [
            {
                "type": "story_event_apply_for_milestone",
                "turn_index": 3,
                "expected_ok": True,
                "event": {
                    "event_id": "event:witness_found",
                    "arc_id": "arc:witness_search",
                    "summary": "The witness was found.",
                    "effects": [
                        {
                            "type": "milestone_complete",
                            "milestone_id": "milestone:find_witness",
                        }
                    ],
                },
            },
            {
                "type": "story_arc_milestone_status",
                "milestone_id": "milestone:find_witness",
                "expected_status": "completed",
            },
            {
                "type": "campaign_journal_objective_contains",
                "expected_summary_contains": "witness was found",
            },
        ],
    },
    "campaign_recap_includes_active_story_objectives": {
        **_arc_setup(),
        "setup_story_arc_milestones": [
            {
                "arc_id": "arc:witness_search",
                "milestone_id": "milestone:find_witness",
                "title": "Find the witness",
                "objective_text": "Find the witness near the tavern.",
            }
        ],
        "turns": ["I inspect the campaign recap for active objectives."],
        "checks": [
            {
                "type": "campaign_recap_objective",
                "expected_objective_id": "milestone:find_witness",
            }
        ],
    },
    "story_arc_milestone_missing_arc_rejected": {
        "turns": ["I try to add a milestone to a missing arc."],
        "checks": [
            {
                "type": "story_arc_milestone_add",
                "arc_id": "arc:missing",
                "milestone_id": "milestone:missing",
                "title": "Impossible objective",
                "expected_ok": False,
            }
        ],
    },
    "story_arc_milestone_missing_complete_rejected": {
        **_arc_setup(),
        "turns": ["I try to complete a missing milestone."],
        "checks": [
            {
                "type": "story_arc_milestone_complete",
                "milestone_id": "milestone:missing",
                "expected_ok": False,
                "expected_reason": "milestone_missing",
            }
        ],
    },
    "story_arc_milestone_state_is_bounded": {
        **_arc_setup(),
        "turns": ["I inspect bounded milestone state."],
        "checks": [
            *[
                {
                    "type": "story_arc_milestone_add",
                    "arc_id": "arc:witness_search",
                    "milestone_id": f"milestone:{i}",
                    "title": f"Milestone {i}",
                    "expected_ok": i < 30,
                }
                for i in range(40)
            ],
            {
                "type": "story_arc_milestone_bounded",
                "arc_id": "arc:witness_search",
                "expected_max": 30,
            },
        ],
    },
}