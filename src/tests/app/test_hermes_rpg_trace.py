from __future__ import annotations

from app.assist_core.hermes_rpg_trace import hermes_rpg_trace_row, hermes_rpg_trace_summary


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


def test_hermes_rpg_trace_summary_counts_rows() -> None:
    payload = hermes_rpg_trace_summary(
        [
            {"ticket_id": "t1", "valid": True},
            {"ticket_id": "t2", "valid": False},
            {"valid": True},
        ]
    )

    assert payload["count"] == 3
    assert payload["valid_count"] == 2
    assert payload["ticket_ids"] == ["t1", "t2"]
    assert payload["state_changed"] is False
