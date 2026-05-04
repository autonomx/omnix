from __future__ import annotations

from typing import Any, Dict


def _arc_setup() -> Dict[str, Any]:
    return {
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:witness_quest",
                "title": "Witness Quest",
                "stage": "investigation",
                "pressure": 30,
            }
        ],
        "setup_story_arc_milestones": [
            {
                "arc_id": "arc:witness_quest",
                "milestone_id": "milestone:find_witness",
                "title": "Find the witness",
                "objective_text": "Locate the witness at the tavern.",
                "quest_id": "quest:witness_hunt",
                "priority": 80,
            },
            {
                "arc_id": "arc:witness_quest",
                "milestone_id": "milestone:gather_evidence",
                "title": "Gather evidence",
                "objective_text": "Collect evidence from the crime scene.",
                "quest_id": "quest:witness_hunt",
                "priority": 60,
            },
        ],
    }


STORY_QUEST_LOG_M49_M51_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "quest_log_payload_lists_active_objectives": {
        **_arc_setup(),
        "turns": ["I check my quest log for active objectives."],
        "checks": [
            {
                "type": "quest_log_payload",
                "limit": 50,
                "expected_active_objective_id": "milestone:find_witness",
                "expected_active_count": 2,
                "expected_ok": True,
            },
        ],
    },
    "quest_log_pin_moves_objective_to_tracker_top": {
        **_arc_setup(),
        "turns": ["I pin the witness objective to track it closely."],
        "checks": [
            {
                "type": "quest_log_pin",
                "objective_id": "milestone:gather_evidence",
                "turn_index": 1,
                "reason": "test_pin",
                "expected_ok": True,
                "expected_reason": "pinned",
            },
            {
                "type": "objective_tracker_payload",
                "limit": 8,
                "expected_objective_id": "milestone:gather_evidence",
                "expected_first_objective_id": "milestone:gather_evidence",
            },
        ],
    },
    "quest_log_unpin_removes_pin": {
        **_arc_setup(),
        "setup_quest_log_actions": [
            {
                "action": "pin",
                "objective_id": "milestone:find_witness",
                "turn_index": 1,
                "reason": "test_setup_pin",
            }
        ],
        "turns": ["I unpin the witness objective since I found them."],
        "checks": [
            {
                "type": "quest_log_unpin",
                "objective_id": "milestone:find_witness",
                "turn_index": 2,
                "reason": "test_unpin",
                "expected_ok": True,
                "expected_reason": "unpinned",
            },
            {
                "type": "objective_tracker_payload",
                "limit": 8,
                "expected_first_objective_id": "milestone:find_witness",
            },
        ],
    },
    "quest_log_completed_objective_moves_to_completed_section": {
        **_arc_setup(),
        "setup_complete_story_arc_milestones": [
            {
                "milestone_id": "milestone:find_witness",
                "turn_index": 1,
                "reason": "test_completion",
            }
        ],
        "turns": ["I complete the witness objective and check my quest log."],
        "checks": [
            {
                "type": "quest_log_payload",
                "limit": 50,
                "expected_active_objective_id": "milestone:gather_evidence",
                "expected_completed_objective_id": "milestone:find_witness",
                "expected_active_count": 1,
            },
        ],
    },
    "quest_log_pin_missing_or_completed_rejected": {
        **_arc_setup(),
        "setup_complete_story_arc_milestones": [
            {
                "milestone_id": "milestone:find_witness",
                "turn_index": 1,
                "reason": "test_completion",
            }
        ],
        "turns": ["I try to pin a completed objective and a non-existent one."],
        "checks": [
            {
                "type": "quest_log_pin",
                "objective_id": "milestone:find_witness",
                "expected_ok": False,
                "expected_reason": "objective_not_active",
            },
            {
                "type": "quest_log_pin",
                "objective_id": "milestone:nonexistent",
                "expected_ok": False,
                "expected_reason": "objective_not_active",
            },
        ],
    },
    "campaign_recap_includes_objective_tracker": {
        **_arc_setup(),
        "setup_quest_log_actions": [
            {
                "action": "pin",
                "objective_id": "milestone:find_witness",
                "turn_index": 1,
                "reason": "test_pin",
            }
        ],
        "turns": ["I check my campaign status including objectives."],
        "checks": [
            {
                "type": "campaign_recap_objective_tracker",
                "turn_index": 2,
                "max_items": 25,
                "expected_objective_id": "milestone:find_witness",
            },
        ],
    },
    "objective_tracker_output_is_bounded": {
        **_arc_setup(),
        "setup_story_arc_milestones": [
            {
                "arc_id": "arc:witness_quest",
                "milestone_id": "milestone:find_witness",
                "title": "Find the witness",
                "objective_text": "Locate the witness at the tavern.",
                "quest_id": "quest:witness_hunt",
                "priority": 80,
            },
            {
                "arc_id": "arc:witness_quest",
                "milestone_id": "milestone:gather_evidence",
                "title": "Gather evidence",
                "objective_text": "Collect evidence from the crime scene.",
                "quest_id": "quest:witness_hunt",
                "priority": 60,
            },
            {
                "arc_id": "arc:side_quest",
                "milestone_id": "milestone:side_a",
                "title": "Side objective A",
                "objective_text": "Do side task A.",
                "quest_id": "quest:side",
                "priority": 40,
            },
            {
                "arc_id": "arc:side_quest",
                "milestone_id": "milestone:side_b",
                "title": "Side objective B",
                "objective_text": "Do side task B.",
                "quest_id": "quest:side",
                "priority": 30,
            },
            {
                "arc_id": "arc:side_quest",
                "milestone_id": "milestone:side_c",
                "title": "Side objective C",
                "objective_text": "Do side task C.",
                "quest_id": "quest:side",
                "priority": 20,
            },
        ],
        "turns": ["I check the objective tracker with many objectives."],
        "checks": [
            {
                "type": "quest_log_debug_bounded",
                "limit": 50,
                "tracker_limit": 8,
            },
        ],
    },
    "quest_log_payload_empty_when_no_objectives": {
        "turns": ["I check my quest log when there are no active objectives."],
        "checks": [
            {
                "type": "quest_log_payload",
                "limit": 50,
                "expected_active_count": 0,
            },
            {
                "type": "objective_tracker_payload",
                "limit": 8,
            },
        ],
    },
}