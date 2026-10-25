"""Phase 18.3A — Canonical player progression state."""
from __future__ import annotations

from typing import Any, Dict

_MAX_PROGRESSION_LOG = 50


def _normalize_xp_meter(progress: Dict[str, Any]) -> None:
    """The xp meter as a number, on ``ensure_player_progression_state``'s own copy."""
    xp = progress.get("xp")
    if not isinstance(xp, dict):
        return

    current = xp.get("current", 0)
    maximum = xp.get("max", 100)
    try:
        progress["xp"] = max(0, int(current))
    except (TypeError, ValueError):
        progress["xp"] = 0
    if "xp_to_next" not in progress:
        try:
            progress["xp_to_next"] = max(1, int(maximum))
        except (TypeError, ValueError):
            progress["xp_to_next"] = 100


def ensure_player_progression_state(player_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure player_state has canonical progression fields (on a copy). Idempotent."""
    progress = dict(player_state or {})  # a fresh copy: the hero given is only read
    _normalize_xp_meter(progress)
    progress.setdefault("name", "Player")
    progress.setdefault("class_id", "")
    progress.setdefault("background_id", "")
    progress.setdefault("species_id", "")
    progress.setdefault("level", 1)
    progress.setdefault("xp", 0)
    progress.setdefault("xp_to_next", 100)
    progress.setdefault("unspent_points", 0)
    progress.setdefault("unspent_skill_points", 0)
    progress.setdefault("combat_rating", 0)
    progress.setdefault("stats", {
        "strength": 5, "dexterity": 5, "constitution": 5,
        "intelligence": 5, "wisdom": 5, "charisma": 5,
    })
    progress.setdefault("skills", {
        "swordsmanship": {"level": 0, "xp": 0, "xp_to_next": 25},
        "archery": {"level": 0, "xp": 0, "xp_to_next": 25},
        "firearms": {"level": 0, "xp": 0, "xp_to_next": 25},
        "defense": {"level": 0, "xp": 0, "xp_to_next": 25},
        "stealth": {"level": 0, "xp": 0, "xp_to_next": 25},
        "persuasion": {"level": 0, "xp": 0, "xp_to_next": 25},
        "intimidation": {"level": 0, "xp": 0, "xp_to_next": 25},
        "investigation": {"level": 0, "xp": 0, "xp_to_next": 25},
        "magic": {"level": 0, "xp": 0, "xp_to_next": 25},
        "hacking": {"level": 0, "xp": 0, "xp_to_next": 25},
    })
    progress.setdefault("perk_flags", [])
    progress.setdefault("progression_log", [])
    # Trim progression_log
    if len(progress["progression_log"]) > _MAX_PROGRESSION_LOG:
        progress["progression_log"] = progress["progression_log"][-_MAX_PROGRESSION_LOG:]
    return progress
