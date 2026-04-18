from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.combat.models import AttackIntent, AttackResolution
from app.rpg.combat.rolls import deterministic_d20, deterministic_damage_roll


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _get_actor(simulation_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    for actor in simulation_state.get("actor_states", []) or []:
        if str(actor.get("id") or "") == actor_id:
            return actor
    for npc in simulation_state.get("npc_states", []) or []:
        if str(npc.get("id") or "") == actor_id:
            return npc
    return {}


def _stat(actor: Dict[str, Any], name: str, default: int = 0) -> int:
    stats = _safe_dict(actor.get("stats"))
    return _safe_int(stats.get(name), default)


def _skill(actor: Dict[str, Any], name: str, default: int = 0) -> int:
    skills = _safe_dict(actor.get("skills"))
    return _safe_int(skills.get(name), default)


def _safe_str(value: Any, default: str = "") -> str:
    try:
        return str(value) if value is not None else default
    except Exception:
        return default


def resolve_attack(
    simulation_state: Dict[str, Any],
    combat_state: Dict[str, Any],
    intent: AttackIntent,
    *,
    turn_id: str,
    tick: int,
) -> AttackResolution:
    attacker = _get_actor(simulation_state, intent.actor_id)
    defender = _get_actor(simulation_state, intent.target_id)
    defender_name = str(defender.get("name") or defender.get("id") or intent.target_id or "the target")

    if not attacker or not defender:
        return AttackResolution(
            combat_id=str(combat_state.get("combat_id") or ""),
            actor_id=intent.actor_id,
            target_id=intent.target_id,
            target_name=defender_name,
            action_type=intent.action_type,
            hit=False,
            crit=False,
            attack_total=0,
            defense_total=0,
            damage_total=0,
            damage_type="blunt",
            target_hp_before=0,
            target_hp_after=0,
            target_downed=False,
            rolls=[],
            notes=["invalid_combat_target"],
        )

    attack_roll = deterministic_d20(f"{turn_id}:{tick}:attack:{intent.actor_id}:{intent.target_id}:{intent.action_type}")
    damage_roll = deterministic_damage_roll(f"{turn_id}:{tick}:damage:{intent.actor_id}:{intent.target_id}:{intent.action_type}", 4)

    strength = _stat(attacker, "strength", 0)
    agility = _stat(attacker, "agility", 0)
    endurance = _stat(defender, "endurance", 0)
    brawling = _skill(attacker, "brawling", 0)
    evasion = _skill(defender, "evasion", 0)

    attack_mod = strength + agility + brawling
    defense_mod = agility + endurance + evasion

    attack_total = attack_roll["result"] + attack_mod
    defense_total = 10 + defense_mod

    hit = attack_total >= defense_total
    crit = attack_roll["result"] == 20

    base_damage = strength + max(0, brawling // 2)
    rolled_damage = damage_roll["result"]
    damage_total = 0
    if hit:
        damage_total = max(1, base_damage + rolled_damage - max(0, endurance // 2))
        if crit:
            damage_total += 2

    hp_before = _safe_int(_safe_dict(defender.get("resources")).get("hp"), 1)
    hp_after = max(0, hp_before - damage_total)
    downed = hp_after <= 0

    notes: List[str] = []
    if hit:
        notes.append("attack_hit")
    else:
        notes.append("attack_missed")
    if crit:
        notes.append("critical_hit")
    if downed:
        notes.append("target_downed")

    return AttackResolution(
        combat_id=str(combat_state.get("combat_id") or ""),
        actor_id=intent.actor_id,
        target_id=intent.target_id,
        target_name=defender_name,
        action_type=intent.action_type,
        hit=hit,
        crit=crit,
        attack_total=attack_total,
        defense_total=defense_total,
        damage_total=damage_total,
        damage_type="blunt",
        target_hp_before=hp_before,
        target_hp_after=hp_after,
        target_downed=downed,
        rolls=[attack_roll, damage_roll],
        notes=notes,
    )
