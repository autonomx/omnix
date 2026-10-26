"""What a lost fight costs, and what a rest restores (RQ-5.1; docs/rpg/design/stakes.md).

A standard defeat is a setback: the hero wakes where they last rested, hurt and battered, lighter in the
purse, perhaps without something they carried. In a hardcore campaign defeat ends the hero's story. A heavy
blow leaves a wound that lingers until a potion, a healer or two nights' rest.
"""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict, safe_list, safe_str
from app.apps.rpg.foundation.state import access as _sections

DEFEAT_HOURS = 8
DEFEAT_HP_SHARE = 0.25
DEFEAT_PURSE_SHARE = 0.20
DEFEAT_ITEM_LOSS_CHANCE = 0.5
BATTERED = "battered"
BATTERED_PENALTY = 2
WOUNDED = "wounded"
WOUNDING_SHARE = 0.4  # a blow taking more than this share of max HP in one go wounds
WOUNDED_PENALTY = 1
WOUND_RESTS = 2


def is_hardcore(simulation_state: dict[str, Any]) -> bool:
    return safe_dict(_sections.campaign_rules_of(simulation_state)).get("hardcore") is True


def campaign_ended(simulation_state: dict[str, Any]) -> dict[str, Any]:
    """How the campaign ended ({} while it goes on)."""
    return safe_dict(_sections.campaign_end_of(simulation_state))


def conditions(actor: dict[str, Any]) -> list[dict[str, Any]]:
    return [safe_dict(condition) for condition in safe_list(safe_dict(actor).get("conditions")) if safe_dict(condition)]


def healing(simulation_state: dict[str, Any], actor_id: str, amount: int) -> int:
    """How much of a heal takes hold: half while wounded."""
    actor = _actor(simulation_state, actor_id)
    if any(condition.get("kind") == WOUNDED for condition in conditions(actor)):
        return max(0, amount) // 2
    return max(0, amount)


def _party(simulation_state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The hero and the companions with them, as stored (read only)."""
    player = safe_dict(_sections.player_state_of(simulation_state))
    members: list[tuple[str, dict[str, Any]]] = [("player", player)]
    for companion in safe_list(safe_dict(_sections.party_state_of(player)).get("companions")):
        if isinstance(companion, dict) and safe_str(companion.get("npc_id")):
            members.append((safe_str(companion.get("npc_id")), companion))
    return members


def _actor(simulation_state: dict[str, Any], actor_id: str) -> dict[str, Any]:
    return next((actor for member_id, actor in _party(simulation_state) if member_id == actor_id), {})


__all__ = [
    "BATTERED",
    "DEFEAT_HOURS",
    "WOUNDED",
    "campaign_ended",
    "conditions",
    "healing",
    "is_hardcore",
]
