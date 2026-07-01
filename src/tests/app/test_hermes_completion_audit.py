from __future__ import annotations

from app.assist_core.hermes_completion_audit import hermes_completion_audit_payload


def test_hermes_completion_audit_marks_rpg_ticket_path_complete() -> None:
    payload = hermes_completion_audit_payload()

    assert payload["ok"] is True
    assert payload["rpg_ticket_path_complete"] is True
    assert payload["missing_active"] == []
    assert payload["writes_state"] is False
    assert "command_summary" in payload["rpg_chain"]


def test_hermes_completion_audit_lists_existing_surfaces() -> None:
    payload = hermes_completion_audit_payload()
    routes = {item["route"] for item in payload["surfaces"]}
    kinds = {item["name"]: item["kind"] for item in payload["surfaces"]}

    assert "/api/hermes/status" in routes
    assert "/api/hermes/rpg/context" in routes
    assert "/api/hermes/rpg/suggestions" in routes
    assert "/api/hermes/plan" in routes
    assert kinds["approve"] == "blocked"
    assert kinds["rpg_plan"] == "ticket"
    assert payload["preview_or_read_only_count"] >= 6
