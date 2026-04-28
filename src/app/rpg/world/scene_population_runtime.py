from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.world.location_registry import current_location_id
from app.rpg.world.npc_biography_registry import get_npc_biography
from app.rpg.world.npc_presence_runtime import (
    present_npcs_at_location,
    update_present_npcs_for_location,
)
from app.rpg.world.npc_schedule_state import active_schedule_for_npc


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_scene_population_state(
    simulation_state: Dict[str, Any],
    *,
    location_id: str = "",
    tick: int,
) -> Dict[str, Any]:
    location_id = _safe_str(location_id or current_location_id(simulation_state))
    update_present_npcs_for_location(simulation_state, location_id=location_id, tick=tick)

    present: List[Dict[str, Any]] = []
    for npc_id in present_npcs_at_location(simulation_state, location_id=location_id):
        bio = get_npc_biography(npc_id)
        schedule = active_schedule_for_npc(simulation_state, npc_id=npc_id, tick=tick)
        present.append(
            {
                "npc_id": npc_id,
                "name": _safe_str(bio.get("name")) or npc_id.replace("npc:", ""),
                "role": _safe_str(bio.get("role")),
                "activity": _safe_str(schedule.get("activity")) or "present",
                "availability": "available",
                "schedule_id": _safe_str(schedule.get("schedule_id")),
                "source": "deterministic_scene_population_runtime",
            }
        )

    state = {
        "location_id": location_id,
        "present_npcs": present[:12],
        "debug": {
            "last_updated_tick": int(tick or 0),
            "source": "deterministic_scene_population_runtime",
        },
    }
    simulation_state["scene_population_state"] = state
    return deepcopy(state)
