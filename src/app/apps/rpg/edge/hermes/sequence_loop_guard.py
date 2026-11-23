from __future__ import annotations

from typing import Any
from app.apps.rpg.foundation.safe_values import folded_text

SOURCE = "hermes_sequence_loop_guard"


def _items(sequence: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in sequence.get("items", []) if isinstance(item, dict)]


def hermes_sequence_loop_guard(sequence: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    seen_commands: set[str] = set()
    seen_ids: set[str] = set()
    for item in _items(sequence):
        item_id = folded_text(item.get("item_id"))
        command = folded_text(item.get("statement"))
        if item_id and item_id in seen_ids:
            return {"ok": False, "source": SOURCE, "stop_reason": "loop_detected", "detail": "duplicate_item_id"}
        if command and command in seen_commands:
            return {"ok": False, "source": SOURCE, "stop_reason": "duplicate_command", "detail": command}
        seen_ids.add(item_id)
        seen_commands.add(command)

    state = dict(state) if isinstance(state, dict) else {}
    last_result = raw_last_result if isinstance(raw_last_result := state.get("last_result"), dict) else {}
    if last_result and last_result.get("state_changed") is False:
        return {"ok": False, "source": SOURCE, "stop_reason": "no_progress", "detail": "last_result_state_unchanged"}
    if folded_text(sequence.get("state_owner")) and sequence.get("state_owner") != "rpg_sim":
        return {"ok": False, "source": SOURCE, "stop_reason": "state_mismatch", "detail": "invalid_state_owner"}
    return {"ok": True, "source": SOURCE, "stop_reason": None, "detail": None}
