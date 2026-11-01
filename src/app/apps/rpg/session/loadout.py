"""The play screen's loadout request (``POST /api/rpg/sessions/{id}/loadout-action``).

Each action is a turn through the turn pipeline (RQ-2.4): a pack action is the item rule's (use, equip, take off,
drop), an ability used is the ability rule's (in a fight or not), one learned is a level's choice (progression.md),
and a hotbar slot is set or cleared by the ability rule. The route maps them (``rpg_session_routes._loadout_turn``).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

LoadoutActionKind = Literal[
    "use",
    "equip",
    "unequip",
    "drop",
    "use_ability",
    "hotbar",
    "unlock_ability",
    "assign_hotbar",
    "remove_hotbar",
]


class RpgLoadoutActionRequest(BaseModel):
    action: LoadoutActionKind
    item_name: str | None = None
    ability_id: str | None = None
    ability_name: str | None = None
    hotbar_slot: str | int | None = None
    target: str | None = None


__all__ = ["LoadoutActionKind", "RpgLoadoutActionRequest"]
