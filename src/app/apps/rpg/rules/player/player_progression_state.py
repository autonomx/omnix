"""Phase 18.3A — Canonical player progression state."""
from __future__ import annotations

from typing import Any, Dict

_MAX_PROGRESSION_LOG = 50


def _normalize_xp_meter(player_state: Dict[str, Any]) -> None:
    xp = player_state.get("xp")
    if not isinstance(xp, dict):
        return

    current = xp.get("current", 0)
    maximum = xp.get("max", 100)
    try:
        player_state["xp"] = max(0, int(current))
    except (TypeError, ValueError):
        player_state["xp"] = 0
    if "xp_to_next" not in player_state:
        try:
            player_state["xp_to_next"] = max(1, int(maximum))
        except (TypeError, ValueError):
            player_state["xp_to_next"] = 100


def ensure_player_progression_state(player_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure player_state has canonical progression fields. Idempotent."""
    player_state = dict(player_state or {})
    _normalize_xp_meter(player_state)
    player_state.setdefault("name", "Player")
    player_state.setdefault("class_id", "")
    player_state.setdefault("background_id", "")
    player_state.setdefault("species_id", "")
    player_state.setdefault("level", 1)
    player_state.setdefault("xp", 0)
    player_state.setdefault("xp_to_next", 100)
    player_state.setdefault("unspent_points", 0)
    player_state.setdefault("unspent_skill_points", 0)
    player_state.setdefault("combat_rating", 0)
    player_state.setdefault("stats", {
        "strength": 5, "dexterity": 5, "constitution": 5,
        "intelligence": 5, "wisdom": 5, "charisma": 5,
    })
    player_state.setdefault("skills", {
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
    player_state.setdefault("perk_flags", [])
    player_state.setdefault("progression_log", [])
    # Trim progression_log
    if len(player_state["progression_log"]) > _MAX_PROGRESSION_LOG:
        player_state["progression_log"] = player_state["progression_log"][-_MAX_PROGRESSION_LOG:]
    return player_state
