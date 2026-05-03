from __future__ import annotations

from typing import Any, Dict, List

VALID_TRUTH_STATUSES = {"true", "rumor", "false", "myth", "unknown", "secret"}


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


def _unique_strs(values: Any) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in _safe_list(values):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def normalize_lore_entry(value: Dict[str, Any], *, lore_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_id = _safe_str(value.get("lore_id")) or lore_id
    truth_status = _safe_str(value.get("truth_status")) or "unknown"
    if truth_status not in VALID_TRUTH_STATUSES:
        truth_status = "unknown"
    return {
        "lore_id": normalized_id,
        "title": _safe_str(value.get("title")) or normalized_id,
        "kind": _safe_str(value.get("kind")) or "fact",
        "truth_status": truth_status,
        "revealed_to_player": _safe_bool(value.get("revealed_to_player"), False),
        "known_by": _unique_strs(value.get("known_by")),
        "tags": _unique_strs(value.get("tags")),
        "summary": _safe_str(value.get("summary")),
        "source": _safe_str(value.get("source")) or "manual",
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_lore_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    entries: Dict[str, Dict[str, Any]] = {}
    for lore_id, entry in _safe_dict(value.get("entries")).items():
        lore_id = str(lore_id or "")
        if not lore_id:
            continue
        entries[lore_id] = normalize_lore_entry(entry, lore_id=lore_id)
    return {
        "version": 1,
        "entries": entries,
    }


def ensure_lore_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    lore_state = normalize_lore_state(simulation_state.get("lore_state"))
    simulation_state["lore_state"] = lore_state
    return lore_state


def get_lore_entry(
    simulation_state: Dict[str, Any],
    lore_id: str,
    *,
    create: bool = False,
    title: str = "",
) -> Dict[str, Any] | None:
    lore_state = ensure_lore_state(simulation_state)
    entries = lore_state.setdefault("entries", {})
    if lore_id not in entries and create:
        entries[lore_id] = normalize_lore_entry(
            {
                "lore_id": lore_id,
                "title": title or lore_id,
                "truth_status": "unknown",
            },
            lore_id=lore_id,
        )
    return entries.get(lore_id)


def upsert_lore_entry(
    simulation_state: Dict[str, Any],
    entry: Dict[str, Any],
) -> Dict[str, Any]:
    entry = normalize_lore_entry(entry, lore_id=str(entry.get("lore_id") or ""))
    lore_id = str(entry.get("lore_id") or "")
    if not lore_id:
        return {"ok": False, "reason": "missing_lore_id", "entry": entry}
    lore_state = ensure_lore_state(simulation_state)
    existing = lore_state.setdefault("entries", {}).get(lore_id)
    if existing:
        merged = dict(existing)
        merged.update(entry)
        merged["known_by"] = _unique_strs(list(existing.get("known_by") or []) + list(entry.get("known_by") or []))
        merged["tags"] = _unique_strs(list(existing.get("tags") or []) + list(entry.get("tags") or []))
        lore_state["entries"][lore_id] = normalize_lore_entry(merged, lore_id=lore_id)
    else:
        lore_state["entries"][lore_id] = entry
    return {
        "ok": True,
        "reason": "upserted",
        "lore_id": lore_id,
        "entry": lore_state["entries"][lore_id],
    }


def reveal_lore_to_player(simulation_state: Dict[str, Any], lore_id: str) -> Dict[str, Any]:
    entry = get_lore_entry(simulation_state, lore_id)
    if not entry:
        return {"ok": False, "reason": "lore_missing", "lore_id": lore_id}
    entry["revealed_to_player"] = True
    return {"ok": True, "reason": "revealed", "lore_id": lore_id, "entry": entry}


def set_lore_truth_status(
    simulation_state: Dict[str, Any],
    lore_id: str,
    truth_status: str,
) -> Dict[str, Any]:
    entry = get_lore_entry(simulation_state, lore_id)
    if not entry:
        return {"ok": False, "reason": "lore_missing", "lore_id": lore_id}
    if truth_status not in VALID_TRUTH_STATUSES:
        return {
            "ok": False,
            "reason": "invalid_truth_status",
            "lore_id": lore_id,
            "truth_status": truth_status,
        }
    entry["truth_status"] = truth_status
    return {"ok": True, "reason": "truth_status_set", "lore_id": lore_id, "entry": entry}


def add_lore_known_by(
    simulation_state: Dict[str, Any],
    lore_id: str,
    entity_id: str,
) -> Dict[str, Any]:
    entry = get_lore_entry(simulation_state, lore_id)
    if not entry:
        return {"ok": False, "reason": "lore_missing", "lore_id": lore_id}
    known_by = list(entry.get("known_by") or [])
    if entity_id not in known_by:
        known_by.append(entity_id)
    entry["known_by"] = _unique_strs(known_by)
    return {"ok": True, "reason": "known_by_added", "lore_id": lore_id, "entry": entry}


def add_lore_tag(
    simulation_state: Dict[str, Any],
    lore_id: str,
    tag: str,
) -> Dict[str, Any]:
    entry = get_lore_entry(simulation_state, lore_id)
    if not entry:
        return {"ok": False, "reason": "lore_missing", "lore_id": lore_id}
    tags = list(entry.get("tags") or [])
    if tag not in tags:
        tags.append(tag)
    entry["tags"] = _unique_strs(tags)
    return {"ok": True, "reason": "tag_added", "lore_id": lore_id, "entry": entry}


def is_lore_available_to_player(simulation_state: Dict[str, Any], lore_id: str) -> bool:
    entry = get_lore_entry(simulation_state, lore_id)
    if not entry:
        return False
    return bool(entry.get("revealed_to_player"))


def is_lore_known_by(simulation_state: Dict[str, Any], lore_id: str, entity_id: str) -> bool:
    entry = get_lore_entry(simulation_state, lore_id)
    if not entry:
        return False
    return entity_id in set(entry.get("known_by") or [])