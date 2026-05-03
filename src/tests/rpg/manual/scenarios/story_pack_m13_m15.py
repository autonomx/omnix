from __future__ import annotations

from typing import Any, Dict


def _valid_pack() -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "red_sashes_intro",
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


STORY_PACK_M13_M15_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_pack_import_adds_lore_arcs_events_rules": {
        "setup_story_packs": [{"proposal": _valid_pack(), "turn_index": 1}],
        "turns": ["I inspect the imported Red Sashes story pack."],
        "checks": [
            {
                "type": "story_pack_lore",
                "lore_id": "lore:red_sashes",
                "expected": {"truth_status": "rumor"},
            },
            {
                "type": "story_pack_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors", "pressure": 20},
            },
            {"type": "story_pack_event_definition", "event_id": "event:bandit_rumor_spreads"},
            {"type": "story_pack_rule_definition", "rule_id": "rule:bandit_warning"},
            {"type": "story_pack_imported", "pack_id": "storypack:red_sashes_intro"},
        ],
    },
    "story_pack_import_is_idempotent": {
        "setup_story_packs": [
            {"proposal": _valid_pack(), "turn_index": 1},
            {"proposal": _valid_pack(), "turn_index": 2},
        ],
        "turns": ["I import the same story pack twice."],
        "checks": [
            {"type": "story_pack_imported", "pack_id": "storypack:red_sashes_intro"},
            {"type": "story_pack_debug_bounded", "max_packs": 1},
        ],
    },
    "story_pack_import_does_not_overwrite_existing_true_lore": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "true",
            }
        ],
        "turns": ["I try to import a pack that contradicts true lore."],
        "checks": [
            {
                "type": "story_pack_import",
                "proposal": dict(
                    _valid_pack(),
                    lore_entries=[
                        {
                            "lore_id": "lore:red_sashes",
                            "title": "The Red Sashes",
                            "truth_status": "false",
                        }
                    ],
                ),
                "expected_ok": False,
                "required_reason": "validation_failed",
            },
            {
                "type": "story_pack_lore",
                "lore_id": "lore:red_sashes",
                "expected": {"truth_status": "true"},
            },
        ],
    },
    "story_pack_can_seed_starter_quest": {
        "setup_story_packs": [
            {
                "proposal": _valid_pack(),
                "starter_quests": [
                    {
                        "action": "start",
                        "quest_id": "quest:stop_red_sashes",
                        "stage": "investigate",
                    }
                ],
            }
        ],
        "turns": ["I inspect the starter quest seeded by the story pack."],
        "checks": [
            {
                "type": "story_pack_quest",
                "quest_id": "quest:stop_red_sashes",
                "expected": {"stage": "investigate", "status": "active"},
            }
        ],
    },
    "story_pack_can_seed_arc_pressure": {
        "setup_story_packs": [{"proposal": dict(_valid_pack(), story_arcs=[dict(_valid_pack()["story_arcs"][0], pressure=55)])}],
        "turns": ["I inspect seeded arc pressure."],
        "checks": [
            {
                "type": "story_pack_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"pressure": 55},
            }
        ],
    },
    "story_pack_can_link_npcs_locations_quests": {
        "setup_story_packs": [
            {
                "proposal": dict(
                    _valid_pack(),
                    story_arcs=[
                        dict(
                            _valid_pack()["story_arcs"][0],
                            linked_entities=["bran", "mira"],
                            linked_locations=["tavern_common_room", "street"],
                            linked_quests=["quest:stop_red_sashes"],
                        )
                    ],
                )
            }
        ],
        "turns": ["I inspect story arc links from the imported pack."],
        "checks": [
            {
                "type": "story_pack_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {
                    "linked_entities": ["bran", "mira"],
                    "linked_locations": ["tavern_common_room", "street"],
                    "linked_quests": ["quest:stop_red_sashes"],
                },
            }
        ],
    },
    "story_pack_invalid_reference_rejected": {
        "turns": ["I try to import a pack with invalid references."],
        "checks": [
            {
                "type": "story_pack_import",
                "proposal": {
                    "proposal_version": "story_proposal_v1",
                    "proposal_type": "story_pack",
                    "title": "Invalid Pack",
                    "lore_entries": [{"lore_id": "", "title": "Empty ID"}],
                },
                "expected_ok": False,
            },
            {
                "type": "story_pack_import",
                "proposal": {
                    "proposal_version": "story_proposal_v1",
                    "proposal_type": "story_pack",
                    "title": "Invalid Pack 2",
                    "story_arcs": [{"arc_id": "", "title": "Empty Arc ID"}],
                },
                "expected_ok": False,
            },
        ],
    },
    "story_pack_debug_summary_is_bounded": {
        "setup_story_packs": [{"proposal": _valid_pack()}],
        "turns": ["I inspect the bounded story pack debug summary."],
        "checks": [
            {
                "type": "story_pack_debug_bounded",
                "max_packs": 5,
            }
        ],
    },
}