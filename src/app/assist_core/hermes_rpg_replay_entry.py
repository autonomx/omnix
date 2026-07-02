from __future__ import annotations

from typing import Any


def hermes_rpg_replay_entry(audit_entry: dict[str, Any]) -> dict[str, Any]:
    command = str(audit_entry.get("command_text") or "").strip()
    return {
        "ok": bool(command),
        "source": "hermes_rpg_replay_entry",
        "command_text": command,
        "replay_kind": "rpg_command",
        "ticket_id": audit_entry.get("ticket_id"),
        "context_hash": audit_entry.get("context_hash"),
        "state_changed": False,
    }
