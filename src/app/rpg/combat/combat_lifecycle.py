from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class CombatEncounterRule:
    id: str
    encounter_id: str
    trigger_every_turns: int = 0
    required_arc_stage: Tuple[str, str] = ()
    required_faction_tier: Tuple[str, str] = ()
    required_flag: str = ""
    blocked_flag: str = ""
    enemy_id: str = "enemy:road_thug"
    enemy_name: str = "Road Thug"
    enemy_hp: int = 8
    enemy_attack: int = 2
    player_attack: int = 3
    max_rounds: int = 4
    cooldown_turns: int = 20
    world_signal: Dict[str, Any] | None = None


_TIER_RANK = {
    "hostile": -2,
    "suspicious": -1,
    "neutral": 0,
    "friendly": 1,
    "trusted": 2,
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _tier_requirement_met(actual: str, required: str) -> bool:
    actual_rank = _TIER_RANK.get(_safe_str(actual), 0)
    required_rank = _TIER_RANK.get(_safe_str(required), 0)

    if required_rank < 0:
        return actual_rank <= required_rank
    if required_rank > 0:
        return actual_rank >= required_rank
    return actual_rank == required_rank


def _faction_tier(state: Mapping[str, Any], faction_id: str) -> str:
    faction = _safe_dict(_safe_dict(state.get("faction_reputation")).get(faction_id))
    return _safe_str(faction.get("tier") or "neutral")


def _rule_due(
    rule: CombatEncounterRule,
    *,
    state: Mapping[str, Any],
    turn_index: int,
    last_trigger_turn_by_rule: Mapping[str, Any],
) -> bool:
    flags = _safe_dict(state.get("flags"))

    if rule.required_flag and not bool(flags.get(rule.required_flag)):
        return False

    if rule.blocked_flag and bool(flags.get(rule.blocked_flag)):
        return False

    if int(rule.trigger_every_turns or 0) > 0:
        if int(turn_index) % int(rule.trigger_every_turns) != 0:
            return False

    if rule.required_arc_stage:
        arc_id, stage = rule.required_arc_stage
        arc = _safe_dict(_safe_dict(state.get("story_arcs")).get(arc_id))
        if _safe_str(arc.get("current_stage")) != _safe_str(stage):
            return False

    if rule.required_faction_tier:
        faction_id, required_tier = rule.required_faction_tier
        if not _tier_requirement_met(_faction_tier(state, faction_id), required_tier):
            return False

    last_turn = int(_safe_dict(last_trigger_turn_by_rule).get(rule.id) or 0)
    if last_turn and int(turn_index) - last_turn < int(rule.cooldown_turns or 0):
        return False

    return True


def _resolve_encounter(
    *,
    rule: CombatEncounterRule,
    turn_index: int,
    player_state: Mapping[str, Any],
) -> Dict[str, Any]:
    player_hp = int(_safe_dict(player_state).get("hp") or 20)
    enemy_hp = int(rule.enemy_hp)
    rounds: List[Dict[str, Any]] = []

    for round_index in range(1, int(rule.max_rounds) + 1):
        enemy_hp = max(0, enemy_hp - int(rule.player_attack))
        rounds.append(
            {
                "round": round_index,
                "actor": "player",
                "target": rule.enemy_id,
                "damage": int(rule.player_attack),
                "enemy_hp_after": enemy_hp,
            }
        )

        if enemy_hp <= 0:
            break

        player_hp = max(0, player_hp - int(rule.enemy_attack))
        rounds.append(
            {
                "round": round_index,
                "actor": rule.enemy_id,
                "target": "player",
                "damage": int(rule.enemy_attack),
                "player_hp_after": player_hp,
            }
        )

        if player_hp <= 0:
            break

    if player_hp <= 0:
        outcome = "player_defeated"
    elif enemy_hp <= 0:
        outcome = "victory"
    else:
        outcome = "withdraw"

    injury_severity = 0
    if outcome == "player_defeated":
        injury_severity = 3
    elif player_hp <= int(_safe_dict(player_state).get("hp") or 20) - 4:
        injury_severity = 2
    elif player_hp < int(_safe_dict(player_state).get("hp") or 20):
        injury_severity = 1

    return {
        "encounter_id": rule.encounter_id,
        "rule_id": rule.id,
        "turn": int(turn_index),
        "enemy_id": rule.enemy_id,
        "enemy_name": rule.enemy_name,
        "outcome": outcome,
        "rounds": rounds,
        "player_hp_before": int(_safe_dict(player_state).get("hp") or 20),
        "player_hp_after": player_hp,
        "enemy_hp_after": enemy_hp,
        "injury_severity": injury_severity,
    }


def run_combat_lifecycle_tick(
    *,
    combat_state: Mapping[str, Any],
    player_state: Mapping[str, Any],
    world_state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[CombatEncounterRule],
    last_trigger_turn_by_rule: Mapping[str, Any] | None = None,
    max_encounters_per_turn: int = 1,
) -> Dict[str, Any]:
    state = dict(_safe_dict(combat_state))
    player = dict(_safe_dict(player_state))
    last_trigger = {
        str(k): int(v or 0)
        for k, v in _safe_dict(last_trigger_turn_by_rule).items()
    }

    encounters: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    memory_events: List[Dict[str, Any]] = []
    injuries: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}

    for rule in rules:
        if len(encounters) >= int(max_encounters_per_turn):
            break

        if not _rule_due(
            rule,
            state=world_state,
            turn_index=turn_index,
            last_trigger_turn_by_rule=last_trigger,
        ):
            continue

        encounter = _resolve_encounter(
            rule=rule,
            turn_index=turn_index,
            player_state=player,
        )
        encounters.append(encounter)
        last_trigger[rule.id] = int(turn_index)

        player["hp"] = int(encounter.get("player_hp_after") or 0)

        event = {
            "type": "combat_lifecycle",
            "subtype": "combat_resolved",
            "encounter_id": rule.encounter_id,
            "rule_id": rule.id,
            "turn": int(turn_index),
            "enemy_id": rule.enemy_id,
            "enemy_name": rule.enemy_name,
            "outcome": encounter.get("outcome"),
            "injury_severity": encounter.get("injury_severity"),
            "meaningful_progress": True,
            "progress_category": "combat_lifecycle",
            "summary": f"Combat against {rule.enemy_name} resolved as {encounter.get('outcome')}.",
        }
        events.append(event)

        if int(encounter.get("injury_severity") or 0) > 0:
            injury = {
                "type": "combat_consequence",
                "subtype": "injury",
                "encounter_id": rule.encounter_id,
                "turn": int(turn_index),
                "severity": int(encounter.get("injury_severity") or 0),
                "player_hp_after": int(encounter.get("player_hp_after") or 0),
                "recovery_needed": True,
            }
            injuries.append(injury)
            flags["combat_consequence:injury_pending"] = True

        if rule.world_signal:
            signal = dict(rule.world_signal)
            signal.setdefault("kind", "combat_consequence")
            signal.setdefault("turn", int(turn_index))
            signal.setdefault("created_turn", int(turn_index))
            signal.setdefault("ttl_turns", 50)
            signal.setdefault("intensity", max(1, int(encounter.get("injury_severity") or 1)))
            world_signals.append(signal)

        memory_events.append(
            {
                "kind": "npc_memory",
                "type": "combat_consequence",
                "summary": f"Locals remember the {rule.enemy_name} fight ending in {encounter.get('outcome')}.",
                "importance": max(1, int(encounter.get("injury_severity") or 1)),
                "turn": int(turn_index),
                "created_turn": int(turn_index),
            }
        )

    state["active_encounter_count"] = 0
    state["resolved_encounter_count"] = int(state.get("resolved_encounter_count") or 0) + len(encounters)
    state["last_combat_turn"] = int(turn_index) if encounters else state.get("last_combat_turn")

    return {
        "ok": True,
        "combat_state": state,
        "player_state": player,
        "encounters": encounters,
        "events": events,
        "world_signals": world_signals,
        "memory_events": memory_events,
        "injuries": injuries,
        "flags": flags,
        "last_trigger_turn_by_rule": last_trigger,
        "encounter_count": len(encounters),
        "event_count": len(events),
        "injury_count": len(injuries),
    }