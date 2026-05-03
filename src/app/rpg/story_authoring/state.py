from __future__ import annotations

from typing import Any, Dict, List


MAX_STORY_AUTHORING_ATTEMPTS = 100


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


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def normalize_story_authoring_attempt(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "attempt_id": _safe_str(value.get("attempt_id")),
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "status": _safe_str(value.get("status")) or "unknown",
        "prompt_kind": _safe_str(value.get("prompt_kind")) or "story_pack",
        "provider": _safe_str(value.get("provider")),
        "model": _safe_str(value.get("model")),
        "proposal_id": _safe_str(value.get("proposal_id")),
        "proposal_type": _safe_str(value.get("proposal_type")),
        "validation_ok": _safe_bool(value.get("validation_ok"), False),
        "import_ok": _safe_bool(value.get("import_ok"), False),
        "imported_pack_id": _safe_str(value.get("imported_pack_id")),
        "errors": [
            dict(row)
            for row in _safe_list(value.get("errors"))
            if isinstance(row, dict)
        ][:50],
        "repair_attempted": _safe_bool(value.get("repair_attempted"), False),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_authoring_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    attempts = [
        normalize_story_authoring_attempt(row)
        for row in _safe_list(value.get("attempts"))
        if isinstance(row, dict)
    ][-MAX_STORY_AUTHORING_ATTEMPTS:]
    attempts.sort(
        key=lambda row: (
            int(row.get("turn_index") or 0),
            str(row.get("attempt_id") or ""),
        )
    )
    return {
        "version": 1,
        "attempts": attempts,
        "max_attempts": MAX_STORY_AUTHORING_ATTEMPTS,
    }


def ensure_story_authoring_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_authoring_state(simulation_state.get("story_authoring_state"))
    simulation_state["story_authoring_state"] = state
    return state


def record_story_authoring_attempt(
    simulation_state: Dict[str, Any],
    *,
    attempt_id: str,
    turn_index: int = 0,
    status: str,
    prompt_kind: str = "story_pack",
    provider: str = "",
    model: str = "",
    proposal_id: str = "",
    proposal_type: str = "",
    validation_ok: bool = False,
    import_ok: bool = False,
    imported_pack_id: str = "",
    errors: List[Dict[str, Any]] | None = None,
    repair_attempted: bool = False,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = ensure_story_authoring_state(simulation_state)
    row = normalize_story_authoring_attempt(
        {
            "attempt_id": attempt_id,
            "turn_index": turn_index,
            "status": status,
            "prompt_kind": prompt_kind,
            "provider": provider,
            "model": model,
            "proposal_id": proposal_id,
            "proposal_type": proposal_type,
            "validation_ok": validation_ok,
            "import_ok": import_ok,
            "imported_pack_id": imported_pack_id,
            "errors": errors or [],
            "repair_attempted": repair_attempted,
            "metadata": metadata or {},
        }
    )
    attempts = list(state.get("attempts") or [])
    attempts.append(row)
    state["attempts"] = attempts[-MAX_STORY_AUTHORING_ATTEMPTS:]
    simulation_state["story_authoring_state"] = normalize_story_authoring_state(state)
    return {
        "ok": True,
        "reason": "story_authoring_attempt_recorded",
        "attempt": row,
    }