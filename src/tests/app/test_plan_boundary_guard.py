from __future__ import annotations

from app.assist_core.plan_boundary_guard import plan_boundary_guard


def test_plan_boundary_guard_allows_review_only_payloads() -> None:
    payload = plan_boundary_guard({"summary": "Review only."})

    assert payload == {
        "ok": True,
        "status": "allowed_for_review",
        "blocked_keys": [],
        "simulation_must_validate": True,
        "review_required": True,
        "read_only": True,
        "executes": False,
    }


def test_plan_boundary_guard_blocks_state_mutation_fields() -> None:
    payload = plan_boundary_guard({"state_delta": {"currency": 1}, "location": "town"})

    assert payload["ok"] is False
    assert payload["status"] == "blocked_by_boundary"
    assert payload["blocked_keys"] == ["location", "state_delta"]
    assert payload["simulation_must_validate"] is True
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False
