from tests.rpg.manual.story_authoring_approval_m37_m39_checks import (
    run_story_authoring_approval_m37_m39_checks,
)


def _valid_pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "manual_approval_pack",
        "title": "Manual Approval Pack",
        "lore_entries": [
            {"lore_id": "lore:manual_approval", "title": "Manual Approval", "truth_status": "rumor"}
        ],
        "story_arcs": [
            {
                "arc_id": "arc:manual_approval",
                "title": "Manual Approval",
                "status": "active",
                "stage": "rumors",
                "pressure": 1,
                "linked_lore": ["lore:manual_approval"],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }


def test_manual_story_authoring_approval_draft_and_pending_checks():
    session = {"simulation_state": {}}

    draft = run_story_authoring_approval_m37_m39_checks(
        checks=[
            {
                "type": "story_authoring_approval_draft",
                "authoring_goal": "Draft a pack.",
                "llm_text_override": _valid_pack(),
                "expected_ok": True,
                "expected_reason": "pending_approval",
            }
        ],
        result={},
        session=session,
    )[0]
    pending = run_story_authoring_approval_m37_m39_checks(
        checks=[
            {
                "type": "story_authoring_approval_pending",
                "expected_count": 1,
                "expected_proposal_id": "manual_approval_pack",
            }
        ],
        result={},
        session=session,
    )[0]

    assert draft["check_type"] == "story_authoring_approval_draft"
    assert draft["ok"] is True, f"Draft failed: {draft}"
    assert pending["check_type"] == "story_authoring_approval_pending"
    assert pending["ok"] is True, f"Pending failed: {pending}"


def test_manual_story_authoring_approval_approve_check_imports_pack():
    session = {"simulation_state": {}}
    run_story_authoring_approval_m37_m39_checks(
        checks=[
            {
                "type": "story_authoring_approval_draft",
                "authoring_goal": "Draft a pack.",
                "llm_text_override": _valid_pack(),
                "expected_ok": True,
            }
        ],
        result={},
        session=session,
    )

    approved = run_story_authoring_approval_m37_m39_checks(
        checks=[
            {
                "type": "story_authoring_approval_approve",
                "expected_ok": True,
                "expected_reason": "approved_imported",
            }
        ],
        result={},
        session=session,
    )[0]

    assert approved["ok"] is True