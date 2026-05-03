from __future__ import annotations

from typing import Any, Dict, List

MAX_IMPORTED_STORY_PACKS = 200


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


def normalize_imported_story_pack(value: Dict[str, Any], *, pack_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_pack_id = _safe_str(value.get("pack_id")) or pack_id
    return {
        "pack_id": normalized_pack_id,
        "proposal_id": _safe_str(value.get("proposal_id")),
        "title": _safe_str(value.get("title")) or normalized_pack_id,
        "imported_turn": _safe_int(value.get("imported_turn"), 0),
        "lore_ids": [
            str(item)
            for item in _safe_list(value.get("lore_ids"))
            if str(item)
        ][:200],
        "arc_ids": [
            str(item)
            for item in _safe_list(value.get("arc_ids"))
            if str(item)
        ][:200],
        "event_ids": [
            str(item)
            for item in _safe_list(value.get("event_ids"))
            if str(item)
        ][:200],
        "rule_ids": [
            str(item)
            for item in _safe_list(value.get("rule_ids"))
            if str(item)
        ][:200],
        "quest_ids": [
            str(item)
            for item in _safe_list(value.get("quest_ids"))
            if str(item)
        ][:200],
        "idempotent": _safe_bool(value.get("idempotent"), True),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_pack_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    packs: Dict[str, Dict[str, Any]] = {}
    for pack_id, row in _safe_dict(value.get("imported_packs")).items():
        pack_id = str(pack_id or "")
        if not pack_id:
            continue
        packs[pack_id] = normalize_imported_story_pack(row, pack_id=pack_id)

    ordered_ids = sorted(
        packs,
        key=lambda pid: (
            int(packs[pid].get("imported_turn") or 0),
            pid,
        ),
    )[-MAX_IMPORTED_STORY_PACKS:]

    return {
        "version": 1,
        "imported_packs": {
            pack_id: packs[pack_id]
            for pack_id in ordered_ids
        },
        "max_imported_packs": MAX_IMPORTED_STORY_PACKS,
    }


def ensure_story_pack_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_pack_state(simulation_state.get("story_pack_state"))
    simulation_state["story_pack_state"] = state
    return state


def get_imported_story_pack(
    simulation_state: Dict[str, Any],
    pack_id: str,
) -> Dict[str, Any] | None:
    state = ensure_story_pack_state(simulation_state)
    return state.get("imported_packs", {}).get(pack_id)


def mark_story_pack_imported(
    simulation_state: Dict[str, Any],
    *,
    pack_id: str,
    proposal_id: str = "",
    title: str = "",
    lore_ids: List[str] | None = None,
    arc_ids: List[str] | None = None,
    event_ids: List[str] | None = None,
    rule_ids: List[str] | None = None,
    quest_ids: List[str] | None = None,
    turn_index: int = 0,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = ensure_story_pack_state(simulation_state)
    if not pack_id:
        return {"ok": False, "reason": "missing_pack_id"}

    row = normalize_imported_story_pack(
        {
            "pack_id": pack_id,
            "proposal_id": proposal_id,
            "title": title or pack_id,
            "imported_turn": int(turn_index or 0),
            "lore_ids": lore_ids or [],
            "arc_ids": arc_ids or [],
            "event_ids": event_ids or [],
            "rule_ids": rule_ids or [],
            "quest_ids": quest_ids or [],
            "idempotent": True,
            "metadata": metadata or {},
        },
        pack_id=pack_id,
    )
    state.setdefault("imported_packs", {})[pack_id] = row
    simulation_state["story_pack_state"] = normalize_story_pack_state(state)
    return {
        "ok": True,
        "reason": "story_pack_import_marked",
        "pack_id": pack_id,
        "imported": simulation_state["story_pack_state"]["imported_packs"][pack_id],
    }