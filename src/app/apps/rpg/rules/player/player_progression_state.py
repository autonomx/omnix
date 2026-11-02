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


# The skills a hero of each kind of world starts with (the playtest: a hero of Aurelia, a high-fantasy world, had
# firearms and hacking); a world of no kind named here keeps them all.
_GENRE_SKILLS = {
    "fantasy": ("swordsmanship", "archery", "defense", "stealth", "persuasion", "intimidation", "investigation",
                "magic"),
    "future": ("swordsmanship", "firearms", "defense", "stealth", "persuasion", "intimidation", "investigation",
               "hacking"),
}
_GENRE_WORDS = {"fantasy": ("fantasy", "isekai", "myth", "medieval", "sword", "sorcery"),
                "future": ("cyber", "sci", "future", "space", "tech", "punk")}


def genre_kind(genre: str) -> str:
    """The kind of world ``genre`` names ("fantasy" for "fantasy_isekai", "future" for "cyberpunk"); "" for none."""
    lowered = str(genre or "").casefold()
    if "steam" in lowered:  # neither a world to come nor a sword's: its own
        return ""
    return next((kind for kind, words in _GENRE_WORDS.items() if any(word in lowered for word in words)), "")


# The default kit's things as a hero of a world to come carries them (the playtest: a cyberpunk hero of Vesper-9 set
# out with a travel cloak and an iron dagger); each fights or wears as the kind its name ends in.
_FUTURE_GEAR = {
    "travel_cloak": {"id": "rain_cloak", "name": "Rain Cloak"},
    "iron_dagger": {"id": "utility_knife", "name": "Utility Knife"},
    "trail_rations": {"id": "ration_bars", "name": "Ration Bars"},
    "torch": {"id": "flashlight", "name": "Flashlight"},
}


def gear_of_kind(kind: str, inventory: list[dict[str, Any]], equipment: list[dict[str, Any]]
                 ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The default kit as a world of ``kind`` ("future", "fantasy") has it; gear the player chose is theirs."""
    if kind != "future":
        return inventory, equipment
    names = {_s_name(item.get("name")): _FUTURE_GEAR[str(item.get("id"))]["name"] for item in inventory
             if str(item.get("id")) in _FUTURE_GEAR}
    inventory = [{**item, **_FUTURE_GEAR.get(str(item.get("id")), {})} for item in inventory]
    equipment = [{**row, "name": names.get(_s_name(row.get("name")), row.get("name"))} for row in equipment]
    return inventory, equipment


def _s_name(value: Any) -> str:
    return str(value or "").casefold()


def skills_for_genre(genre: str) -> Dict[str, Any] | None:
    """The starting skills for a world of ``genre`` ("fantasy_isekai", "cyberpunk"); None when it names no kind."""
    kind = genre_kind(genre)
    if not kind:
        return None
    return {name: {"level": 0, "xp": 0, "xp_to_next": 25} for name in _GENRE_SKILLS[kind]}


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
