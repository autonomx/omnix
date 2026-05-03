from __future__ import annotations

from typing import Any, Dict, List

MAX_NPC_EVOLUTION_HISTORY = 50
MAX_PERSONALITY_VALUE = 100
MIN_PERSONALITY_VALUE = -100


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp_personality(value: Any) -> int:
    return max(MIN_PERSONALITY_VALUE, min(MAX_PERSONALITY_VALUE, _safe_int(value, 0)))


def _unique_strs(values: Any, *, limit: int = 50) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in _safe_list(values):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def normalize_npc_evolution(value: Dict[str, Any], *, npc_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_npc_id = _safe_str(value.get("npc_id")) or npc_id
    personality = {
        str(key): _clamp_personality(val)
        for key, val in _safe_dict(value.get("personality")).items()
        if str(key)
    }
    history = [
        dict(row)
        for row in _safe_list(value.get("history"))
        if isinstance(row, dict)
    ][-MAX_NPC_EVOLUTION_HISTORY:]
    return {
        "npc_id": normalized_npc_id,
        "active_arcs": _unique_strs(value.get("active_arcs")),
        "completed_arcs": _unique_strs(value.get("completed_arcs")),
        "profession": _safe_str(value.get("profession")),
        "role": _safe_str(value.get("role")),
        "motivation": _safe_str(value.get("motivation")),
        "companion_eligible": _safe_bool(value.get("companion_eligible"), False),
        "companion_offered": _safe_bool(value.get("companion_offered"), False),
        "personality": personality,
        "flags": dict(_safe_dict(value.get("flags"))),
        "history": history,
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_npc_evolution_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    npcs: Dict[str, Dict[str, Any]] = {}
    for npc_id, row in _safe_dict(value.get("npcs")).items():
        npc_id = str(npc_id or "")
        if not npc_id:
            continue
        npcs[npc_id] = normalize_npc_evolution(row, npc_id=npc_id)
    return {
        "version": 1,
        "npcs": npcs,
        "max_history_per_npc": MAX_NPC_EVOLUTION_HISTORY,
    }


def ensure_npc_evolution_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_npc_evolution_state(simulation_state.get("npc_evolution_state"))
    simulation_state["npc_evolution_state"] = state
    return state


def get_npc_evolution(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    create: bool = False,
) -> Dict[str, Any] | None:
    state = ensure_npc_evolution_state(simulation_state)
    npcs = state.setdefault("npcs", {})
    if npc_id not in npcs and create:
        npcs[npc_id] = normalize_npc_evolution({"npc_id": npc_id}, npc_id=npc_id)
    return npcs.get(npc_id)


def _append_history(
    evolution: Dict[str, Any],
    *,
    kind: str,
    turn_index: int = 0,
    details: Dict[str, Any] | None = None,
) -> None:
    history = list(evolution.get("history") or [])
    history.append(
        {
            "kind": kind,
            "turn_index": int(turn_index or 0),
            "details": dict(details or {}),
        }
    )
    evolution["history"] = history[-MAX_NPC_EVOLUTION_HISTORY:]


def start_npc_arc(
    simulation_state: Dict[str, Any],
    npc_id: str,
    arc_id: str,
    *,
    motivation: str = "",
    role: str = "",
    profession: str = "",
    turn_index: int = 0,
) -> Dict[str, Any]:
    evolution = get_npc_evolution(simulation_state, npc_id, create=True)
    assert evolution is not None
    active = list(evolution.get("active_arcs") or [])
    completed = set(evolution.get("completed_arcs") or [])
    if arc_id not in active and arc_id not in completed:
        active.append(arc_id)
    evolution["active_arcs"] = _unique_strs(active)
    if motivation:
        evolution["motivation"] = motivation
    if role:
        evolution["role"] = role
    if profession:
        evolution["profession"] = profession
    _append_history(
        evolution,
        kind="npc_arc_started",
        turn_index=turn_index,
        details={"arc_id": arc_id, "motivation": motivation, "role": role, "profession": profession},
    )
    return {
        "ok": True,
        "reason": "npc_arc_started",
        "npc_id": npc_id,
        "arc_id": arc_id,
        "evolution": evolution,
    }


def complete_npc_arc(
    simulation_state: Dict[str, Any],
    npc_id: str,
    arc_id: str,
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    evolution = get_npc_evolution(simulation_state, npc_id, create=True)
    assert evolution is not None
    active = [item for item in list(evolution.get("active_arcs") or []) if item != arc_id]
    completed = list(evolution.get("completed_arcs") or [])
    if arc_id not in completed:
        completed.append(arc_id)
    evolution["active_arcs"] = _unique_strs(active)
    evolution["completed_arcs"] = _unique_strs(completed)
    _append_history(evolution, kind="npc_arc_completed", turn_index=turn_index, details={"arc_id": arc_id})
    return {
        "ok": True,
        "reason": "npc_arc_completed",
        "npc_id": npc_id,
        "arc_id": arc_id,
        "evolution": evolution,
    }


def apply_npc_evolution_delta(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    profession: str = "",
    role: str = "",
    motivation: str = "",
    personality_deltas: Dict[str, Any] | None = None,
    companion_eligible: bool | None = None,
    companion_offered: bool | None = None,
    flags: Dict[str, Any] | None = None,
    source_event_id: str = "",
    turn_index: int = 0,
) -> Dict[str, Any]:
    evolution = get_npc_evolution(simulation_state, npc_id, create=True)
    assert evolution is not None
    before_personality = dict(evolution.get("personality") or {})
    if profession:
        evolution["profession"] = profession
    if role:
        evolution["role"] = role
    if motivation:
        evolution["motivation"] = motivation
    personality = dict(evolution.get("personality") or {})
    for key, delta in _safe_dict(personality_deltas).items():
        key = str(key or "")
        if not key:
            continue
        personality[key] = _clamp_personality(int(personality.get(key) or 0) + int(delta or 0))
    evolution["personality"] = personality
    if companion_eligible is not None:
        evolution["companion_eligible"] = bool(companion_eligible)
    if companion_offered is not None:
        evolution["companion_offered"] = bool(companion_offered)
    if flags:
        existing_flags = dict(evolution.get("flags") or {})
        existing_flags.update(dict(flags))
        evolution["flags"] = existing_flags
    _append_history(
        evolution,
        kind="npc_evolution_delta",
        turn_index=turn_index,
        details={
            "source_event_id": source_event_id,
            "profession": profession,
            "role": role,
            "motivation": motivation,
            "personality_before": before_personality,
            "personality_after": personality,
            "companion_eligible": companion_eligible,
            "companion_offered": companion_offered,
            "flags": flags or {},
        },
    )
    return {
        "ok": True,
        "reason": "npc_evolution_delta_applied",
        "npc_id": npc_id,
        "evolution": evolution,
    }


def set_npc_arc_flag(
    simulation_state: Dict[str, Any],
    npc_id: str,
    flag: str,
    value: Any,
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    evolution = get_npc_evolution(simulation_state, npc_id, create=True)
    assert evolution is not None
    evolution.setdefault("flags", {})[flag] = value
    _append_history(evolution, kind="npc_flag_set", turn_index=turn_index, details={"flag": flag, "value": value})
    return {
        "ok": True,
        "reason": "npc_flag_set",
        "npc_id": npc_id,
        "flag": flag,
        "value": value,
        "evolution": evolution,
    }