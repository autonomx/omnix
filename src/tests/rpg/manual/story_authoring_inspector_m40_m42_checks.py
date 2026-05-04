from __future__ import annotations

import json
from typing import Any, Dict, List

from app.rpg.story_authoring.inspector import (
    approve_story_authoring_inspector_proposal,
    build_story_authoring_inspector_payload,
    draft_story_authoring_inspector_proposal,
    reject_story_authoring_inspector_proposal,
)
from app.rpg.story_packs.registry import get_imported_story_pack


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_simulation_state(
    *,
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    session_dict = _safe_dict(session)
    session_setup_payload = _safe_dict(session_dict.get("setup_payload"))
    session_metadata = _safe_dict(session_setup_payload.get("metadata"))

    candidates = [
        session_dict.get("simulation_state"),
        session_metadata.get("simulation_state"),
        _safe_dict(result.get("session")).get("simulation_state"),
        _safe_dict(nested.get("session")).get("simulation_state"),
        result.get("simulation_state"),
        nested.get("simulation_state"),
    ]

    first_non_empty: Dict[str, Any] = {}
    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate and not first_non_empty:
            first_non_empty = candidate
        if (
            isinstance(candidate.get("story_authoring_approval_state"), dict)
            or isinstance(candidate.get("story_pack_state"), dict)
        ):
            return candidate
    return first_non_empty


def _latest_pending_id(simulation_state: Dict[str, Any]) -> str:
    payload = build_story_authoring_inspector_payload(simulation_state)
    pending = payload.get("pending") or []
    if not pending:
        return ""
    return str(pending[-1].get("pending_id") or "")


def run_story_authoring_inspector_m40_m42_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_authoring_inspector_payload":
        payload = build_story_authoring_inspector_payload(
            simulation_state,
            limit=int(check.get("limit") or 20),
        )
        expected_pending_count = check.get("expected_pending_count")
        expected_proposal_id = check.get("expected_proposal_id")
        ok = payload.get("ok") is True
        if expected_pending_count is not None:
            ok = ok and int(payload.get("pending_count") or 0) == int(expected_pending_count)
        if expected_proposal_id:
            ok = ok and expected_proposal_id in [row.get("proposal_id") for row in payload.get("pending") or []]
        return {
            "check_type": check_type,
            "ok": ok,
            "payload": payload,
            "expected_pending_count": expected_pending_count,
            "expected_proposal_id": expected_proposal_id,
        }

    if check_type == "story_authoring_inspector_draft":
        llm_text_override = check.get("llm_text_override")
        if isinstance(llm_text_override, dict):
            llm_text_override = json.dumps(llm_text_override)
        draft_result = draft_story_authoring_inspector_proposal(
            simulation_state,
            authoring_goal=str(check.get("authoring_goal") or "Draft a story pack."),
            turn_index=int(check.get("turn_index") or 1),
            llm_text_override=llm_text_override,
            repair_once=bool(check.get("repair_once", False)),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and draft_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and draft_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "draft_result": draft_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "story_authoring_inspector_approve":
        pending_id = str(check.get("pending_id") or "") or _latest_pending_id(simulation_state)
        approve_result = approve_story_authoring_inspector_proposal(
            simulation_state,
            pending_id=pending_id,
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "gm_approved"),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and approve_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and approve_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "pending_id": pending_id,
            "approve_result": approve_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "story_authoring_inspector_reject":
        pending_id = str(check.get("pending_id") or "") or _latest_pending_id(simulation_state)
        reject_result = reject_story_authoring_inspector_proposal(
            simulation_state,
            pending_id=pending_id,
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "gm_rejected"),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and reject_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and reject_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "pending_id": pending_id,
            "reject_result": reject_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "story_authoring_inspector_imported_pack":
        pack_id = str(check.get("pack_id") or "")
        imported = get_imported_story_pack(simulation_state, pack_id)
        expected_present = bool(check.get("expected_present", True))
        return {
            "check_type": check_type,
            "ok": bool(imported) is expected_present,
            "pack_id": pack_id,
            "imported": imported,
            "expected_present": expected_present,
        }

    if check_type == "story_authoring_inspector_debug_bounded":
        payload = build_story_authoring_inspector_payload(
            simulation_state,
            limit=int(check.get("limit") or 20),
        )
        limit = int(check.get("limit") or 20)
        return {
            "check_type": check_type,
            "ok": len(payload.get("pending") or []) <= limit and len(payload.get("history") or []) <= 20,
            "payload": payload,
            "limit": limit,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_authoring_inspector_m40_m42_check_type:{check_type}",
    }


def run_story_authoring_inspector_m40_m42_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_authoring_inspector_m40_m42_check(check=check, result=result, session=session)
        for check in checks
    ]