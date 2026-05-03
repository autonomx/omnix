from __future__ import annotations

from typing import Any, Dict


def _valid_authored_pack() -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "authored_bandit_pack",
        "title": "Authored Bandit Pack",
        "lore_entries": [
            {
                "lore_id": "lore:authored_red_sashes",
                "title": "Authored Red Sashes",
                "truth_status": "rumor",
                "summary": "A fresh rumor says the Red Sashes are testing the road.",
            }
        ],
        "story_arcs": [
            {
                "arc_id": "arc:authored_bandit_pressure",
                "title": "Authored Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 10,
                "linked_lore": ["lore:authored_red_sashes"],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }


def _invalid_reference_pack() -> Dict[str, Any]:
    pack = _valid_authored_pack()
    pack["story_events"] = [
        {
            "event_id": "event:bad_authored",
            "arc_id": "arc:missing",
            "effects": [],
        }
    ]
    return pack


STORY_AUTHORING_M34_M36_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_authoring_prompt_uses_campaign_recap": {
        "setup_campaign_journal_entries": [
            {
                "kind": "story_event",
                "summary": "Bandit rumors reached the tavern.",
                "turn_index": 1,
                "source_id": "event:rumor",
            }
        ],
        "turns": ["I ask the story authoring system for a grounded proposal prompt."],
        "checks": [
            {
                "type": "story_authoring_prompt",
                "authoring_goal": "Create a grounded bandit escalation pack.",
                "must_contain": ["campaign_recap", "story_proposal_v1", "Bandit rumors reached the tavern"],
            }
        ],
    },
    "story_authoring_prompt_excludes_unrevealed_secret_lore": {
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
        "turns": ["I inspect the story authoring prompt for leaked secrets."],
        "checks": [
            {
                "type": "story_authoring_prompt",
                "authoring_goal": "Create a grounded story pack.",
                "must_contain": ["campaign_recap", "Do not reveal hidden or secret lore"],
                "must_not_contain": ["Bran secretly owes the Red Sashes"],
            }
        ],
    },
    "story_authoring_valid_proposal_validates_without_import": {
        "turns": ["I validate an authored story proposal without importing it."],
        "checks": [
            {
                "type": "story_authoring_run",
                "authoring_goal": "Create a small authored bandit pack.",
                "llm_text_override": _valid_authored_pack(),
                "import_if_valid": False,
                "expected_ok": True,
                "expected_reason": "validated",
            },
            {
                "type": "story_authoring_attempt",
                "expected_status": "validated",
                "expected_validation_ok": True,
                "expected_import_ok": False,
            },
        ],
    },
    "story_authoring_valid_proposal_imports_when_enabled": {
        "turns": ["I import a valid authored story proposal."],
        "checks": [
            {
                "type": "story_authoring_run",
                "authoring_goal": "Create and import a small authored bandit pack.",
                "llm_text_override": _valid_authored_pack(),
                "import_if_valid": True,
                "expected_ok": True,
                "expected_reason": "imported",
            },
            {
                "type": "story_authoring_imported_pack",
                "pack_id": "storypack:authored_bandit_pack",
            },
            {
                "type": "story_authoring_attempt",
                "expected_status": "imported",
                "expected_validation_ok": True,
                "expected_import_ok": True,
            },
        ],
    },
    "story_authoring_invalid_json_rejected": {
        "turns": ["I reject invalid story authoring JSON."],
        "checks": [
            {
                "type": "story_authoring_run",
                "authoring_goal": "Create invalid JSON.",
                "llm_text_override": "{bad json",
                "import_if_valid": True,
                "expected_ok": False,
                "expected_reason": "parse_failed",
            },
            {
                "type": "story_authoring_attempt",
                "expected_status": "parse_failed",
                "expected_validation_ok": False,
                "expected_import_ok": False,
            },
        ],
    },
    "story_authoring_invalid_reference_rejected_without_import": {
        "turns": ["I reject an authored story proposal with invalid references."],
        "checks": [
            {
                "type": "story_authoring_run",
                "authoring_goal": "Create invalid referenced pack.",
                "llm_text_override": _invalid_reference_pack(),
                "import_if_valid": True,
                "expected_ok": False,
                "expected_reason": "validation_failed",
            },
            {
                "type": "story_authoring_attempt",
                "expected_status": "validation_failed",
                "expected_validation_ok": False,
                "expected_import_ok": False,
            },
        ],
    },
    "story_authoring_attempt_history_is_bounded": {
        "setup_story_authoring_runs": [
            {
                "authoring_goal": f"Create authored pack {i}",
                "turn_index": i,
                "llm_text_override": dict(
                    _valid_authored_pack(),
                    proposal_id=f"authored_pack_{i}",
                    lore_entries=[
                        {
                            "lore_id": f"lore:authored_{i}",
                            "title": f"Authored {i}",
                            "truth_status": "rumor",
                        }
                    ],
                    story_arcs=[
                        {
                            "arc_id": f"arc:authored_{i}",
                            "title": f"Authored {i}",
                            "status": "active",
                            "stage": "rumors",
                            "pressure": 1,
                            "linked_lore": [f"lore:authored_{i}"],
                        }
                    ],
                ),
                "import_if_valid": False,
            }
            for i in range(130)
        ],
        "turns": ["I inspect bounded story authoring attempt history."],
        "checks": [
            {
                "type": "story_authoring_debug_bounded",
                "max_attempts": 100,
            }
        ],
    },
}