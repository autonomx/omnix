from __future__ import annotations

from typing import Any


def hermes_rpg_command_card(match_payload: dict[str, Any]) -> dict[str, Any]:
    command = str(match_payload.get("command") or "").strip()
    ok = match_payload.get("ok") is True and bool(command)
    return {
        "ok": ok,
        "source": "hermes_rpg_command_card",
        "ticket_id": match_payload.get("ticket_id"),
        "command_text": command,
        "fills_input": ok,
        "submits": False,
        "state_changed": False,
    }
