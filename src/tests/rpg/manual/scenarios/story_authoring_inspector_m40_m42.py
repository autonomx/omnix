from __future__ import annotations

from typing import Any, Dict


def _valid_inspector_pack(proposal_id: str = "inspector_bandit_pack") -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": proposal_id,
        "title": "Inspector Bandit Pack",
        "lore_entries": [
            {
                "lore_id": f"lore:{proposal_id}",
                "title": "Inspector Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "story_arcs": [
            {
                "arc_id": f"arc:{proposal_id}",
                "title": "Inspector Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 10,
                "linked_lore": [f"lore:{proposal_id}"],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }


STORY_AUTHORING_INSPECTOR_M40_M42_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_authoring_inspector_payload_lists_pending_proposal": {
        "setup_story_authoring_approval_actions": [
            {
                "action": "draft",
                "authoring_goal": "Draft an inspector-visible pack.",
                "llm_text_override": _valid_inspector_pack(),
                "turn_index": 1,
            }
        ],
        "turns": ["I inspect pending authored story proposals."],
        "checks": [
            {
                "type": "story_authoring_inspector_payload",
                "expected_pending_count": 1,
                "expected_proposal_id": "inspector_bandit_pack",
            },
            {
                "type": "story_authoring_inspector_imported_pack",
                "pack_id": "storypack:inspector_bandit_pack",
                "expected_present": False,
            },
        ],
    },
    "story_authoring_inspector_draft_updates_pending_panel": {
        "turns": ["I draft an inspector proposal from the UI-facing wrapper."],
        "checks": [
            {
                "type": "story_authoring_inspector_draft",
                "authoring_goal": "Draft an inspector pack.",
                "llm_text_override": _valid_inspector_pack("inspector_draft_pack"),
                "turn_index": 1,
                "expected_ok": True,
                "expected_reason": "pending_approval",
            },
            {
                "type": "story_authoring_inspector_payload",
                "expected_pending_count": 1,
                "expected_proposal_id": "inspector_draft_pack",
            },
            {
                "type": "story_authoring_inspector_imported_pack",
                "pack_id": "storypack:inspector_draft_pack",
                "expected_present": False,
            },
        ],
    },
    "story_authoring_inspector_approve_imports_and_refreshes_panel": {
        "setup_story_authoring_approval_actions": [
            {
                "action": "draft",
                "authoring_goal": "Draft an inspector approval pack.",
                "llm_text_override": _valid_inspector_pack("inspector_approve_pack"),
                "turn_index": 1,
            }
        ],
        "turns": ["I approve the inspector pending proposal."],
        "checks": [
            {
                "type": "story_authoring_inspector_approve",
                "turn_index": 2,
                "expected_ok": True,
                "expected_reason": "approved_imported",
            },
            {
                "type": "story_authoring_inspector_payload",
                "expected_pending_count": 0,
            },
            {
                "type": "story_authoring_inspector_imported_pack",
                "pack_id": "storypack:inspector_approve_pack",
                "expected_present": True,
            },
        ],
    },
    "story_authoring_inspector_reject_removes_without_import": {
        "setup_story_authoring_approval_actions": [
            {
                "action": "draft",
                "authoring_goal": "Draft an inspector reject pack.",
                "llm_text_override": _valid_inspector_pack("inspector_reject_pack"),
                "turn_index": 1,
            }
        ],
        "turns": ["I reject the inspector pending proposal."],
        "checks": [
            {
                "type": "story_authoring_inspector_reject",
                "turn_index": 2,
                "reason": "needs rewrite",
                "expected_ok": True,
                "expected_reason": "rejected",
            },
            {
                "type": "story_authoring_inspector_payload",
                "expected_pending_count": 0,
            },
            {
                "type": "story_authoring_inspector_imported_pack",
                "pack_id": "storypack:inspector_reject_pack",
                "expected_present": False,
            },
        ],
    },
    "story_authoring_inspector_missing_approve_is_safe": {
        "turns": ["I try approving a missing inspector proposal."],
        "checks": [
            {
                "type": "story_authoring_inspector_approve",
                "pending_id": "authored_pending:missing",
                "turn_index": 1,
                "expected_ok": False,
                "expected_reason": "pending_proposal_missing",
            }
        ],
    },
    "story_authoring_inspector_missing_reject_is_safe": {
        "turns": ["I try rejecting a missing inspector proposal."],
        "checks": [
            {
                "type": "story_authoring_inspector_reject",
                "pending_id": "authored_pending:missing",
                "turn_index": 1,
                "expected_ok": False,
                "expected_reason": "pending_proposal_missing",
            }
        ],
    },
    "story_authoring_inspector_payload_is_bounded": {
        "setup_story_authoring_approval_actions": [
            {
                "action": "draft",
                "authoring_goal": "Draft multiple inspector packs.",
                "llm_text_override": _valid_inspector_pack("bounded_pack_1"),
                "turn_index": 1,
            },
            {
                "action": "draft",
                "authoring_goal": "Draft multiple inspector packs.",
                "llm_text_override": _valid_inspector_pack("bounded_pack_2"),
                "turn_index": 2,
            },
            {
                "action": "draft",
                "authoring_goal": "Draft multiple inspector packs.",
                "llm_text_override": _valid_inspector_pack("bounded_pack_3"),
                "turn_index": 3,
            },
        ],
        "turns": ["I check that the payload is bounded to prevent UI overload."],
        "checks": [
            {
                "type": "story_authoring_inspector_payload",
                "expected_pending_count": 3,
            },
            {
                "type": "story_authoring_inspector_debug_bounded",
                "limit": 20,
            },
        ],
    },
}