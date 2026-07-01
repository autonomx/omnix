from __future__ import annotations

from typing import Any


def hermes_rpg_command_summary(cards: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [card for card in cards if isinstance(card, dict)]
    submits_count = sum(1 for card in rows if card.get("submits") is True)
    changed_count = sum(1 for card in rows if card.get("state_changed") is True)
    return {
        "ok": True,
        "source": "hermes_rpg_command_summary",
        "count": len(rows),
        "fillable_count": sum(1 for card in rows if card.get("fills_input") is True),
        "submits_count": submits_count,
        "changed_count": changed_count,
        "clear": submits_count == 0 and changed_count == 0,
        "state_changed": False,
    }
