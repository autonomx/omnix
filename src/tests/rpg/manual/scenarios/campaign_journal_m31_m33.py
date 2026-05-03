from __future__ import annotations

from typing import Any, Dict


def _story_setup() -> Dict[str, Any]:
    return {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
                "summary": "A gang may be active near the road.",
            },
            {
                "action": "upsert",
                "lore_id": "lore:bran_debt",
                "title": "Bran's Debt",
                "truth_status": "secret",
                "revealed_to_player": False,
                "summary": "Bran owes money to dangerous people.",
            },
        ],
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "stage": "rumors",
                "pressure": 60,
                "links": {"lore": ["lore:red_sashes"], "entities": ["bran"]},
            }
        ],
        "setup_story_event_queue": [
            {
                "event": {
                    "event_id": "event:delayed_bandit_attack",
                    "arc_id": "arc:bandit_pressure",
                    "effects": [],
                },
                "enqueued_turn": 1,
                "due_turn": 5,
                "source": "manual",
            }
        ],
        "setup_npc_evolution_transitions": [
            {
                "action": "start_arc",
                "npc_id": "bran",
                "arc_id": "npc_arc:bran_revenge",
                "motivation": "revenge_against_red_sashes",
                "profession": "former_innkeeper",
            },
            {
                "action": "evolve",
                "npc_id": "bran",
                "companion_eligible": True,
            },
        ],
    }


CAMPAIGN_JOURNAL_M31_M33_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "campaign_journal_records_story_event_entry": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 50}
        ],
        "setup_story_events": [
            {
                "event_id": "event:bandit_warning",
                "arc_id": "arc:bandit_pressure",
                "kind": "warning",
                "summary": "A bandit warning reached the tavern.",
                "effects": [
                    {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "warning"}
                ],
            }
        ],
        "turns": ["I inspect the campaign journal after the warning."],
        "checks": [
            {
                "type": "campaign_journal_contains",
                "expected_kind": "story_event",
                "expected_summary_contains": "bandit warning",
            }
        ],
    },
    "campaign_journal_separates_rumor_and_secret_lore": {
        **_story_setup(),
        "turns": ["I inspect what lore is visible to the player."],
        "checks": [
            {
                "type": "campaign_journal_lore",
                "lore_id": "lore:red_sashes",
                "expected_present": True,
                "expected_truth_status": "rumor",
            },
            {
                "type": "campaign_journal_lore",
                "lore_id": "lore:bran_debt",
                "expected_present": False,
            },
        ],
    },
    "campaign_story_recap_lists_active_arcs_and_pending_consequences": {
        **_story_setup(),
        "turns": ["I inspect the story recap."],
        "checks": [
            {
                "type": "campaign_story_recap",
                "turn_index": 2,
                "expected_arc_id": "arc:bandit_pressure",
                "expected_pending_event_id": "event:delayed_bandit_attack",
                "expected_npc_id": "bran",
            }
        ],
    },
    "campaign_story_recap_lists_party_member_after_companion_accept": {
        **_story_setup(),
        "setup_social_state": {"relationships": {"bran": {"trust": 80, "hostility": 0}}},
        "setup_companion_offer_actions": [
            {"action": "accept", "npc_id": "bran", "turn_index": 3}
        ],
        "turns": ["I inspect the story recap after Bran joins."],
        "checks": [
            {
                "type": "campaign_story_recap",
                "turn_index": 4,
                "expected_party_npc_id": "bran",
            },
            {
                "type": "campaign_journal_contains",
                "expected_kind": "companion",
                "expected_summary_contains": "joined the party",
            },
        ],
    },
    "campaign_story_recap_narrator_context_has_rules": {
        **_story_setup(),
        "turns": ["I inspect the narrator-safe story recap."],
        "checks": [
            {
                "type": "campaign_story_recap",
                "turn_index": 2,
                "expected_arc_id": "arc:bandit_pressure",
            }
        ],
    },
    "campaign_journal_entry_idempotent": {
        "setup_campaign_journal_entries": [
            {
                "kind": "story_event",
                "summary": "The same event is recorded once.",
                "turn_index": 1,
                "source_id": "event:same",
            },
            {
                "kind": "story_event",
                "summary": "The same event is recorded once.",
                "turn_index": 1,
                "source_id": "event:same",
            },
        ],
        "turns": ["I inspect duplicate journal recording."],
        "checks": [
            {
                "type": "campaign_journal_contains",
                "expected_kind": "story_event",
                "expected_summary_contains": "recorded once",
            }
        ],
    },
    "campaign_story_recap_is_bounded": {
        "setup_campaign_journal_entries": [
            {
                "kind": "story_event",
                "summary": f"Journal event {i}",
                "turn_index": i,
                "source_id": f"event:{i}",
            }
            for i in range(80)
        ],
        "turns": ["I inspect the bounded story recap."],
        "checks": [
            {
                "type": "campaign_story_recap_bounded",
                "turn_index": 80,
                "max_items": 10,
            }
        ],
    },
}