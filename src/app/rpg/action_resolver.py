"""
Action Resolution Engine for the AI Role-Playing System.

Provides pure game-engine logic for resolving player and NPC actions.
The engine *decides* outcomes (via stat_check); the LLM layer merely *narrates*.

Usage in the pipeline::

    from app.rpg.action_resolver import resolve_action, apply_damage

    outcome = resolve_action(session.player, "attack", difficulty="normal", seed=42)
    if outcome["result"]["success"] and target_npc:
        apply_damage(target_npc, outcome["damage"])
"""

from typing import Any, Dict, Optional

from app.rpg.models import PlayerState, stat_check


# ---------------------------------------------------------------------------
# Damage Helpers
# ---------------------------------------------------------------------------

def apply_damage(target: Any, amount: int) -> int:
    """Apply *amount* damage to *target* (PlayerState or NPC dict).

    Clamps hp at 0.  Returns the actual damage dealt.
    """
    current_hp = getattr(target, "hp", None)
    if current_hp is not None:
        # Dataclass target (e.g. PlayerState)
        actual = min(amount, current_hp)
        target.hp = max(0, current_hp - amount)
        return actual

    # Dict-based NPC
    if isinstance(target, dict) and "hp" in target:
        actual = min(amount, target["hp"])
        target["hp"] = max(0, target["hp"] - amount)
        return actual

    return 0


# ---------------------------------------------------------------------------
# Action Resolution
# ---------------------------------------------------------------------------

# Map action types to the stat + skill they exercise
_ACTION_PROFILES: Dict[str, Dict[str, str]] = {
    "attack": {"stat": "strength", "skill": "swordsmanship"},
    "persuade": {"stat": "charisma", "skill": "persuasion"},
    "sneak": {"stat": "dexterity", "skill": "stealth"},
    "steal": {"stat": "dexterity", "skill": "stealth"},
    "cast_spell": {"stat": "intelligence", "skill": "magic"},
    "use_item": {"stat": "intelligence", "skill": "magic"},
}


def resolve_action(
    player: PlayerState,
    action_type: str,
    difficulty: str = "normal",
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Resolve a player action using the game engine (no LLM).

    Returns a dict with:
      - ``type``    – the action_type echoed back
      - ``result``  – the full stat_check dict
      - ``damage``  – damage dealt (only for attack, else 0)
      - ``stat``    – name of the stat used
      - ``skill``   – name of the skill used
    """
    profile = _ACTION_PROFILES.get(action_type, {"stat": "strength", "skill": "swordsmanship"})

    stat_name = profile["stat"]
    skill_name = profile["skill"]

    stat_value = getattr(player.stats, stat_name, 5)
    skill_value = player.skills.get(skill_name, 0)

    result = stat_check(stat_value, skill_value, difficulty, seed=seed)

    damage = 0
    if action_type == "attack" and result["success"]:
        damage = 5 + player.stats.strength

    return {
        "type": action_type,
        "result": result,
        "damage": damage,
        "stat": stat_name,
        "skill": skill_name,
    }
