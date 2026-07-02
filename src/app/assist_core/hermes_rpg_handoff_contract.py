from __future__ import annotations

from typing import Any


def hermes_rpg_handoff_contract(fill_payload: dict[str, Any]) -> dict[str, Any]:
    command = str(fill_payload.get("value") or "").strip()
    ok = fill_payload.get("ok") is True and bool(command)
    return {
        "ok": ok,
        "source": "hermes_rpg_handoff_contract",
        "command_text": command,
        "canonical_path": "rpg_command_input",
        "hermes_submits": False,
        "state_changed": False,
    }
