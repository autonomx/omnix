from __future__ import annotations

from app.assist_core.hermes_rpg_plan_summary import hermes_rpg_plan_summary_payload


def test_hermes_rpg_plan_summary_lists_parts_without_writes() -> None:
    payload = hermes_rpg_plan_summary_payload()

    assert payload["ok"] is True
    assert payload["path"] == "/api/hermes/plan"
    assert payload["parts"] == [
        "context",
        "request",
        "normalize",
        "validate",
        "ticket",
        "trace",
        "ticket_match",
        "command_card",
        "command_bundle",
        "command_summary",
    ]
    assert payload["writes_state"] is False
    assert payload["default_enabled"] is False
    assert payload["user_step"] is True
