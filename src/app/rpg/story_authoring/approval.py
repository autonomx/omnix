from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.rpg.story_authoring.runtime import author_story_proposal
from app.rpg.story_packs.activation import activate_story_pack
from app.rpg.story_packs.importer import import_story_pack
from app.rpg.story_proposals.validation import validate_story_proposal

MAX_PENDING_AUTHORED_PROPOSALS = 50
MAX_AUTHORING_APPROVAL_HISTORY = 100


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


def _stable_pending_id(*, proposal: Dict[str, Any], authoring_goal: str, turn_index: int) -> str:
    payload = json.dumps(
        {
            "proposal_id": proposal.get("proposal_id"),
            "proposal_type": proposal.get("proposal_type"),
            "authoring_goal": authoring_goal,
            "turn_index": int(turn_index or 0),
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"authored_pending:{digest}"


def normalize_pending_authored_proposal(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "pending_id": _safe_str(value.get("pending_id")),
        "status": _safe_str(value.get("status")) or "pending",
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "authoring_goal": _safe_str(value.get("authoring_goal")),
        "proposal_id": _safe_str(value.get("proposal_id")),
        "proposal_type": _safe_str(value.get("proposal_type")),
        "title": _safe_str(value.get("title")),
        "proposal": dict(_safe_dict(value.get("proposal"))),
        "validation": dict(_safe_dict(value.get("validation"))),
        "attempt_id": _safe_str(value.get("attempt_id")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_authoring_approval_history_item(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "pending_id": _safe_str(value.get("pending_id")),
        "status": _safe_str(value.get("status")) or "unknown",
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "reason": _safe_str(value.get("reason")),
        "import_ok": bool(value.get("import_ok")),
        "imported_pack_id": _safe_str(value.get("imported_pack_id")),
        "details": dict(_safe_dict(value.get("details"))),
    }


def normalize_story_authoring_approval_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    pending = [
        normalize_pending_authored_proposal(row)
        for row in _safe_list(value.get("pending"))
        if isinstance(row, dict)
    ]
    pending = [
        row
        for row in pending
        if row.get("pending_id") and row.get("status") == "pending"
    ][-MAX_PENDING_AUTHORED_PROPOSALS:]
    pending.sort(key=lambda row: (int(row.get("turn_index") or 0), str(row.get("pending_id") or "")))

    history = [
        normalize_authoring_approval_history_item(row)
        for row in _safe_list(value.get("history"))
        if isinstance(row, dict)
    ][-MAX_AUTHORING_APPROVAL_HISTORY:]
    history.sort(key=lambda row: (int(row.get("turn_index") or 0), str(row.get("pending_id") or "")))

    return {
        "version": 1,
        "pending": pending,
        "history": history,
        "max_pending": MAX_PENDING_AUTHORED_PROPOSALS,
        "max_history": MAX_AUTHORING_APPROVAL_HISTORY,
    }


def ensure_story_authoring_approval_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_authoring_approval_state(simulation_state.get("story_authoring_approval_state"))
    simulation_state["story_authoring_approval_state"] = state
    return state


def _append_history(
    simulation_state: Dict[str, Any],
    *,
    pending_id: str,
    status: str,
    turn_index: int,
    reason: str = "",
    import_ok: bool = False,
    imported_pack_id: str = "",
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = ensure_story_authoring_approval_state(simulation_state)
    history = list(state.get("history") or [])
    history.append(
        normalize_authoring_approval_history_item(
            {
                "pending_id": pending_id,
                "status": status,
                "turn_index": turn_index,
                "reason": reason,
                "import_ok": import_ok,
                "imported_pack_id": imported_pack_id,
                "details": details or {},
            }
        )
    )
    state["history"] = history[-MAX_AUTHORING_APPROVAL_HISTORY:]
    simulation_state["story_authoring_approval_state"] = normalize_story_authoring_approval_state(state)
    return {"ok": True, "reason": "approval_history_recorded"}


def draft_story_proposal_for_approval(
    simulation_state: Dict[str, Any],
    *,
    authoring_goal: str,
    app_context: Any = None,
    turn_index: int = 0,
    llm_text_override: Any = None,
    repair_once: bool = False,
) -> Dict[str, Any]:
    authoring_result = author_story_proposal(
        simulation_state,
        authoring_goal=authoring_goal,
        app_context=app_context,
        turn_index=turn_index,
        import_if_valid=False,
        repair_once=repair_once,
        llm_text_override=llm_text_override,
    )
    if not authoring_result.get("ok"):
        return {
            "ok": False,
            "reason": "authoring_failed",
            "authoring_result": authoring_result,
        }

    proposal = dict(_safe_dict(authoring_result.get("proposal")))
    validation = dict(_safe_dict(authoring_result.get("validation")))
    if not validation.get("ok"):
        return {
            "ok": False,
            "reason": "validation_failed",
            "authoring_result": authoring_result,
            "validation": validation,
        }

    pending_id = _stable_pending_id(
        proposal=proposal,
        authoring_goal=authoring_goal,
        turn_index=turn_index,
    )
    state = ensure_story_authoring_approval_state(simulation_state)
    pending = list(state.get("pending") or [])
    for row in pending:
        if row.get("pending_id") == pending_id:
            return {
                "ok": True,
                "reason": "already_pending",
                "pending_id": pending_id,
                "pending": row,
                "authoring_result": authoring_result,
            }

    item = normalize_pending_authored_proposal(
        {
            "pending_id": pending_id,
            "status": "pending",
            "turn_index": turn_index,
            "authoring_goal": authoring_goal,
            "proposal_id": proposal.get("proposal_id"),
            "proposal_type": proposal.get("proposal_type"),
            "title": proposal.get("title"),
            "proposal": proposal,
            "validation": validation,
            "attempt_id": authoring_result.get("attempt_id"),
            "metadata": {"source": "story_authoring_approval_v1"},
        }
    )
    pending.append(item)
    state["pending"] = pending[-MAX_PENDING_AUTHORED_PROPOSALS:]
    simulation_state["story_authoring_approval_state"] = normalize_story_authoring_approval_state(state)
    return {
        "ok": True,
        "reason": "pending_approval",
        "pending_id": pending_id,
        "pending": item,
        "authoring_result": authoring_result,
    }


def list_pending_story_proposals(simulation_state: Dict[str, Any], *, limit: int = 20) -> Dict[str, Any]:
    state = ensure_story_authoring_approval_state(simulation_state)
    limit = max(0, min(50, int(limit or 20)))
    pending = list(state.get("pending") or [])[-limit:]
    return {
        "ok": True,
        "pending": pending,
        "pending_count": len(state.get("pending") or []),
        "history": list(state.get("history") or [])[-limit:],
        "bounded": {"limit": limit, "max_pending": MAX_PENDING_AUTHORED_PROPOSALS},
    }


def get_pending_story_proposal(simulation_state: Dict[str, Any], pending_id: str) -> Dict[str, Any] | None:
    state = ensure_story_authoring_approval_state(simulation_state)
    for row in state.get("pending") or []:
        if row.get("pending_id") == pending_id:
            return row
    return None


def approve_story_proposal(
    simulation_state: Dict[str, Any],
    *,
    pending_id: str,
    turn_index: int = 0,
    reason: str = "gm_approved",
    auto_activate: bool = False,
) -> Dict[str, Any]:
    pending_id = str(pending_id or "")
    state = ensure_story_authoring_approval_state(simulation_state)
    pending = list(state.get("pending") or [])
    item = None
    remaining = []
    for row in pending:
        if row.get("pending_id") == pending_id:
            item = row
        else:
            remaining.append(row)
    if item is None:
        return {"ok": False, "reason": "pending_proposal_missing", "pending_id": pending_id}

    proposal = dict(_safe_dict(item.get("proposal")))
    validation = validate_story_proposal(simulation_state, proposal)
    if not validation.get("ok"):
        _append_history(
            simulation_state,
            pending_id=pending_id,
            status="approval_failed",
            turn_index=turn_index,
            reason="validation_failed",
            details={"validation": validation},
        )
        return {
            "ok": False,
            "reason": "validation_failed",
            "pending_id": pending_id,
            "validation": validation,
        }

    import_result = import_story_pack(simulation_state, proposal, turn_index=turn_index)
    if not import_result.get("ok"):
        _append_history(
            simulation_state,
            pending_id=pending_id,
            status="approval_failed",
            turn_index=turn_index,
            reason="import_failed",
            details={"import_result": import_result},
        )
        return {
            "ok": False,
            "reason": "import_failed",
            "pending_id": pending_id,
            "import_result": import_result,
        }

    activation_result = None
    if auto_activate:
        activation_result = activate_story_pack(
            simulation_state,
            str(import_result.get("pack_id") or ""),
            turn_index=turn_index,
            reason="approved_auto_activate",
            metadata={"pending_id": pending_id},
        )

    state = ensure_story_authoring_approval_state(simulation_state)
    state["pending"] = remaining
    simulation_state["story_authoring_approval_state"] = normalize_story_authoring_approval_state(state)
    _append_history(
        simulation_state,
        pending_id=pending_id,
        status="approved",
        turn_index=turn_index,
        reason=reason,
        import_ok=True,
        imported_pack_id=str(import_result.get("pack_id") or ""),
        details={
            "proposal_id": proposal.get("proposal_id"),
            "import_result": import_result,
            "activation_result": activation_result or {},
            "auto_activate": auto_activate,
        },
    )
    return {
        "ok": True,
        "reason": "approved_imported_activated" if activation_result and activation_result.get("ok") else "approved_imported",
        "pending_id": pending_id,
        "import_result": import_result,
        "activation_result": activation_result,
    }


def reject_story_proposal(
    simulation_state: Dict[str, Any],
    *,
    pending_id: str,
    turn_index: int = 0,
    reason: str = "gm_rejected",
) -> Dict[str, Any]:
    pending_id = str(pending_id or "")
    state = ensure_story_authoring_approval_state(simulation_state)
    pending = list(state.get("pending") or [])
    item = None
    remaining = []
    for row in pending:
        if row.get("pending_id") == pending_id:
            item = row
        else:
            remaining.append(row)
    if item is None:
        return {"ok": False, "reason": "pending_proposal_missing", "pending_id": pending_id}

    state["pending"] = remaining
    simulation_state["story_authoring_approval_state"] = normalize_story_authoring_approval_state(state)
    _append_history(
        simulation_state,
        pending_id=pending_id,
        status="rejected",
        turn_index=turn_index,
        reason=reason,
        details={"proposal_id": item.get("proposal_id")},
    )
    return {
        "ok": True,
        "reason": "rejected",
        "pending_id": pending_id,
    }