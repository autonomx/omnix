"""Phase 15 — Encounter / tactical mode.

Turn order, initiative, action resolution, combat rules, effects,
non-combat encounters, companion AI, UI bridge, analytics, determinism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

def _sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def _si(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d

def _ss(v: Any, d: str = "") -> str:
    return str(v) if v is not None else d

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PARTICIPANTS = 12
MAX_ROUNDS = 50
MAX_EFFECTS = 20
MAX_ACTION_LOG = 200
ENCOUNTER_MODES = {"combat", "stealth", "investigation", "diplomacy", "chase"}
ENCOUNTER_STATUSES = {"inactive", "active", "resolved", "aborted"}
ACTION_TYPES = {"attack", "defend", "move", "use_item", "ability", "flee",
                "negotiate", "investigate", "hide", "assist"}
EFFECT_TYPES = {"damage", "heal", "buff", "debuff", "status", "move"}


def _normalize_mode(v: Any) -> str:
    value = _ss(v, "combat")
    return value if value in ENCOUNTER_MODES else "combat"


def _normalize_status(v: Any) -> str:
    value = _ss(v, "inactive")
    return value if value in ENCOUNTER_STATUSES else "inactive"


def _normalize_action_type(v: Any) -> str:
    value = _ss(v)
    return value if value in ACTION_TYPES else "defend"


def _normalize_effect_type(v: Any) -> str:
    value = _ss(v)
    return value if value in EFFECT_TYPES else "status"


def _sort_key_effect(eff: "CombatEffect") -> tuple[str, str, int]:
    return (
        _ss(eff.target_id),
        _ss(eff.effect_id),
        _si(eff.remaining),
    )


def _normalize_action_log_item(item: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(item) if isinstance(item, dict) else {}
    effects = item.get("effects") or []
    if not isinstance(effects, list):
        effects = []
    return {
        "action_id": _ss(item.get("action_id")),
        "actor_id": _ss(item.get("actor_id")),
        "action_type": _normalize_action_type(item.get("action_type")),
        "success": bool(item.get("success", False)),
        "effects": [
            {
                "type": _normalize_effect_type(e.get("type")),
                "target": _ss(e.get("target")),
                "value": _sf(e.get("value")),
            }
            for e in effects
            if isinstance(e, dict)
        ],
        "narrative": _ss(item.get("narrative")),
    }


def _derive_active_effects_from_participants(
    participants: List["TacticalParticipant"],
) -> List["CombatEffect"]:
    out: List[CombatEffect] = []
    for participant in participants:
        for eff in participant.effects:
            out.append(CombatEffect.from_dict(eff.to_dict()))
    out = sorted(out, key=_sort_key_effect)
    return out

# ---------------------------------------------------------------------------
# 15.0 — Encounter state foundations
# ---------------------------------------------------------------------------

@dataclass
class CombatEffect:
    effect_id: str = ""
    effect_type: str = ""
    target_id: str = ""
    value: float = 0.0
    duration: int = 1
    remaining: int = 1
    source_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_id": self.effect_id, "effect_type": self.effect_type,
            "target_id": self.target_id, "value": self.value,
            "duration": self.duration, "remaining": self.remaining,
            "source_id": self.source_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CombatEffect":
        return cls(
            effect_id=_ss(d.get("effect_id")),
            effect_type=_normalize_effect_type(d.get("effect_type")),
            target_id=_ss(d.get("target_id")),
            value=_sf(d.get("value")),
            duration=max(0, _si(d.get("duration"), 1)),
            remaining=max(0, _si(d.get("remaining"), 1)),
            source_id=_ss(d.get("source_id")),
        )


@dataclass
class TacticalParticipant:
    entity_id: str = ""
    name: str = ""
    team: str = "neutral"
    hp: float = 100.0
    max_hp: float = 100.0
    initiative: float = 0.0
    status: str = "active"  # active, incapacitated, fled, defeated
    position: int = 0
    effects: List[CombatEffect] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id, "name": self.name,
            "team": self.team, "hp": self.hp, "max_hp": self.max_hp,
            "initiative": self.initiative, "status": self.status,
            "position": self.position,
            "effects": [e.to_dict() for e in self.effects],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TacticalParticipant":
        return cls(
            entity_id=_ss(d.get("entity_id")), name=_ss(d.get("name")),
            team=_ss(d.get("team"), "neutral"),
            hp=_sf(d.get("hp"), 100.0), max_hp=_sf(d.get("max_hp"), 100.0),
            initiative=_sf(d.get("initiative")),
            status=_ss(d.get("status"), "active") if _ss(d.get("status"), "active") in {"active", "incapacitated", "fled", "defeated"} else "active",
            position=_si(d.get("position")),
            effects=[CombatEffect.from_dict(e) for e in (d.get("effects") or [])],
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class TacticalAction:
    action_id: str = ""
    actor_id: str = ""
    action_type: str = ""
    target_id: str = ""
    value: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id, "actor_id": self.actor_id,
            "action_type": self.action_type, "target_id": self.target_id,
            "value": self.value, "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TacticalAction":
        return cls(
            action_id=_ss(d.get("action_id")),
            actor_id=_ss(d.get("actor_id")),
            action_type=_normalize_action_type(d.get("action_type")),
            target_id=_ss(d.get("target_id")),
            value=_sf(d.get("value")),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class EncounterTacticalState:
    encounter_id: str = ""
    mode: str = "combat"
    status: str = "inactive"
    round_number: int = 0
    turn_index: int = 0
    participants: List[TacticalParticipant] = field(default_factory=list)
    turn_order: List[str] = field(default_factory=list)
    action_log: List[Dict[str, Any]] = field(default_factory=list)
    active_effects: List[CombatEffect] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "encounter_id": self.encounter_id, "mode": self.mode,
            "status": self.status, "round_number": self.round_number,
            "turn_index": self.turn_index,
            "participants": [p.to_dict() for p in self.participants],
            "turn_order": list(self.turn_order),
            "action_log": list(self.action_log),
            "active_effects": [e.to_dict() for e in self.active_effects],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EncounterTacticalState":
        return cls(
            encounter_id=_ss(d.get("encounter_id")),
            mode=_normalize_mode(d.get("mode")),
            status=_normalize_status(d.get("status")),
            round_number=_si(d.get("round_number")),
            turn_index=_si(d.get("turn_index")),
            participants=[TacticalParticipant.from_dict(p) for p in (d.get("participants") or [])],
            turn_order=list(d.get("turn_order") or []),
            action_log=[_normalize_action_log_item(v) for v in (d.get("action_log") or []) if isinstance(v, dict)],
            active_effects=[CombatEffect.from_dict(e) for e in (d.get("active_effects") or [])],
        )


# ---------------------------------------------------------------------------
# 15.1 — Turn order / initiative model
# ---------------------------------------------------------------------------

class InitiativeSystem:
    """Deterministic initiative ordering."""

    @staticmethod
    def compute_turn_order(participants: List[TacticalParticipant]) -> List[str]:
        active = [p for p in participants if p.status == "active"]
        active.sort(key=lambda p: (-p.initiative, p.entity_id))
        return [p.entity_id for p in active]

    @staticmethod
    def advance_turn(state: EncounterTacticalState) -> EncounterTacticalState:
        if not state.turn_order:
            return state
        state.turn_index += 1
        if state.turn_index >= len(state.turn_order):
            state.turn_index = 0
            state.round_number += 1
        return state

    @staticmethod
    def get_current_actor(state: EncounterTacticalState) -> Optional[str]:
        if not state.turn_order or state.turn_index >= len(state.turn_order):
            return None
        return state.turn_order[state.turn_index]


# ---------------------------------------------------------------------------
# 15.2 — Action resolution framework
# ---------------------------------------------------------------------------

class ActionResolver:
    """Resolve tactical actions deterministically."""

    @staticmethod
    def resolve_action(
        action: TacticalAction,
        state: EncounterTacticalState,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "action_id": action.action_id,
            "actor_id": action.actor_id,
            "action_type": action.action_type,
            "success": True,
            "effects": [],
            "narrative": "",
        }

        actor = None
        target = None
        for p in state.participants:
            if p.entity_id == action.actor_id:
                actor = p
            if p.entity_id == action.target_id:
                target = p

        if actor is None or actor.status != "active":
            result["success"] = False
            result["narrative"] = "Actor cannot act"
            return result

        if action.action_type == "attack" and target:
            damage = max(0.0, action.value)
            target.hp = max(0.0, target.hp - damage)
            if target.hp <= 0:
                target.status = "defeated"
            result["effects"].append({"type": "damage", "target": action.target_id, "value": damage})
            result["narrative"] = f"{actor.name} attacks {target.name} for {damage} damage"

        elif action.action_type == "heal" and target:
            heal = max(0.0, action.value)
            target.hp = min(target.max_hp, target.hp + heal)
            result["effects"].append({"type": "heal", "target": action.target_id, "value": heal})
            result["narrative"] = f"{actor.name} heals {target.name} for {heal}"

        elif action.action_type == "defend":
            result["effects"].append({"type": "buff", "target": action.actor_id, "value": 0.5})
            result["narrative"] = f"{actor.name} takes a defensive stance"

        elif action.action_type == "flee":
            actor.status = "fled"
            result["narrative"] = f"{actor.name} flees the encounter"

        elif action.action_type == "negotiate" and target:
            result["narrative"] = f"{actor.name} attempts to negotiate with {target.name}"

        elif action.action_type == "investigate":
            result["narrative"] = f"{actor.name} investigates the area"

        elif action.action_type == "hide":
            result["narrative"] = f"{actor.name} attempts to hide"

        else:
            result["narrative"] = f"{actor.name} performs {action.action_type}"

        state.action_log.append(_normalize_action_log_item(result))
        if len(state.action_log) > MAX_ACTION_LOG:
            state.action_log = state.action_log[-MAX_ACTION_LOG:]
        return result


# ---------------------------------------------------------------------------
# 15.3 — Combat rules / effects / statuses
# ---------------------------------------------------------------------------

class EffectManager:
    """Manage active combat effects."""

    _counter = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"eff_{cls._counter}"

    @classmethod
    def apply_effect(cls, target: TacticalParticipant,
                     effect_type: str, value: float,
                     duration: int = 1, source_id: str = "") -> CombatEffect:
        eff = CombatEffect(
            effect_id=cls._next_id(), effect_type=effect_type,
            target_id=target.entity_id, value=value,
            duration=duration, remaining=duration, source_id=source_id,
        )
        target.effects.append(eff)
        if len(target.effects) > MAX_EFFECTS:
            target.effects = target.effects[-MAX_EFFECTS:]
        return eff

    @staticmethod
    def tick_effects(participant: TacticalParticipant) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        remaining: List[CombatEffect] = []
        for eff in participant.effects:
            eff.remaining -= 1
            if eff.effect_type == "damage":
                participant.hp = max(0.0, participant.hp - eff.value)
                results.append({"type": "dot_damage", "value": eff.value})
            elif eff.effect_type == "heal":
                participant.hp = min(participant.max_hp, participant.hp + eff.value)
                results.append({"type": "hot_heal", "value": eff.value})
            if eff.remaining > 0:
                remaining.append(eff)
            else:
                results.append({"type": "effect_expired", "effect_id": eff.effect_id})
        participant.effects = remaining
        if participant.hp <= 0:
            participant.status = "defeated"
        return results

    @staticmethod
    def clear_effects(participant: TacticalParticipant) -> None:
        participant.effects = []


# ---------------------------------------------------------------------------
# 15.4 — Non-combat tactical encounters
# ---------------------------------------------------------------------------

class NonCombatResolver:
    """Resolve non-combat tactical encounters."""

    @staticmethod
    def resolve_stealth_action(actor: TacticalParticipant,
                               difficulty: float = 0.5) -> Dict[str, Any]:
        # Deterministic: compare initiative to difficulty
        success = actor.initiative >= difficulty
        return {
            "action": "stealth",
            "actor_id": actor.entity_id,
            "success": success,
            "narrative": f"{actor.name} {'succeeds' if success else 'fails'} stealth check",
        }

    @staticmethod
    def resolve_investigation(actor: TacticalParticipant,
                              clue_threshold: float = 0.3) -> Dict[str, Any]:
        found = actor.initiative >= clue_threshold
        return {
            "action": "investigate",
            "actor_id": actor.entity_id,
            "clue_found": found,
            "narrative": f"{actor.name} {'finds a clue' if found else 'finds nothing'}",
        }

    @staticmethod
    def resolve_diplomacy(actor: TacticalParticipant,
                          target: TacticalParticipant,
                          relationship_score: float = 0.0) -> Dict[str, Any]:
        # Higher relationship and initiative improve success
        score = actor.initiative * 0.5 + relationship_score * 0.5
        success = score >= 0.4
        return {
            "action": "diplomacy",
            "actor_id": actor.entity_id,
            "target_id": target.entity_id,
            "success": success,
            "narrative": f"{actor.name} {'convinces' if success else 'fails to convince'} {target.name}",
        }


# ---------------------------------------------------------------------------
# 15.5 — Companion tactical AI
# ---------------------------------------------------------------------------

class CompanionTacticalAI:
    """Deterministic companion behavior in encounters."""

    @staticmethod
    def choose_action(
        companion: TacticalParticipant,
        allies: List[TacticalParticipant],
        enemies: List[TacticalParticipant],
        encounter_mode: str = "combat",
    ) -> TacticalAction:
        if encounter_mode == "combat":
            # Heal wounded ally if any
            wounded = [a for a in allies if a.status == "active" and a.hp < a.max_hp * 0.3]
            if wounded:
                target = min(wounded, key=lambda a: a.hp)
                return TacticalAction(
                    actor_id=companion.entity_id, action_type="heal",
                    target_id=target.entity_id, value=20.0,
                )
            # Attack weakest enemy
            active_enemies = [e for e in enemies if e.status == "active"]
            if active_enemies:
                target = min(active_enemies, key=lambda e: e.hp)
                return TacticalAction(
                    actor_id=companion.entity_id, action_type="attack",
                    target_id=target.entity_id, value=15.0,
                )
        elif encounter_mode == "stealth":
            return TacticalAction(
                actor_id=companion.entity_id, action_type="hide",
            )
        elif encounter_mode == "investigation":
            return TacticalAction(
                actor_id=companion.entity_id, action_type="investigate",
            )

        return TacticalAction(
            actor_id=companion.entity_id, action_type="defend",
        )


# ---------------------------------------------------------------------------
# 15.6 — Encounter UI / presentation bridge
# ---------------------------------------------------------------------------

class EncounterPresenter:
    """Format encounter state for UI."""

    @staticmethod
    def present_state(state: EncounterTacticalState) -> Dict[str, Any]:
        return {
            "encounter_id": state.encounter_id,
            "mode": state.mode,
            "status": state.status,
            "round": state.round_number,
            "current_actor": InitiativeSystem.get_current_actor(state),
            "participants": [
                {
                    "id": p.entity_id, "name": p.name, "team": p.team,
                    "hp": p.hp, "max_hp": p.max_hp, "status": p.status,
                    "effect_count": len(p.effects),
                }
                for p in state.participants
            ],
        }

    @staticmethod
    def present_action_log(state: EncounterTacticalState,
                           last_n: int = 5) -> List[Dict[str, Any]]:
        return list(state.action_log[-last_n:])


# ---------------------------------------------------------------------------
# 15.7 — Encounter analytics / replay tools
# ---------------------------------------------------------------------------

class EncounterAnalytics:
    """Analytics for encounter replay and review."""

    @staticmethod
    def compute_statistics(state: EncounterTacticalState) -> Dict[str, Any]:
        teams: Dict[str, int] = {}
        for p in state.participants:
            teams.setdefault(p.team, 0)
            if p.status == "active":
                teams[p.team] += 1
        return {
            "rounds": state.round_number,
            "actions_taken": len(state.action_log),
            "active_by_team": teams,
            "total_participants": len(state.participants),
            "defeated_count": len([p for p in state.participants if p.status == "defeated"]),
            "fled_count": len([p for p in state.participants if p.status == "fled"]),
        }

    @staticmethod
    def get_damage_summary(state: EncounterTacticalState) -> Dict[str, float]:
        damage: Dict[str, float] = {}
        for log in state.action_log:
            for eff in (log.get("effects") or []):
                if eff.get("type") == "damage":
                    actor = log.get("actor_id", "unknown")
                    damage[actor] = damage.get(actor, 0.0) + _sf(eff.get("value"))
        return damage


# ---------------------------------------------------------------------------
# 15.8 — Encounter determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class EncounterDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: EncounterTacticalState,
                             s2: EncounterTacticalState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(state: EncounterTacticalState) -> List[str]:
        violations: List[str] = []
        if len(state.participants) > MAX_PARTICIPANTS:
            violations.append(f"participants exceed max ({len(state.participants)} > {MAX_PARTICIPANTS})")
        if state.round_number > MAX_ROUNDS:
            violations.append(f"rounds exceed max ({state.round_number} > {MAX_ROUNDS})")
        if len(state.action_log) > MAX_ACTION_LOG:
            violations.append(f"action_log exceeds max ({len(state.action_log)} > {MAX_ACTION_LOG})")
        if state.mode not in ENCOUNTER_MODES:
            violations.append(f"invalid encounter mode: {state.mode}")
        if state.status not in ENCOUNTER_STATUSES:
            violations.append(f"invalid encounter status: {state.status}")
        for p in state.participants:
            if p.hp < 0:
                violations.append(f"participant {p.entity_id} hp negative: {p.hp}")
            if len(p.effects) > MAX_EFFECTS:
                violations.append(f"participant {p.entity_id} effects exceed max")
        participant_ids = {p.entity_id for p in state.participants}
        for actor_id in state.turn_order:
            if actor_id not in participant_ids:
                violations.append(f"turn_order references unknown participant: {actor_id}")
        if state.turn_order and (state.turn_index < 0 or state.turn_index >= len(state.turn_order)):
            violations.append(f"turn_index out of range: {state.turn_index}")
        return violations

    @staticmethod
    def normalize_state(state: EncounterTacticalState) -> EncounterTacticalState:
        participants = list(state.participants)
        if len(participants) > MAX_PARTICIPANTS:
            participants = participants[:MAX_PARTICIPANTS]
        for p in participants:
            p.hp = max(0.0, p.hp)
            p.max_hp = max(0.0, p.max_hp)
            p.initiative = _sf(p.initiative)
            if p.status not in {"active", "incapacitated", "fled", "defeated"}:
                p.status = "active"
            if len(p.effects) > MAX_EFFECTS:
                p.effects = p.effects[-MAX_EFFECTS:]
            p.effects = sorted(
                [CombatEffect.from_dict(e.to_dict()) for e in p.effects],
                key=_sort_key_effect,
            )

        turn_order = InitiativeSystem.compute_turn_order(participants)
        turn_index = min(max(0, state.turn_index), max(0, len(turn_order) - 1)) if turn_order else 0
        action_log = [
            _normalize_action_log_item(v)
            for v in list(state.action_log)[-MAX_ACTION_LOG:]
            if isinstance(v, dict)
        ]
        active_effects = _derive_active_effects_from_participants(participants)

        return EncounterTacticalState(
            encounter_id=state.encounter_id,
            mode=_normalize_mode(state.mode),
            status=_normalize_status(state.status),
            round_number=min(max(0, state.round_number), MAX_ROUNDS),
            turn_index=turn_index,
            participants=participants,
            turn_order=turn_order,
            action_log=action_log,
            active_effects=active_effects,
        )
