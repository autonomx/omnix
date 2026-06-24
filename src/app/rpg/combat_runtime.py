"""Runtime combat lifecycle expansion adapters for RPG Phase 21."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from app.rpg.combat_lifecycle import (
    CombatAction,
    CombatState,
    Combatant,
    award_xp,
    combat_report_payload,
    loot_allowed,
    resolve_attack,
)

COMBAT_RUNTIME_SOURCE = "phase21_combat_runtime_v1"
ExpandedDefeatOutcome = Literal[
    "defeated",
    "unconscious",
    "captured",
    "robbed",
    "rescued",
    "retreated",
    "surrendered",
    "reputation_loss",
]
_ALLOWED_XP_SOURCES = ("kill", "quest", "milestone")


def build_combat_runtime_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Resolve/report one deterministic combat action and expanded outcomes."""

    state = _combat_state(_mapping(turn_result.get("combat_state") or turn_result.get("simulation_state")))
    action = _combat_action(turn_result)
    resolution = resolve_attack(state, action) if action else None
    active_state = resolution.state if resolution else state
    outcome = _expanded_outcome(turn_result, resolution.defeat_outcome if resolution else None)
    xp_source = str(turn_result.get("xp_source") or "kill")
    xp_amount = int(turn_result.get("xp_amount") or 0)
    xp_award = award_xp(xp_source, xp_amount) if xp_source in _ALLOWED_XP_SOURCES else 0
    skill = _skill_progress(turn_result)
    issues = tuple(_combat_issues(resolution, outcome, xp_source))
    return {
        "source": COMBAT_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "resolution": _resolution_payload(resolution),
        "expanded_defeat_outcome": outcome,
        "loot_allowed": bool(resolution and loot_allowed(resolution) and outcome == "defeated"),
        "xp": {"source": xp_source, "amount": xp_award, "allowed": xp_source in _ALLOWED_XP_SOURCES},
        "skill_progress": skill,
        "combat": combat_report_payload(active_state),
    }


def _combat_state(raw: Mapping[str, object]) -> CombatState:
    combat = _mapping(raw.get("combat") or raw)
    combatants = tuple(
        _combatant(item) for item in _sequence(combat.get("combatants")) if isinstance(item, Mapping)
    )
    return CombatState(
        encounter_id=str(combat.get("encounter_id") or "runtime-combat"),
        combatants=combatants,
        round_number=int(combat.get("round_number") or 1),
        turn_index=int(combat.get("turn_index") or 0),
        active=bool(combat.get("active", True)),
    )


def _combatant(raw: Mapping[str, object]) -> Combatant:
    return Combatant(
        combatant_id=str(raw.get("combatant_id") or raw.get("id") or "combatant"),
        side=str(raw.get("side") or "enemy"),  # type: ignore[arg-type]
        initiative=int(raw.get("initiative") or 0),
        hp=int(raw.get("hp") or 0),
        max_hp=int(raw.get("max_hp") or raw.get("hp") or 1),
        policy=raw.get("policy"),  # type: ignore[arg-type]
    )


def _combat_action(turn_result: Mapping[str, object]) -> CombatAction | None:
    raw = _mapping(turn_result.get("combat_action"))
    actor = raw.get("actor_id") or turn_result.get("actor_id")
    target = raw.get("target_id") or turn_result.get("target_id")
    if not actor or not target:
        return None
    return CombatAction(
        actor_id=str(actor),
        target_id=str(target),
        damage=int(raw.get("damage") or turn_result.get("damage") or 0),
        source=str(raw.get("source") or turn_result.get("source") or "attack"),
    )


def _expanded_outcome(turn_result: Mapping[str, object], core_outcome: object) -> ExpandedDefeatOutcome | None:
    requested = str(turn_result.get("defeat_outcome") or "")
    allowed = {
        "defeated",
        "unconscious",
        "captured",
        "robbed",
        "rescued",
        "retreated",
        "surrendered",
        "reputation_loss",
    }
    if requested in allowed:
        return requested  # type: ignore[return-value]
    return core_outcome if core_outcome in allowed else None


def _skill_progress(turn_result: Mapping[str, object]) -> dict[str, object]:
    raw = _mapping(turn_result.get("skill_use"))
    if not raw:
        return {"skill_id": None, "delta": 0, "source": None}
    delta = max(0, int(raw.get("delta") or 1))
    return {
        "skill_id": str(raw.get("skill_id") or raw.get("skill") or "unknown"),
        "delta": delta,
        "source": str(raw.get("source") or "usage"),
    }


def _combat_issues(resolution: object, outcome: object, xp_source: str) -> tuple[str, ...]:
    issues: list[str] = []
    if resolution is None:
        issues.append("missing_combat_action")
    elif getattr(resolution, "ok", False) is not True:
        issues.append(f"combat_failed:{getattr(resolution, 'reason', 'unknown')}")
    if xp_source not in _ALLOWED_XP_SOURCES:
        issues.append(f"xp_source_not_allowed:{xp_source}")
    if outcome in ("robbed", "rescued", "reputation_loss"):
        issues.append(f"non_loot_outcome:{outcome}")
    return tuple(issues)


def _resolution_payload(resolution: object) -> dict[str, object]:
    if resolution is None:
        return {"ok": False, "reason": "missing_combat_action"}
    return {
        "ok": bool(getattr(resolution, "ok", False)),
        "reason": str(getattr(resolution, "reason", "unknown")),
        "narration_facts": list(getattr(resolution, "narration_facts", ())),
        "defeat_outcome": getattr(resolution, "defeat_outcome", None),
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
