"""Deterministic combat lifecycle helpers for RPG encounters."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

CombatantSide = Literal["player", "party", "enemy", "neutral"]
EnemyPolicy = Literal["attack_weakest", "hold_position", "flee_when_hurt", "surrender_when_hurt"]
DefeatOutcome = Literal["defeated", "unconscious", "captured", "retreated", "surrendered"]
XpSource = Literal["kill", "quest", "milestone"]


@dataclass(frozen=True)
class Combatant:
    combatant_id: str
    side: CombatantSide
    initiative: int
    hp: int
    max_hp: int
    policy: EnemyPolicy | None = None

    @property
    def active(self) -> bool:
        return self.hp > 0

    def with_damage(self, amount: int) -> "Combatant":
        return replace(self, hp=max(0, self.hp - max(0, amount)))


@dataclass(frozen=True)
class CombatState:
    encounter_id: str
    combatants: tuple[Combatant, ...]
    round_number: int = 1
    turn_index: int = 0
    active: bool = True

    def initiative_order(self) -> tuple[Combatant, ...]:
        return tuple(sorted((c for c in self.combatants if c.active), key=lambda c: (-c.initiative, c.combatant_id)))

    def current_combatant(self) -> Combatant | None:
        order = self.initiative_order()
        if not order:
            return None
        return order[self.turn_index % len(order)]

    def with_combatant(self, combatant: Combatant) -> "CombatState":
        return replace(self, combatants=tuple(combatant if c.combatant_id == combatant.combatant_id else c for c in self.combatants))

    def advance_turn(self) -> "CombatState":
        order = self.initiative_order()
        if not order:
            return replace(self, active=False)
        next_index = self.turn_index + 1
        next_round = self.round_number + (1 if next_index >= len(order) else 0)
        return replace(self, turn_index=next_index % len(order), round_number=next_round)


@dataclass(frozen=True)
class CombatAction:
    actor_id: str
    target_id: str
    damage: int
    source: str = "attack"


@dataclass(frozen=True)
class CombatResolution:
    ok: bool
    reason: str
    state: CombatState
    narration_facts: tuple[str, ...]
    defeat_outcome: DefeatOutcome | None = None


def resolve_attack(state: CombatState, action: CombatAction) -> CombatResolution:
    actor = _find(state, action.actor_id)
    target = _find(state, action.target_id)
    if not state.active:
        return CombatResolution(False, "combat_inactive", state, ())
    if actor is None or target is None:
        return CombatResolution(False, "combatant_unknown", state, ())
    if not actor.active:
        return CombatResolution(False, "actor_inactive", state, ())
    if not target.active:
        return CombatResolution(False, "target_inactive", state, ())

    damaged = target.with_damage(action.damage)
    updated = state.with_combatant(damaged)
    facts = (f"{actor.combatant_id} used {action.source} on {target.combatant_id} for {max(0, action.damage)} damage.",)
    if not damaged.active:
        return CombatResolution(True, "target_defeated", updated, facts + (f"{target.combatant_id} reached 0 HP.",), "defeated")
    return CombatResolution(True, "hit", updated, facts)


def choose_enemy_action(state: CombatState, enemy_id: str) -> CombatAction | None:
    enemy = _find(state, enemy_id)
    if enemy is None or not enemy.active or enemy.side != "enemy":
        return None
    opponents = [c for c in state.combatants if c.side in ("player", "party") and c.active]
    if not opponents:
        return None
    if enemy.policy in ("flee_when_hurt", "surrender_when_hurt") and enemy.hp * 2 <= enemy.max_hp:
        return None
    target = sorted(opponents, key=lambda c: (c.hp, c.combatant_id))[0]
    return CombatAction(enemy.combatant_id, target.combatant_id, 1, "enemy_policy")


def award_xp(source: XpSource, amount: int) -> int:
    if source not in ("kill", "quest", "milestone"):
        raise ValueError("unsupported XP source")
    return max(0, amount)


def loot_allowed(resolution: CombatResolution) -> bool:
    return resolution.ok and resolution.defeat_outcome == "defeated"


def _find(state: CombatState, combatant_id: str) -> Combatant | None:
    return next((combatant for combatant in state.combatants if combatant.combatant_id == combatant_id), None)


def combat_report_payload(state: CombatState) -> dict[str, object]:
    current = state.current_combatant()
    return {
        "encounter_id": state.encounter_id,
        "active": state.active,
        "round_number": state.round_number,
        "turn_index": state.turn_index,
        "current_combatant_id": current.combatant_id if current else None,
        "initiative_order": [combatant.combatant_id for combatant in state.initiative_order()],
    }
