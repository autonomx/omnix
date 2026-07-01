from __future__ import annotations

from app.assist_core.hermes_completion_audit import hermes_completion_audit_payload


def test_hermes_completion_audit_marks_active_rpg_flow_incomplete() -> None:
    payload = hermes_completion_audit_payload()

    assert payload["ok"] is True
    assert payload["complete_for_active_rpg_flow"] is False
    assert "planner_contract" in payload["missing_active"]
    assert "active_plan_route" in payload["missing_active"]


def test_hermes_completion_audit_lists_existing_surfaces() -> None:
    payload = hermes_completion_audit_payload()
    routes = {item["route"] for item in payload["surfaces"]}
    kinds = {item["name"]: item["kind"] for item in payload["surfaces"]}

    assert "/api/hermes/status" in routes
    assert "/api/hermes/rpg/context" in routes
    assert "/api/hermes/rpg/suggestions" in routes
    assert kinds["approve"] == "blocked"
    assert payload["preview_or_read_only_count"] >= 4
