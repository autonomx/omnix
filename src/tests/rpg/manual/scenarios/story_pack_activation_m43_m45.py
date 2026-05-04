from __future__ import annotations

from typing import Any, Dict


def _activation_pack(proposal_id: str = "activation_bridge_pack") -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": proposal_id,
        "title": "Activation Bridge Pack",
        "lore_entries": [
            {
                "lore_id": f"lore:{proposal_id}",
                "title": "Activation Bridge Lore",
                "truth_status": "rumor",
            }
        ],
        "story_arcs": [
            {
                "arc_id": f"arc:{proposal_id}",
                "title": "Activation Bridge Arc",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": [f"lore:{proposal_id}"],
            }
        ],
        "story_events": [
            {
                "event_id": f"event:{proposal_id}",
                "arc_id": f"arc:{proposal_id}",
                "kind": "consequence",
                "summary": "The active story pack escalated.",
                "effects": [
                    {"type": "arc_stage_set", "arc_id": f"arc:{proposal_id}", "stage": "escalated"}
                ],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": f"rule:{proposal_id}",
                "arc_id": f"arc:{proposal_id}",
                "priority": 90,
                "conditions": [
                    {"type": "arc_pressure_at_least", "arc_id": f"arc:{proposal_id}", "minimum": 50},
                    {"type": "arc_stage", "arc_id": f"arc:{proposal_id}", "stage": "rumors"},
                ],
                "event": {"event_id": f"event:{proposal_id}", "arc_id": f"arc:{proposal_id}", "effects": []},
                "max_applications": 1,
            }
        ],
    }


# Manual test scenarios for story pack activation M43-M45

STORY_PACK_ACTIVATION_M43_M45_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_pack_imported_pack_starts_inactive": {
        "turns": ["I inspect an imported story pack before activation."],
        "checks": [
            {
                "type": "story_pack_activation_import",
                "proposal": _activation_pack("inactive_test_pack"),
                "turn_index": 1,
                "expected_ok": True,
            },
            {
                "type": "story_pack_activation_status",
                "pack_id": "storypack:inactive_test_pack",
                "expected_active": False,
            },
            {
                "type": "story_pack_activation_director_evaluate",
                "mode": "idle",
                "turn_index": 2,
                "expected_eligible_count": 0,
                "expected_registered_rule_count": 0,
            },
        ],
    },
    "story_pack_activation_enables_director_rules": {
        "turns": ["I activate an imported story pack and inspect director rules."],
        "checks": [
            {
                "type": "story_pack_activation_import",
                "proposal": _activation_pack("manual_import_pack"),
                "turn_index": 1,
                "expected_ok": True,
            },
            {
                "type": "story_pack_activation_activate",
                "pack_id": "storypack:manual_import_pack",
                "turn_index": 2,
                "expected_ok": True,
                "expected_reason": "activated",
            },
            {
                "type": "story_pack_activation_status",
                "pack_id": "storypack:manual_import_pack",
                "expected_active": True,
            },
            {
                "type": "story_pack_activation_director_evaluate",
                "mode": "idle",
                "turn_index": 3,
                "expected_eligible_count": 1,
                "expected_registered_rule_count": 1,
            },
        ],
    },
    "story_pack_activation_director_applies_active_pack_event": {
        "turns": ["I let the campaign director apply an active story pack event."],
        "checks": [
            {
                "type": "story_pack_activation_import",
                "proposal": _activation_pack("director_apply_pack"),
                "turn_index": 1,
                "expected_ok": True,
            },
            {
                "type": "story_pack_activation_activate",
                "pack_id": "storypack:director_apply_pack",
                "turn_index": 2,
                "expected_ok": True,
            },
            {
                "type": "story_pack_activation_director_apply",
                "mode": "idle",
                "turn_index": 3,
                "expected_applied_count": 1,
            },
        ],
    },
    "story_pack_deactivation_disables_director_rules": {
        "turns": ["I deactivate an active story pack and inspect director rules."],
        "checks": [
            {
                "type": "story_pack_activation_import",
                "proposal": _activation_pack("deactivation_test_pack"),
                "turn_index": 1,
                "expected_ok": True,
            },
            {
                "type": "story_pack_activation_activate",
                "pack_id": "storypack:deactivation_test_pack",
                "turn_index": 2,
                "expected_ok": True,
            },
            {
                "type": "story_pack_activation_deactivate",
                "pack_id": "storypack:deactivation_test_pack",
                "turn_index": 3,
                "expected_ok": True,
                "expected_reason": "deactivated",
            },
            {
                "type": "story_pack_activation_status",
                "pack_id": "storypack:deactivation_test_pack",
                "expected_active": False,
            },
            {
                "type": "story_pack_activation_director_evaluate",
                "mode": "idle",
                "turn_index": 4,
                "expected_eligible_count": 0,
                "expected_registered_rule_count": 0,
            },
        ],
    },
    "story_pack_activation_missing_pack_rejected": {
        "turns": ["I try to activate a missing story pack."],
        "checks": [
            {
                "type": "story_pack_activation_activate",
                "pack_id": "storypack:missing_pack",
                "turn_index": 1,
                "expected_ok": False,
                "expected_reason": "story_pack_not_imported",
            }
        ],
    },
    "story_authoring_approval_import_without_auto_activate_stays_inactive": {
        "turns": ["I approve an authored pack without auto activation."],
        "checks": [
            {
                "type": "story_pack_activation_approve_authored",
                "proposal": _activation_pack("draft_approve_no_auto_pack"),
                "draft_turn_index": 1,
                "turn_index": 2,
                "auto_activate": False,
                "expected_reason": "approved_imported",
            },
            {
                "type": "story_pack_activation_status",
                "pack_id": "storypack:draft_approve_no_auto_pack",
                "expected_active": False,
            },
            {
                "type": "story_pack_activation_director_evaluate",
                "mode": "idle",
                "turn_index": 3,
                "expected_eligible_count": 0,
                "expected_registered_rule_count": 0,
            },
        ],
    },
    "story_authoring_approval_auto_activate_bridges_to_director": {
        "turns": ["I approve an authored pack with auto activation."],
        "checks": [
            {
                "type": "story_pack_activation_approve_authored",
                "proposal": _activation_pack("draft_approve_auto_activate_pack"),
                "draft_turn_index": 1,
                "turn_index": 2,
                "auto_activate": True,
                "expected_reason": "approved_imported_activated",
            },
            {
                "type": "story_pack_activation_status",
                "pack_id": "storypack:draft_approve_auto_activate_pack",
                "expected_active": True,
            },
            {
                "type": "story_pack_activation_director_evaluate",
                "mode": "idle",
                "turn_index": 3,
                "expected_eligible_count": 1,
                "expected_registered_rule_count": 1,
            },
            {
                "type": "story_pack_activation_director_apply",
                "mode": "idle",
                "turn_index": 4,
                "expected_applied_count": 1,
            },
        ],
    },
    "story_pack_activation_snapshot_is_bounded": {
        "turns": ["I inspect bounded story pack activation state."],
        "checks": [
            *[
                {
                    "type": "story_pack_activation_import",
                    "proposal": _activation_pack(f"bounded_pack_{i}"),
                    "turn_index": i,
                    "expected_ok": True,
                }
                for i in range(30)
            ],
            {
                "type": "story_pack_activation_snapshot",
                "limit": 20,
            },
        ],
    },
}