from __future__ import annotations

from typing import Any


def hermes_rpg_input_fill(card: dict[str, Any]) -> dict[str, Any]:
    command = str(card.get("command_text") or "").strip()
    ok = card.get("ok") is True and bool(command)
    return {
        "ok": ok,
        "source": "hermes_rpg_input_fill",
        "value": command,
        "fills_input": ok,
        "submits": False,
        "state_changed": False,
    }
