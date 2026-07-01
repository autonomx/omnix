from __future__ import annotations

from app.assist_core.plan_boundary_guard import plan_boundary_guard
from app.assist_core.rpg_handoff_payload import rpg_handoff_payload
from app.assist_core.rpg_handoff_validation import validate_rpg_handoff_payload


def test_review_payload_stays_read_only() -> None:
    payload = plan_boundary_guard({"summary": "Review only."})

    assert payload["ok"] is True
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_rpg_payload_stays_not_applied() -> None:
    handoff = rpg_handoff_payload("inspect")
    checked = validate_rpg_handoff_payload(handoff)

    assert handoff["proposal_only"] is True
    assert handoff["applied"] is False
    assert checked["status"] == "valid_for_review"
    assert checked["review_required"] is True
    assert checked["executes"] is False
