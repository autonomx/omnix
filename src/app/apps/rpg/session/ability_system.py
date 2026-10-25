"""Compatibility facade for RPG ability tree and effect helpers.

The implementation is split across focused modules so every RPG source file stays
below the architecture line-limit gate.
"""
from __future__ import annotations

from app.apps.rpg.session.ability_models import ALLOWED_DIMENSIONS, DEFAULT_SKILL_XP_PER_ABILITY_USE
from app.apps.rpg.session.ability_runtime import (
    apply_ability_to_state,
    assign_ability_to_hotbar,
    grant_player_xp,
    grant_skill_xp,
    remove_hotbar_slot,
    skill_modifier_for_check,
    tick_ability_state,
    unlock_ability_in_state,
    upgrade_ability_rank_in_state,
)
from app.apps.rpg.session.ability_tree import build_ability_tree, build_progression_package, validate_ability_tree

__all__ = [
    "ALLOWED_DIMENSIONS",
    "DEFAULT_SKILL_XP_PER_ABILITY_USE",
    "apply_ability_to_state",
    "assign_ability_to_hotbar",
    "build_ability_tree",
    "build_progression_package",
    "grant_player_xp",
    "grant_skill_xp",
    "remove_hotbar_slot",
    "skill_modifier_for_check",
    "tick_ability_state",
    "unlock_ability_in_state",
    "upgrade_ability_rank_in_state",
    "validate_ability_tree",
]
