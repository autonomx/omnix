from __future__ import annotations

from typing import Any, Dict


def _queue_pack() -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "queue_bandit_pack",
        "title": "Queue Bandit Pack",
        "lore_entries": [
            {"lore_id": "lore:red_sashes", "title": "The Red Sashes", "truth_status": "rumor"}
        ],
        "story_arcs": [
            {
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": ["lore:red_sashes"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:delayed_bandit_attack",
                "arc_id": "arc:bandit_pressure",
                "kind": "consequence",
                "summary": "The delayed bandit attack lands.",
                "effects": [
                    {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "attack"},
                    {"type": "world_event_emit"},
                ],
            },
        ],
        "escalation_rules": [],
    }


STORY_EVENT_QUEUE_M25_M27_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_event_queue_enqueues_without_applying": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "definition_event_id": "event:delayed_bandit_attack",
                "enqueued_turn": 1,
                "delay_turns": 2,
                "source": "manual",
            }
        ],
        "turns": ["I inspect the delayed consequence before it fires."],
        "checks": [
            {
                "type": "story_event_queue_pending",
                "expected_count": 1,
                "expected_event_id": "event:delayed_bandit_attack",
            },
            {
                "type": "story_event_queue_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors"},
            },
            {
                "type": "story_event_queue_event_applied",
                "event_id": "event:delayed_bandit_attack",
                "expected_applied": False,
            },
        ],
    },
    "story_event_queue_waits_until_due_turn": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "definition_event_id": "event:delayed_bandit_attack",
                "enqueued_turn": 1,
                "due_turn": 4,
                "source": "manual",
            }
        ],
        "setup_story_event_queue_process": [
            {"mode": "idle", "turn_index": 3}
        ],
        "turns": ["I check that the event is still waiting."],
        "checks": [
            {
                "type": "story_event_queue_pending",
                "expected_count": 1,
                "expected_event_id": "event:delayed_bandit_attack",
            },
            {
                "type": "story_event_queue_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors"},
            },
        ],
    },
    "story_event_queue_applies_when_due": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "definition_event_id": "event:delayed_bandit_attack",
                "enqueued_turn": 1,
                "due_turn": 3,
                "source": "manual",
            }
        ],
        "setup_story_event_queue_process": [
            {"mode": "idle", "turn_index": 3}
        ],
        "turns": ["I inspect the applied delayed bandit attack."],
        "checks": [
            {
                "type": "story_event_queue_event_applied",
                "event_id": "event:delayed_bandit_attack",
                "expected_applied": True,
            },
            {
                "type": "story_event_queue_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "attack"},
            },
            {
                "type": "story_event_queue_history",
                "expected_event_id": "event:delayed_bandit_attack",
                "expected_status": "applied",
            },
        ],
    },
    "story_event_queue_does_not_process_in_combat_mode": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "definition_event_id": "event:delayed_bandit_attack",
                "enqueued_turn": 1,
                "due_turn": 1,
                "source": "manual",
            }
        ],
        "setup_story_event_queue_process": [
            {"mode": "combat", "turn_index": 2}
        ],
        "turns": ["I check that combat blocks queued story consequences."],
        "checks": [
            {
                "type": "story_event_queue_pending",
                "expected_count": 1,
                "expected_event_id": "event:delayed_bandit_attack",
            },
            {
                "type": "story_event_queue_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors"},
            },
        ],
    },
    "story_event_queue_prevents_duplicate_event_application": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "definition_event_id": "event:delayed_bandit_attack",
                "enqueued_turn": 1,
                "due_turn": 1,
                "source": "manual",
            },
            {
                "definition_event_id": "event:delayed_bandit_attack",
                "enqueued_turn": 1,
                "due_turn": 1,
                "source": "manual",
            },
        ],
        "setup_story_event_queue_process": [
            {"mode": "idle", "turn_index": 1},
            {"mode": "idle", "turn_index": 2},
        ],
        "turns": ["I check that the delayed attack only applies once."],
        "checks": [
            {
                "type": "story_event_queue_event_applied",
                "event_id": "event:delayed_bandit_attack",
                "expected_applied": True,
            },
            {
                "type": "story_event_queue_pending",
                "expected_count": 0,
            },
        ],
    },
    "story_event_queue_records_failed_event": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "event": {
                    "event_id": "event:bad_missing_arc",
                    "arc_id": "arc:missing",
                    "effects": [
                        {"type": "arc_stage_set", "arc_id": "arc:missing", "stage": "bad"}
                    ],
                },
                "enqueued_turn": 1,
                "due_turn": 1,
                "source": "manual",
            }
        ],
        "setup_story_event_queue_process": [
            {"mode": "idle", "turn_index": 1}
        ],
        "turns": ["I inspect a failed queued story event."],
        "checks": [
            {
                "type": "story_event_queue_history",
                "expected_event_id": "event:bad_missing_arc",
                "expected_status": "failed",
            }
        ],
    },
    "story_event_queue_campaign_director_processes_due_items": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "definition_event_id": "event:delayed_bandit_attack",
                "enqueued_turn": 1,
                "due_turn": 2,
                "source": "manual",
            }
        ],
        "setup_campaign_director_ticks": [
            {"mode": "idle", "turn_index": 2}
        ],
        "turns": ["I inspect a queued event processed by campaign director runtime."],
        "checks": [
            {
                "type": "story_event_queue_event_applied",
                "event_id": "event:delayed_bandit_attack",
                "expected_applied": True,
            },
            {
                "type": "story_event_queue_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "attack"},
            },
        ],
    },
    "story_event_queue_debug_is_bounded": {
        "setup_story_packs": [{"proposal": _queue_pack(), "turn_index": 1}],
        "setup_story_event_queue": [
            {
                "event": {
                    "event_id": f"event:queued_{i}",
                    "arc_id": "arc:bandit_pressure",
                    "effects": [],
                },
                "enqueued_turn": 1,
                "due_turn": i,
                "source": "manual",
            }
            for i in range(250)
        ],
        "turns": ["I inspect the bounded story event queue."],
        "checks": [
            {
                "type": "story_event_queue_pending",
                "expected_count": 200,
            }
        ],
    },
}