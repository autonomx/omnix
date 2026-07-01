from __future__ import annotations

from typing import Any

from .hermes_rpg_command_card import hermes_rpg_command_card
from .hermes_rpg_ticket import hermes_rpg_ticket_match


def hermes_rpg_command_bundle(ticket: dict[str, Any], submitted_id: str) -> dict[str, Any]:
    match = hermes_rpg_ticket_match(ticket, submitted_id)
    card = hermes_rpg_command_card(match)
    return {
        "ok": match.get("ok") is True and card.get("ok") is True,
        "source": "hermes_rpg_command_bundle",
        "match": match,
        "card": card,
        "state_changed": False,
    }
