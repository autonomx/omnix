import json

from app.rpg.story_authoring.approval import draft_story_proposal_for_approval
from app.rpg.story_authoring.inspector import (
    approve_story_authoring_inspector_proposal,
    build_story_authoring_inspector_payload,
    draft_story_authoring_inspector_proposal,
    reject_story_authoring_inspector_proposal,
)
from app.rpg.story_packs.registry import get_imported_story_pack


def _valid_pack(proposal_id: str = "inspector_bandit_pack"):
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": proposal_id,
        "title": "Inspector Bandit Pack",
        "lore_entries": [
            {"lore_id": f"lore:{proposal_id}", "title": "Inspector Lore", "truth_status": "rumor"}
        ],
        "story_arcs": [
            {
                "arc_id": f"arc:{proposal_id}",
                "title": "Inspector Arc",
                "status": "active",
                "stage": "rumors",
                "pressure": 10,
                "linked_lore": [f"lore:{proposal_id}"],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }


def test_story_authoring_inspector_payload_lists_pending_summary_without_import():
    simulation_state = {}
    draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft inspector pack.",
        llm_text_override=json.dumps(_valid_pack()),
        turn_index=1,
    )

    payload = build_story_authoring_inspector_payload(simulation_state)

    assert payload["ok"] is True
    assert payload["format_version"] == "story_authoring_inspector_v1"
    assert payload["pending_count"] == 1
    assert payload["pending"][0]["proposal_id"] == "inspector_bandit_pack"
    assert payload["pending"][0]["proposal_summary"]["counts"]["lore_entries"] == 1
    assert "story_pack_state" not in simulation_state


def test_story_authoring_inspector_draft_wrapper_returns_updated_payload():
    simulation_state = {}

    result = draft_story_authoring_inspector_proposal(
        simulation_state,
        authoring_goal="Draft inspector pack.",
        llm_text_override=json.dumps(_valid_pack()),
        turn_index=1,
    )

    assert result["ok"] is True
    assert result["inspector"]["pending_count"] == 1


def test_story_authoring_inspector_approve_imports_and_refreshes_payload():
    simulation_state = {}
    draft = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft inspector pack.",
        llm_text_override=json.dumps(_valid_pack()),
        turn_index=1,
    )

    result = approve_story_authoring_inspector_proposal(
        simulation_state,
        pending_id=draft["pending_id"],
        turn_index=2,
    )

    assert result["ok"] is True
    assert result["reason"] == "approved_imported"
    assert result["inspector"]["pending_count"] == 0
    assert get_imported_story_pack(simulation_state, "storypack:inspector_bandit_pack") is not None


def test_story_authoring_inspector_reject_removes_pending_without_import():
    simulation_state = {}
    draft = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft inspector reject pack.",
        llm_text_override=json.dumps(_valid_pack("inspector_reject_pack")),
        turn_index=1,
    )

    result = reject_story_authoring_inspector_proposal(
        simulation_state,
        pending_id=draft["pending_id"],
        turn_index=2,
        reason="not now",
    )

    assert result["ok"] is True
    assert result["reason"] == "rejected"
    assert result["inspector"]["pending_count"] == 0
    assert get_imported_story_pack(simulation_state, "storypack:inspector_reject_pack") is None


def test_story_authoring_inspector_payload_is_bounded():
    simulation_state = {}
    for i in range(70):
        draft_story_proposal_for_approval(
            simulation_state,
            authoring_goal=f"Draft inspector pack {i}.",
            llm_text_override=json.dumps(_valid_pack(f"inspector_pack_{i}")),
            turn_index=i,
        )

    payload = build_story_authoring_inspector_payload(simulation_state, limit=20)

    assert len(payload["pending"]) <= 20
    assert payload["bounded"]["max_pending"] == 20