from __future__ import annotations

from app.assist_core.hermes_rpg_trace import hermes_rpg_trace_row


def test_hermes_rpg_trace_row_carries_ticket_and_context() -> None:
    payload = hermes_rpg_trace_row(
        {
            "mode": "pending",
            "planner_context": {"context_hash": "abc"},
            "ticket": {"ticket_id": "t1", "command": "check inventory"},
            "validation": {"valid": True},
        }
    )

    assert payload["ticket_id"] == "t1"
    assert payload["command"] == "check inventory"
    assert payload["context_hash"] == "abc"
    assert payload["valid"] is True
    assert payload["state_changed"] is False
