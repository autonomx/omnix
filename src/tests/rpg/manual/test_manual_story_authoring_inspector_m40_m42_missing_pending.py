from tests.rpg.manual.story_authoring_inspector_m40_m42_checks import (
    run_story_authoring_inspector_m40_m42_checks,
)


def test_manual_story_authoring_inspector_missing_approve_reason_is_canonical():
    session = {"simulation_state": {}}

    result = run_story_authoring_inspector_m40_m42_checks(
        checks=[
            {
                "type": "story_authoring_inspector_approve",
                "pending_id": "authored_pending:missing",
                "expected_ok": False,
                "expected_reason": "pending_proposal_missing",
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_story_authoring_inspector_missing_reject_reason_is_canonical():
    session = {"simulation_state": {}}

    result = run_story_authoring_inspector_m40_m42_checks(
        checks=[
            {
                "type": "story_authoring_inspector_reject",
                "pending_id": "authored_pending:missing",
                "expected_ok": False,
                "expected_reason": "pending_proposal_missing",
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True