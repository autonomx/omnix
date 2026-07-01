from __future__ import annotations

from typing import Any


def hermes_rpg_command_summary(cards: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [card for card in cards if isinstance(card, dict)]
    return {
        "ok": True,
        "source": "hermes_rpg_command_summary",
        "count": len(rows),
        "fillable_count": sum(1 for card in rows if card.get("fills_input") is True),
        "submits_count": sum(1 for card in rows if card.get("submits") is True),
        "state_changed": False,
    }
