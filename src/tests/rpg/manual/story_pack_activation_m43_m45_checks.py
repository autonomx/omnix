from __future__ import annotations

import json
from typing import Any, Dict, List

from app.rpg.campaign_director.runtime import (
    apply_campaign_director_tick,
    evaluate_campaign_director_tick,
)
from app.rpg.story_authoring.approval import (
    approve_story_proposal,
    draft_story_proposal_for_approval,
)
from app.rpg.story_packs.activation import (
    activate_story_pack,
    build_story_pack_activation_snapshot,
    deactivate_story_pack,
    is_story_pack_active,
)
from app.rpg.story_packs.importer import import_story_pack


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
            isinstance(candidate.get("story_pack_activation_state"), dict)
            or isinstance(candidate.get("story_pack_state"), dict)
            or isinstance(candidate.get("campaign_director_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_story_pack_activation_m43_m45_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_pack_activation_import":
        proposal = _safe_dict(check.get("proposal"))
        import_result = import_story_pack(
            simulation_state,
            proposal,
            turn_index=int(check.get("turn_index") or 1),
        )
        expected_ok = check.get("expected_ok")
        ok = True
        if expected_ok is not None:
            ok = ok and import_result.get("ok") is bool(expected_ok)
        return {
            "check_type": check_type,
            "ok": ok,
            "import_result": import_result,
            "expected_ok": expected_ok,
        }

    if check_type == "story_pack_activation_activate":
        pack_id = str(check.get("pack_id") or "")
        activate_result = activate_story_pack(
            simulation_state,
            pack_id,
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "manual_activate"),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and activate_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and activate_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "activate_result": activate_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "story_pack_activation_deactivate":
        pack_id = str(check.get("pack_id") or "")
        deactivate_result = deactivate_story_pack(
            simulation_state,
            pack_id,
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "manual_deactivate"),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and deactivate_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and deactivate_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "deactivate_result": deactivate_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "story_pack_activation_status":
        pack_id = str(check.get("pack_id") or "")
        expected_active = bool(check.get("expected_active", True))
        actual = is_story_pack_active(simulation_state, pack_id)
        return {
            "check_type": check_type,
            "ok": actual is expected_active,
            "pack_id": pack_id,
            "actual_active": actual,
            "expected_active": expected_active,
            "snapshot": build_story_pack_activation_snapshot(simulation_state),
        }

    if check_type == "story_pack_activation_snapshot":
        snapshot = build_story_pack_activation_snapshot(
            simulation_state,
            limit=int(check.get("limit") or 20),
        )
        expected_pack_id = check.get("expected_pack_id")
        expected_status = check.get("expected_status")
        rows = list(snapshot.get("packs") or [])
        if expected_pack_id:
            rows = [row for row in rows if row.get("pack_id") == expected_pack_id]
        if expected_status:
            rows = [row for row in rows if row.get("status") == expected_status]
        return {
            "check_type": check_type,
            "ok": bool(rows) if (expected_pack_id or expected_status) else snapshot.get("ok") is True,
            "snapshot": snapshot,
            "matched": rows,
            "expected_pack_id": expected_pack_id,
            "expected_status": expected_status,
        }

    if check_type == "story_pack_activation_director_evaluate":
        evaluation = evaluate_campaign_director_tick(
            simulation_state,
            mode=str(check.get("mode") or "idle"),
            turn_index=int(check.get("turn_index") or 1),
            arc_id=str(check.get("arc_id") or ""),
        )
        expected_eligible_count = check.get("expected_eligible_count")
        expected_registered_rule_count = check.get("expected_registered_rule_count")
        ok = True
        if expected_eligible_count is not None:
            ok = ok and int(evaluation.get("eligible_count") or 0) == int(expected_eligible_count)
        if expected_registered_rule_count is not None:
            ok = ok and int(evaluation.get("registered_rule_count") or 0) == int(expected_registered_rule_count)
        return {
            "check_type": check_type,
            "ok": ok,
            "evaluation": evaluation,
            "expected_eligible_count": expected_eligible_count,
            "expected_registered_rule_count": expected_registered_rule_count,
        }

    if check_type == "story_pack_activation_director_apply":
        applied = apply_campaign_director_tick(
            simulation_state,
            mode=str(check.get("mode") or "idle"),
            turn_index=int(check.get("turn_index") or 1),
            arc_id=str(check.get("arc_id") or ""),
        )
        expected_applied_count = check.get("expected_applied_count")
        ok = True
        if expected_applied_count is not None:
            ok = ok and int(applied.get("applied_count") or 0) == int(expected_applied_count)
        return {
            "check_type": check_type,
            "ok": ok,
            "applied": applied,
            "expected_applied_count": expected_applied_count,
        }

    if check_type == "story_pack_activation_approve_authored":
        proposal = check.get("proposal")
        llm_text_override = json.dumps(proposal) if isinstance(proposal, dict) else check.get("llm_text_override")
        draft = draft_story_proposal_for_approval(
            simulation_state,
            authoring_goal=str(check.get("authoring_goal") or "Draft activation bridge pack."),
            llm_text_override=llm_text_override,
            turn_index=int(check.get("draft_turn_index") or 1),
        )
        approve = approve_story_proposal(
            simulation_state,
            pending_id=str(draft.get("pending_id") or ""),
            turn_index=int(check.get("turn_index") or 2),
            auto_activate=bool(check.get("auto_activate", False)),
        )
        expected_reason = check.get("expected_reason")
        ok = approve.get("ok") is True
        if expected_reason:
            ok = ok and approve.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "draft": draft,
            "approve": approve,
            "expected_reason": expected_reason,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_pack_activation_m43_m45_check_type:{check_type}",
    }


def run_story_pack_activation_m43_m45_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_pack_activation_m43_m45_check(check=check, result=result, session=session)
        for check in checks
    ]