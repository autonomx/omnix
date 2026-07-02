from __future__ import annotations

from typing import Any


def hermes_rpg_user_step(intent: dict[str, Any], *, confirmed: bool) -> dict[str, Any]:
    command = str(intent.get("command_text") or "").strip()
    ready = intent.get("ok") is True and bool(command) and confirmed is True
    return {
        "ok": ready,
        "source": "hermes_rpg_user_step",
        "command_text": command,
        "confirmed": confirmed is True,
        "ready": ready,
        "state_changed": False,
    }
