from __future__ import annotations

from typing import Any, Dict, List

VALID_ARC_STATUSES = {"inactive", "active", "resolved", "failed"}
LINK_KINDS = {
    "lore": "linked_lore",
    "quest": "linked_quests",
    "puzzle": "linked_puzzles",
    "location": "linked_locations",
    "entity": "linked_entities",
}


def clamp_pressure(value: Any) -> int:
    try:
        number = int(value)
    except Exception:
        number = 0
    return max(0, min(100, number))


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _unique_strs(values: Any) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in _safe_list(values):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def normalize_story_arc(value: Dict[str, Any], *, arc_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_id = _safe_str(value.get("arc_id")) or arc_id
    status = _safe_str(value.get("status")) or "inactive"
    if status not in VALID_ARC_STATUSES:
        status = "inactive"
    return {
        "arc_id": normalized_id,
        "title": _safe_str(value.get("title")) or normalized_id,
        "status": status,
        "stage": _safe_str(value.get("stage")) or status,
        "pressure": clamp_pressure(value.get("pressure")),
        "escalation_level": max(0, _safe_int(value.get("escalation_level"), 0)),
        "linked_lore": _unique_strs(value.get("linked_lore")),
        "linked_quests": _unique_strs(value.get("linked_quests")),
        "linked_puzzles": _unique_strs(value.get("linked_puzzles")),
        "linked_locations": _unique_strs(value.get("linked_locations")),
        "linked_entities": _unique_strs(value.get("linked_entities")),
        "flags": dict(_safe_dict(value.get("flags"))),
        "started_turn": _safe_int_or_none(value.get("started_turn")),
        "resolved_turn": _safe_int_or_none(value.get("resolved_turn")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_arc_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    arcs: Dict[str, Dict[str, Any]] = {}
    for arc_id, arc in _safe_dict(value.get("arcs")).items():
        arc_id = str(arc_id or "")
        if not arc_id:
            continue
        arcs[arc_id] = normalize_story_arc(arc, arc_id=arc_id)
    return {
        "version": 1,
        "arcs": arcs,
    }


def ensure_story_arc_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_arc_state(simulation_state.get("story_arc_state"))
    simulation_state["story_arc_state"] = state
    return state


def get_story_arc(
    simulation_state: Dict[str, Any],
    arc_id: str,
    *,
    create: bool = False,
    title: str = "",
) -> Dict[str, Any] | None:
    state = ensure_story_arc_state(simulation_state)
    arcs = state.setdefault("arcs", {})
    if arc_id not in arcs and create:
        arcs[arc_id] = normalize_story_arc(
            {
                "arc_id": arc_id,
                "title": title or arc_id,
                "status": "inactive",
                "stage": "inactive",
            },
            arc_id=arc_id,
        )
    return arcs.get(arc_id)


def _apply_links(arc: Dict[str, Any], links: Dict[str, Any]) -> None:
    links = _safe_dict(links)
    for kind, key in LINK_KINDS.items():
        values = list(arc.get(key) or [])
        values.extend(_safe_list(links.get(kind)))
        values.extend(_safe_list(links.get(key)))
        # Also check plural versions for convenience
        plural_kind = kind + "s"
        plural_key = key + "s"
        values.extend(_safe_list(links.get(plural_kind)))
        values.extend(_safe_list(links.get(plural_key)))
        arc[key] = _unique_strs(values)


def start_story_arc(
    simulation_state: Dict[str, Any],
    arc_id: str,
    *,
    title: str = "",
    stage: str = "started",
    pressure: int = 0,
    links: Dict[str, Any] | None = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    arc = get_story_arc(simulation_state, arc_id, create=True, title=title)
    assert arc is not None
    arc["status"] = "active"
    arc["stage"] = stage
    arc["pressure"] = clamp_pressure(pressure)
    if arc.get("started_turn") is None:
        arc["started_turn"] = int(turn_index or 0)
    _apply_links(arc, links or {})
    return {
        "ok": True,
        "kind": "story_arc_start",
        "arc_id": arc_id,
        "stage": arc["stage"],
        "status": arc["status"],
        "pressure": arc["pressure"],
        "arc": arc,
    }


def set_story_arc_stage(
    simulation_state: Dict[str, Any],
    arc_id: str,
    stage: str,
    *,
    status: str | None = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    arc = get_story_arc(simulation_state, arc_id, create=True)
    assert arc is not None
    arc["stage"] = stage
    if status:
        arc["status"] = status
    if status in {"resolved", "failed"} and arc.get("resolved_turn") is None:
        arc["resolved_turn"] = int(turn_index or 0)
    return {
        "ok": True,
        "kind": "story_arc_stage",
        "arc_id": arc_id,
        "stage": arc["stage"],
        "status": arc["status"],
        "arc": arc,
    }


def apply_story_arc_pressure_delta(
    simulation_state: Dict[str, Any],
    arc_id: str,
    delta: int,
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    arc = get_story_arc(simulation_state, arc_id, create=True)
    assert arc is not None
    before = int(arc.get("pressure") or 0)
    after = clamp_pressure(before + int(delta or 0))
    arc["pressure"] = after
    arc.setdefault("metadata", {})["last_pressure_turn"] = int(turn_index or 0)
    return {
        "ok": True,
        "kind": "story_arc_pressure_delta",
        "arc_id": arc_id,
        "before": before,
        "delta": int(delta or 0),
        "after": after,
        "arc": arc,
    }


def set_story_arc_flag(
    simulation_state: Dict[str, Any],
    arc_id: str,
    flag: str,
    value: Any,
) -> Dict[str, Any]:
    arc = get_story_arc(simulation_state, arc_id, create=True)
    assert arc is not None
    arc.setdefault("flags", {})[flag] = value
    return {
        "ok": True,
        "kind": "story_arc_flag",
        "arc_id": arc_id,
        "flag": flag,
        "value": value,
        "arc": arc,
    }


def link_story_arc(
    simulation_state: Dict[str, Any],
    arc_id: str,
    kind: str,
    target_id: str,
) -> Dict[str, Any]:
    arc = get_story_arc(simulation_state, arc_id, create=True)
    assert arc is not None
    key = LINK_KINDS.get(kind)
    if not key:
        return {
            "ok": False,
            "reason": f"unknown_link_kind:{kind}",
            "arc_id": arc_id,
            "kind": kind,
            "target_id": target_id,
        }
    values = list(arc.get(key) or [])
    if target_id not in values:
        values.append(target_id)
    arc[key] = _unique_strs(values)
    return {
        "ok": True,
        "reason": "linked",
        "arc_id": arc_id,
        "kind": kind,
        "target_id": target_id,
        "arc": arc,
    }