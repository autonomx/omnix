from __future__ import annotations

from typing import Any, Dict


def _valid_approval_pack(proposal_id: str = "approval_bandit_pack") -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": proposal_id,
        "title": "Approval Bandit Pack",
        "lore_entries": [
            {
                "lore_id": f"lore:{proposal_id}",
                "title": "Approval Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "story_arcs": [
            {
                "arc_id": f"arc:{proposal_id}",
                "title": "Approval Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 10,
                "linked_lore": [f"lore:{proposal_id}"],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }


def _invalid_approval_pack() -> Dict[str, Any]:
    pack = _valid_approval_pack("approval_invalid_pack")
    pack["story_events"] = [
        {
            "event_id": "event:approval_bad",
            "arc_id": "arc:missing",
            "effects": [],
        }
    ]
    return pack


STORY_AUTHORING_APPROVAL_M37_M39_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_authoring_approval_draft_creates_pending_without_import": {
        "turns": ["I draft an authored story pack for GM review."],
        "checks": [
            {
                "type": "story_authoring_approval_draft",
                "authoring_goal": "Draft a bandit pack for approval.",
                "llm_text_override": _valid_approval_pack(),
                "turn_index": 1,
                "expected_ok": True,
                "expected_reason": "pending_approval",
            },
            {
                "type": "story_authoring_approval_pending",
                "expected_count": 1,
                "expected_proposal_id": "approval_bandit_pack",
            },
            {
                "type": "story_authoring_approval_imported_pack",
                "pack_id": "storypack:approval_bandit_pack",
                "expected_present": False,
            },
        ],
    },
    "story_authoring_approval_approve_imports_pending_pack": {
        "setup_story_authoring_approval_actions": [
            {
                "action": "draft",
                "authoring_goal": "Draft a bandit pack for approval.",
                "llm_text_override": _valid_approval_pack(),
                "turn_index": 1,
            }
        ],
        "turns": ["I approve the pending authored story pack."],
        "checks": [
            {
                "type": "story_authoring_approval_approve",
                "turn_index": 2,
                "expected_ok": True,
                "expected_reason": "approved_imported",
            },
            {
                "type": "story_authoring_approval_imported_pack",
                "pack_id": "storypack:approval_bandit_pack",
                "expected_present": True,
            },
            {
                "type": "story_authoring_approval_pending",
                "expected_count": 0,
            },
            {
                "type": "story_authoring_approval_history",
                "expected_status": "approved",
            },
        ],
    },
    "story_authoring_approval_reject_removes_pending_without_import": {
        "setup_story_authoring_approval_actions": [
            {
                "action": "draft",
                "authoring_goal": "Draft a bandit pack for approval.",
                "llm_text_override": _valid_approval_pack("approval_rejected_pack"),
                "turn_index": 1,
            }
        ],
        "turns": ["I reject the pending authored story pack."],
        "checks": [
            {
                "type": "story_authoring_approval_reject",
                "turn_index": 2,
                "reason": "too early",
                "expected_ok": True,
                "expected_reason": "rejected",
            },
            {
                "type": "story_authoring_approval_imported_pack",
                "pack_id": "storypack:approval_rejected_pack",
                "expected_present": False,
            },
            {
                "type": "story_authoring_approval_pending",
                "expected_count": 0,
            },
            {
                "type": "story_authoring_approval_history",
                "expected_status": "rejected",
            },
        ],
    },
    "story_authoring_approval_invalid_draft_not_pending": {
        "turns": ["I try to draft an invalid authored story pack."],
        "checks": [
            {
                "type": "story_authoring_approval_draft",
                "authoring_goal": "Draft an invalid pack.",
                "llm_text_override": _invalid_approval_pack(),
                "turn_index": 1,
                "expected_ok": False,
                "expected_reason": "authoring_failed",
            },
            {
                "type": "story_authoring_approval_pending",
                "expected_count": 0,
            },
        ],
    },
    "story_authoring_approval_approve_missing_pending_rejected": {
        "turns": ["I try to approve a missing authored proposal."],
        "checks": [
            {
                "type": "story_authoring_approval_approve",
                "pending_id": "authored_pending:missing",
                "turn_index": 1,
                "expected_ok": False,
                "expected_reason": "pending_proposal_missing",
            }
        ],
    },
    "story_authoring_approval_reject_missing_pending_rejected": {
        "turns": ["I try to reject a missing authored proposal."],
        "checks": [
            {
                "type": "story_authoring_approval_reject",
                "pending_id": "authored_pending:missing",
                "turn_index": 1,
                "expected_ok": False,
                "expected_reason": "pending_proposal_missing",
            }
        ],
    },
    "story_authoring_approval_debug_is_bounded": {
        "setup_story_authoring_approval_actions": [
            {
                "action": "draft",
                "authoring_goal": f"Draft pack {i}",
                "llm_text_override": _valid_approval_pack(f"approval_pack_{i}"),
                "turn_index": i,
            }
            for i in range(70)
        ],
        "turns": ["I inspect bounded GM approval debug state."],
        "checks": [
            {
                "type": "story_authoring_approval_debug_bounded",
                "max_pending": 50,
                "max_history": 100,
            }
        ],
    },
}