from __future__ import annotations

from typing import Any


def rpg_handoff_payload(command_text: str, source: str = "planner") -> dict[str, Any]:
    return {
        "ok": bool(command_text.strip()),
        "source": source,
        "command_text": command_text.strip(),
        "proposal_only": True,
        "applied": False,
        "simulation_must_validate": True,
        "review_required": True,
        "read_only": True,
        "executes": False,
    }
