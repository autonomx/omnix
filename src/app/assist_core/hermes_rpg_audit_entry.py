from __future__ import annotations

from typing import Any


def hermes_rpg_audit_entry(payload: dict[str, Any]) -> dict[str, Any]:
    command = str(payload.get("command_text") or payload.get("value") or "").strip()
    return {
        "ok": bool(command),
        "source": "hermes_rpg_audit_entry",
        "ticket_id": payload.get("ticket_id"),
        "context_hash": payload.get("context_hash"),
        "command_text": command,
        "confirmed": payload.get("confirmed") is True,
        "state_changed": False,
    }
