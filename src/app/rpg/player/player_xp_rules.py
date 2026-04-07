"""Phase 18.3A — XP computation rules.

Deterministic formulas for awarding XP from combat, quests, discoveries, and diplomacy.
AI may assign difficulty_tier, quest_rank etc. but formulas are deterministic.
"""
from __future__ import annotations

from typing import Any, Dict


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def compute_enemy_difficulty_xp(enemy_state: Dict[str, Any]) -> int:
    """Compute XP from defeating an enemy based on difficulty_tier."""
    enemy = dict(enemy_state or {})
    tier = _safe_int(enemy.get("difficulty_tier"), 1)
    return 20 + tier * 15


def compute_quest_xp(quest_state: Dict[str, Any]) -> int:
    """Compute XP from quest completion based on quest_rank."""
    quest = dict(quest_state or {})
    rank = _safe_int(quest.get("quest_rank") or quest.get("rank"), 1)
    return 50 + rank * 25


def compute_action_skill_xp(action_result: Dict[str, Any]) -> Dict[str, int]:
    """Compute skill XP from an action result. Returns {skill_id: amount}."""
    result = dict(action_result or {})
    skill_id = _safe_str(result.get("skill_id"))
    if not skill_id:
        return {}
    outcome = _safe_str(result.get("outcome"))
    difficulty = _safe_str(result.get("difficulty", "normal"))

    difficulty_bonus = {"trivial": 0, "easy": 0, "normal": 1, "hard": 2, "very_hard": 3, "legendary": 5}.get(difficulty, 1)
    success_bonus = {"success": 2, "critical_success": 4, "hit": 2, "crit": 4, "partial": 1, "graze": 1}.get(outcome, 0)

    amount = 2 + difficulty_bonus + success_bonus
    return {skill_id: amount}


def compute_stat_influence_bonus(player_state: Dict[str, Any], action_result: Dict[str, Any]) -> int:
    """Compute bonus XP based on stat influence on action."""
    player = dict(player_state or {})
    result = dict(action_result or {})
    stat_used = _safe_str(result.get("stat_used"))
    if not stat_used:
        return 0
    stats = dict(player.get("stats") or {})
    stat_val = _safe_int(stats.get(stat_used), 5)
    mod = max(0, (stat_val - 10) // 2)
    return mod
