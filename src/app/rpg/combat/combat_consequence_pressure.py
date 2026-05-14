from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def apply_combat_consequence_pressure(
    *,
    player_state: Mapping[str, Any],
    pending_injuries: List[Dict[str, Any]],
    turn_index: int,
) -> Dict[str, Any]:
    player = dict(_safe_dict(player_state))
    injuries = [_safe_dict(row) for row in _safe_list(pending_injuries)]

    events: List[Dict[str, Any]] = []
    economy_pressure_hints: List[Dict[str, Any]] = []

    unresolved = []
    for injury in injuries:
        if bool(injury.get("resolved")):
            continue

        severity = int(injury.get("severity") or 0)
        if severity <= 0:
            continue

        treatment_cost = max(1, severity)

        events.append(
            {
                "type": "combat_consequence",
                "subtype": "recovery_pressure",
                "turn": int(turn_index),
                "encounter_id": injury.get("encounter_id"),
                "severity": severity,
                "treatment_cost_gold": treatment_cost,
                "summary": "Combat injuries create recovery pressure.",
                "meaningful_progress": False,
                "progress_category": "combat_consequence",
            }
        )

        economy_pressure_hints.append(
            {
                "type": "economy_pressure_hint",
                "subtype": "injury_treatment_cost",
                "turn": int(turn_index),
                "currency": "gold",
                "amount": treatment_cost,
                "source": "combat_consequence",
            }
        )

        updated = dict(injury)
        updated["pressure_emitted_turn"] = int(turn_index)
        updated["resolved"] = True
        unresolved.append(updated)

    return {
        "ok": True,
        "player_state": player,
        "events": events,
        "economy_pressure_hints": economy_pressure_hints,
        "pending_injuries": unresolved,
        "event_count": len(events),
    }