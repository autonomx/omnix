from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.combat.state import normalize_combat_state


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _actor_lookup(simulation_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    for collection_key in ("actor_states", "npc_states"):
        for actor in _safe_list(simulation_state.get(collection_key)):
            if str(actor.get("id") or "") == actor_id:
                return actor
    return {}


def _is_downed(actor: Dict[str, Any]) -> bool:
    resources = _safe_dict(actor.get("resources"))
    hp = int(resources.get("hp", 0) or 0)
    statuses = [str(x).strip().lower() for x in _safe_list(actor.get("status_effects"))]
    return hp <= 0 or "downed" in statuses


def _actor_team(actor: Dict[str, Any]) -> str:
    return str(actor.get("combat_team") or actor.get("team") or actor.get("faction") or "neutral")


def build_combat_participants(simulation_state: Dict[str, Any], actor_ids: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for actor_id in actor_ids:
        actor_id = str(actor_id or "").strip()
        if not actor_id or actor_id in seen:
            continue
        if _actor_lookup(simulation_state, actor_id):
            seen.add(actor_id)
            out.append(actor_id)
    return out


def evaluate_combat_exit(simulation_state: Dict[str, Any], combat_state: Dict[str, Any]) -> Dict[str, Any]:
    state = normalize_combat_state(combat_state)
    if not state.get("active"):
        return state

    participants = [str(x) for x in state.get("participants") or [] if str(x or "").strip()]
    alive_by_team: Dict[str, List[str]] = {}
    downed_ids: List[str] = []

    for actor_id in participants:
        actor = _actor_lookup(simulation_state, actor_id)
        if not actor:
            continue
        if _is_downed(actor):
            downed_ids.append(actor_id)
            continue
        team = _actor_team(actor)
        alive_by_team.setdefault(team, []).append(actor_id)

    if len(alive_by_team) <= 1:
        state["active"] = False
        state["phase"] = "resolved"
        alive_teams = list(alive_by_team.keys())
        winners = alive_by_team.get(alive_teams[0], []) if alive_teams else []
        losers = [actor_id for actor_id in participants if actor_id not in winners]
        state["winner_ids"] = winners
        state["loser_ids"] = losers
        state["exit_reason"] = "last_team_standing" if winners else "all_downed"
        state["pending_npc_turn"] = False

    return state
