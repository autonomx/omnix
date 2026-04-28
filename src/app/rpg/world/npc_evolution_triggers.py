from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.world.npc_biography_registry import get_npc_biography
from app.rpg.world.npc_evolution_state import apply_npc_evolution_event
from app.rpg.world.npc_reputation_state import get_npc_reputation


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def evolve_npcs_from_world_event(
    simulation_state: Dict[str, Any],
    *,
    world_event: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    event = _safe_dict(world_event)
    event_id = _safe_str(event.get("event_id") or event.get("id"))
    kind = _safe_str(event.get("kind"))
    location_id = _safe_str(event.get("location_id"))
    affected_npcs = [
        _safe_str(npc_id)
        for npc_id in _safe_list(event.get("affected_npcs"))
        if _safe_str(npc_id).startswith("npc:")
    ]

    results: List[Dict[str, Any]] = []

    if kind == "location_destroyed":
        for npc_id in affected_npcs:
            bio = get_npc_biography(npc_id)
            home = _safe_str(bio.get("home_location_id"))
            work = _safe_str(bio.get("work_location_id"))
            role = _safe_str(bio.get("role") or bio.get("starting_role")).lower()

            if location_id and location_id not in {home, work}:
                continue

            if "tavern" in role:
                result = apply_npc_evolution_event(
                    simulation_state,
                    npc_id=npc_id,
                    event_id=event_id,
                    kind="home_or_work_destroyed",
                    current_role="Displaced tavern keeper",
                    identity_arc="revenge_after_losing_tavern",
                    personality_modifier={
                        "trait": "vengeful",
                        "strength": 2,
                        "reason": _safe_str(event.get("summary")) or "His tavern was destroyed.",
                    },
                    motivation={
                        "kind": "revenge",
                        "summary": "Find the bandits who destroyed his tavern.",
                        "strength": 4,
                    },
                    party_join_eligibility={
                        "eligible": True,
                        "reason": "lost_home_and_has_revenge_motivation",
                        "requires_player_trust": 1,
                    },
                    tick=tick,
                )
                results.append(result)

    return {
        "applied": any(result.get("applied") for result in results),
        "results": results,
        "source": "deterministic_npc_evolution_trigger_runtime",
    }


def evolve_npc_from_reputation_thresholds(
    simulation_state: Dict[str, Any],
    *,
    npc_id: str,
    tick: int,
) -> Dict[str, Any]:
    npc_id = _safe_str(npc_id)
    if not npc_id.startswith("npc:"):
        return {"applied": False, "reason": "invalid_npc_id"}

    rep = get_npc_reputation(simulation_state, npc_id=npc_id)
    trust = int(rep.get("trust") or 0)
    annoyance = int(rep.get("annoyance") or 0)

    if trust >= 4:
        return apply_npc_evolution_event(
            simulation_state,
            npc_id=npc_id,
            event_id=f"reputation:trust:{npc_id}:4",
            kind="trust_threshold",
            personality_modifier={
                "trait": "loyal_to_player",
                "strength": 1,
                "reason": "The player has repeatedly earned trust.",
            },
            motivation={
                "kind": "support_player",
                "summary": "Help the player when it does not violate core values.",
                "strength": 2,
            },
            tick=tick,
        )

    if annoyance >= 4:
        return apply_npc_evolution_event(
            simulation_state,
            npc_id=npc_id,
            event_id=f"reputation:annoyance:{npc_id}:4",
            kind="annoyance_threshold",
            personality_modifier={
                "trait": "guarded_against_player",
                "strength": 1,
                "reason": "The player has repeatedly irritated or pressured this NPC.",
            },
            motivation={
                "kind": "avoid_player_pressure",
                "summary": "Limit what is shared with the player.",
                "strength": 2,
            },
            tick=tick,
        )

    return {
        "applied": False,
        "reason": "no_reputation_threshold_crossed",
        "source": "deterministic_npc_evolution_trigger_runtime",
    }
