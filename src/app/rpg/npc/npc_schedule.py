from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping


@dataclass(frozen=True)
class NPCScheduleBlock:
    npc_id: str
    location_id: str
    start_hour: int
    end_hour: int
    activity: str
    availability: str = "available"
    priority: int = 0


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _hour_from_turn(
    *,
    turn_index: int,
    minutes_per_turn: int = 60,
    start_hour: int = 8,
) -> int:
    total_minutes = int(start_hour * 60) + max(0, int(turn_index) - 1) * int(minutes_per_turn)
    return int((total_minutes // 60) % 24)


def _block_matches_hour(block: NPCScheduleBlock, hour: int) -> bool:
    start = int(block.start_hour) % 24
    end = int(block.end_hour) % 24
    hour = int(hour) % 24

    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def resolve_npc_schedule_state(
    *,
    npc_ids: Iterable[str],
    schedule_blocks: Iterable[NPCScheduleBlock],
    turn_index: int,
    minutes_per_turn: int = 60,
    start_hour: int = 8,
    previous_presence: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    hour = _hour_from_turn(
        turn_index=turn_index,
        minutes_per_turn=minutes_per_turn,
        start_hour=start_hour,
    )

    previous = _safe_dict(previous_presence)
    blocks_by_npc: Dict[str, List[NPCScheduleBlock]] = {}

    for block in schedule_blocks:
        blocks_by_npc.setdefault(block.npc_id, []).append(block)

    presence: Dict[str, Dict[str, Any]] = {}
    movement_events: List[Dict[str, Any]] = []

    for npc_id in npc_ids:
        blocks = sorted(
            blocks_by_npc.get(str(npc_id), []),
            key=lambda block: int(block.priority),
            reverse=True,
        )

        active = next((block for block in blocks if _block_matches_hour(block, hour)), None)

        if active is None:
            row = {
                "npc_id": str(npc_id),
                "location_id": "location:unknown",
                "activity": "untracked",
                "availability": "unknown",
                "hour": hour,
            }
        else:
            row = {
                "npc_id": str(npc_id),
                "location_id": active.location_id,
                "activity": active.activity,
                "availability": active.availability,
                "hour": hour,
            }

        old_location = _safe_str(_safe_dict(previous.get(str(npc_id))).get("location_id"))
        if old_location and old_location != row["location_id"]:
            movement_events.append(
                {
                    "type": "npc_schedule",
                    "subtype": "npc_moved",
                    "npc_id": str(npc_id),
                    "from_location_id": old_location,
                    "to_location_id": row["location_id"],
                    "activity": row["activity"],
                    "turn": int(turn_index),
                    "hour": hour,
                    "meaningful_progress": False,
                    "progress_category": "npc_schedule",
                }
            )

        presence[str(npc_id)] = row

    return {
        "ok": True,
        "turn": int(turn_index),
        "hour": hour,
        "presence": presence,
        "movement_events": movement_events,
        "npc_count": len(presence),
    }


def npcs_present_at_location(
    *,
    presence: Mapping[str, Any],
    location_id: str,
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for npc_id, raw in _safe_dict(presence).items():
        row = _safe_dict(raw)
        if _safe_str(row.get("location_id")) == _safe_str(location_id):
            result.append(dict(row, npc_id=str(npc_id)))
    return result