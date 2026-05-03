from __future__ import annotations

from typing import Any, Dict


def _valid_story_pack() -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "proposal:red_sashes_intro",
        "title": "Red Sashes Intro",
        "lore_entries": [
            {
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "kind": "faction",
                "truth_status": "rumor",
                "tags": ["bandit", "local-threat"],
                "summary": "A road gang known for red cloth tied around their arms.",
            }
        ],
        "story_arcs": [
            {
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 20,
                "linked_lore": ["lore:red_sashes"],
                "linked_entities": ["bran"],
                "linked_locations": ["tavern_common_room"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:bandit_rumor_spreads",
                "arc_id": "arc:bandit_pressure",
                "kind": "rumor",
                "summary": "Rumors of Red Sashes activity spread.",
                "effects": [
                    {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 10},
                    {"type": "world_event_emit"},
                ],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": "rule:bandit_warning",
                "arc_id": "arc:bandit_pressure",
                "priority": 70,
                "cooldown_turns": 3,
                "max_applications": 1,
                "conditions": [
                    {
                        "type": "arc_pressure_at_least",
                        "arc_id": "arc:bandit_pressure",
                        "minimum": 50,
                    }
                ],
                "event": {
                    "event_id": "event:bandits_warn_bran",
                    "arc_id": "arc:bandit_pressure",
                    "kind": "warning",
                    "summary": "Bandits warned Bran to pay protection money.",
                    "effects": [
                        {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "threat"}
                    ],
                },
            }
        ],
    }


STORY_PROPOSAL_M10_M12_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_proposal_valid_pack_imports": {
        "turns": ["I validate a proposed Red Sashes story pack."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": _valid_story_pack(),
                "expected_ok": True,
            },
            {
                "type": "story_proposal_normalized_counts",
                "proposal": _valid_story_pack(),
                "expected": {
                    "lore_entries": 1,
                    "story_arcs": 1,
                    "story_events": 1,
                    "escalation_rules": 1,
                },
            },
        ],
    },
    "story_proposal_invalid_json_rejected": {
        "turns": ["I validate a malformed story proposal."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": "not a dict",
                "expected_ok": False,
                "required_error": "unsupported_proposal_version",
            }
        ],
    },
    "story_proposal_unknown_arc_rejected": {
        "turns": ["I validate an event referencing a missing arc."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": {
                    "proposal_version": "story_proposal_v1",
                    "proposal_type": "story_pack",
                    "story_events": [
                        {"event_id": "event:x", "arc_id": "arc:missing", "effects": []}
                    ],
                },
                "expected_ok": False,
                "required_error": "unknown_arc_reference",
            }
        ],
    },
    "story_proposal_unknown_location_rejected": {
        "setup_spatial_graph": "tavern_fixture",
        "turns": ["I validate an event referencing an impossible location."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": {
                    "proposal_version": "story_proposal_v1",
                    "proposal_type": "story_pack",
                    "story_arcs": [
                        {"arc_id": "arc:bandit_pressure", "title": "Bandit Pressure"}
                    ],
                    "story_events": [
                        {
                            "event_id": "event:x",
                            "arc_id": "arc:bandit_pressure",
                            "location_id": "missing_location",
                            "effects": [],
                        }
                    ],
                },
                "expected_ok": False,
                "required_error": "unknown_location_reference",
            }
        ],
    },
    "story_proposal_unbounded_pressure_rejected": {
        "turns": ["I validate an unbounded pressure proposal."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": dict(
                    _valid_story_pack(),
                    story_events=[
                        {
                            "event_id": "event:bad_pressure",
                            "arc_id": "arc:bandit_pressure",
                            "effects": [
                                {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 999}
                            ],
                        }
                    ],
                ),
                "expected_ok": False,
                "required_error": "pressure_delta_out_of_bounds",
            }
        ],
    },
    "story_proposal_unknown_effect_rejected": {
        "turns": ["I validate an unknown story effect."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": dict(
                    _valid_story_pack(),
                    story_events=[
                        {
                            "event_id": "event:bad_effect",
                            "arc_id": "arc:bandit_pressure",
                            "effects": [{"type": "invent_gold", "amount": 999}],
                        }
                    ],
                ),
                "expected_ok": False,
                "required_error": "unknown_effect_type",
            }
        ],
    },
    "story_proposal_contradicts_true_lore_rejected": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "true",
            }
        ],
        "turns": ["I validate contradictory lore."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": dict(
                    _valid_story_pack(),
                    lore_entries=[
                        {
                            "lore_id": "lore:red_sashes",
                            "title": "The Red Sashes",
                            "truth_status": "false",
                        }
                    ],
                ),
                "expected_ok": False,
                "required_error": "contradicts_existing_true_lore",
            }
        ],
    },
    "story_proposal_rumor_kept_as_rumor": {
        "turns": ["I validate that rumor lore stays a rumor."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": _valid_story_pack(),
                "expected_ok": True,
            }
        ],
    },
    "story_proposal_secret_not_revealed_by_default": {
        "turns": ["I validate secret lore reveal rules."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": dict(
                    _valid_story_pack(),
                    lore_entries=[
                        {
                            "lore_id": "lore:bran_debt",
                            "title": "Bran's Debt",
                            "truth_status": "secret",
                            "revealed_to_player": True,
                        }
                    ],
                ),
                "expected_ok": False,
                "required_error": "secret_lore_revealed_by_default",
            }
        ],
    },
    "story_proposal_duplicate_ids_rejected": {
        "turns": ["I validate duplicate proposal IDs."],
        "checks": [
            {
                "type": "story_proposal_validation",
                "proposal": dict(
                    _valid_story_pack(),
                    lore_entries=[
                        {"lore_id": "lore:x", "title": "X"},
                        {"lore_id": "lore:x", "title": "X again"},
                    ],
                ),
                "expected_ok": False,
                "required_error": "duplicate_id",
            }
        ],
    },
}