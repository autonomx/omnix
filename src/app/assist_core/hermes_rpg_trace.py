from __future__ import annotations

from typing import Any


def hermes_rpg_trace_row(payload: dict[str, Any]) -> dict[str, Any]:
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
    context = payload.get("planner_context") if isinstance(payload.get("planner_context"), dict) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    return {
        "ok": True,
        "source": "hermes_rpg_trace",
        "ticket_id": ticket.get("ticket_id"),
        "command": ticket.get("command"),
        "valid": validation.get("valid") is True,
        "context_hash": context.get("context_hash"),
        "mode": payload.get("mode"),
        "state_changed": False,
    }


def hermes_rpg_trace_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    clean_rows = [row for row in rows if isinstance(row, dict)]
    return {
        "ok": True,
        "source": "hermes_rpg_trace_summary",
        "count": len(clean_rows),
        "valid_count": sum(1 for row in clean_rows if row.get("valid") is True),
        "ticket_ids": [row.get("ticket_id") for row in clean_rows if row.get("ticket_id")],
        "state_changed": False,
    }
