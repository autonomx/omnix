from __future__ import annotations

import hashlib
from typing import Any, Dict, List
from app.apps.rpg.foundation.state import access as _sections


SOURCE = "deterministic_combat_runtime"


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def deterministic_roll(seed: str, low: int, high: int) -> int:
    low = int(low)
    high = max(low, int(high))
    span = high - low + 1
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return low + (int(digest[:16], 16) % span)


def get_combat_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(_sections.combat_state_of(simulation_state))


def current_actor_id(combat_state: Dict[str, Any]) -> str:
    order = safe_list(combat_state.get("initiative_order"))
    if not order:
        return ""
    idx = safe_int(combat_state.get("turn_index"), 0) % len(order)
    return safe_str(safe_dict(order[idx]).get("actor_id"))


def participant(combat_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    return safe_dict(safe_dict(combat_state.get("participants")).get(actor_id))


def living_actor_ids(combat_state: Dict[str, Any], side: str) -> List[str]:
    ids: List[str] = []
    for actor_id, row in safe_dict(combat_state.get("participants")).items():
        row = safe_dict(row)
        if (
            safe_str(row.get("side")) == side
            and safe_str(row.get("status") or "active") == "active"
            and safe_int(row.get("hp"), 0) > 0
        ):
            ids.append(safe_str(actor_id))
    return ids


def living_enemy_ids(combat_state: Dict[str, Any]) -> List[str]:
    return living_actor_ids(combat_state, "enemy")


def living_party_ids(combat_state: Dict[str, Any]) -> List[str]:
    return living_actor_ids(combat_state, "party")


def default_target_for_actor(combat_state: Dict[str, Any], actor_id: str) -> str:
    actor = participant(combat_state, actor_id)
    if safe_str(actor.get("side")) == "enemy":
        party = living_party_ids(combat_state)
        return party[0] if party else ""
    enemies = living_enemy_ids(combat_state)
    return enemies[0] if enemies else ""


def combat_seed(combat_state: Dict[str, Any], *parts: Any) -> str:
    return "|".join(
        [
            safe_str(combat_state.get("encounter_id")),
            str(safe_int(combat_state.get("round"), 1)),
            str(safe_int(combat_state.get("turn_index"), 0)),
            *[safe_str(part) for part in parts],
        ]
    )


def build_initiative_order(
    *,
    encounter_id: str,
    participants: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows = []
    for actor_id, row in safe_dict(participants).items():
        row = safe_dict(row)
        if safe_str(row.get("status") or "active") != "active":
            continue

        roll = deterministic_roll(f"{encounter_id}|initiative|{actor_id}", 1, 20)
        bonus = safe_int(row.get("initiative_bonus"), 0)
        rows.append({
            "actor_id": actor_id,
            "initiative": roll + bonus,
            "roll": roll,
            "bonus": bonus,
        })

    rows.sort(key=lambda row: (-safe_int(row.get("initiative")), safe_str(row.get("actor_id"))))
    return rows
