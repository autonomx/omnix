import json

from app.rpg.story_authoring.approval import (
    approve_story_proposal,
    draft_story_proposal_for_approval,
    list_pending_story_proposals,
    reject_story_proposal,
)
from app.rpg.story_packs.registry import get_imported_story_pack


def _valid_pack(proposal_id: str = "approval_bandit_pack"):
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


def test_draft_story_proposal_for_approval_does_not_import():
    simulation_state = {}

    result = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft a pack.",
        llm_text_override=json.dumps(_valid_pack()),
        turn_index=1,
    )

    pending = list_pending_story_proposals(simulation_state)
    assert result["ok"] is True
    assert result["reason"] == "pending_approval"
    assert pending["pending_count"] == 1
    assert "story_pack_state" not in simulation_state


def test_approve_story_proposal_imports_pending_pack_once():
    simulation_state = {}
    draft = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft a pack.",
        llm_text_override=json.dumps(_valid_pack()),
        turn_index=1,
    )

    first = approve_story_proposal(
        simulation_state,
        pending_id=draft["pending_id"],
        turn_index=2,
    )
    second = approve_story_proposal(
        simulation_state,
        pending_id=draft["pending_id"],
        turn_index=3,
    )

    assert first["ok"] is True
    assert first["reason"] == "approved_imported"
    assert get_imported_story_pack(simulation_state, "storypack:approval_bandit_pack") is not None
    assert second["ok"] is False
    assert second["reason"] == "pending_proposal_missing"
    assert list_pending_story_proposals(simulation_state)["pending_count"] == 0


def test_reject_story_proposal_removes_pending_without_import():
    simulation_state = {}
    draft = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft a pack.",
        llm_text_override=json.dumps(_valid_pack()),
        turn_index=1,
    )

    result = reject_story_proposal(
        simulation_state,
        pending_id=draft["pending_id"],
        turn_index=2,
        reason="not today",
    )

    state = simulation_state["story_authoring_approval_state"]
    assert result["ok"] is True
    assert result["reason"] == "rejected"
    assert state["pending"] == []
    assert state["history"][0]["status"] == "rejected"
    assert "story_pack_state" not in simulation_state


def test_invalid_draft_is_not_pending():
    simulation_state = {}
    invalid = _valid_pack()
    invalid["story_events"] = [{"event_id": "event:bad", "arc_id": "arc:missing", "effects": []}]

    result = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft invalid pack.",
        llm_text_override=json.dumps(invalid),
        turn_index=1,
    )

    assert result["ok"] is False
    assert result["reason"] == "authoring_failed"
    assert list_pending_story_proposals(simulation_state)["pending_count"] == 0


def test_authoring_approval_state_is_bounded():
    simulation_state = {}
    for i in range(70):
        draft_story_proposal_for_approval(
            simulation_state,
            authoring_goal=f"Draft pack {i}.",
            llm_text_override=json.dumps(_valid_pack(f"approval_pack_{i}")),
            turn_index=i,
        )

    assert len(simulation_state["story_authoring_approval_state"]["pending"]) == 50