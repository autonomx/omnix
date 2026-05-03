from __future__ import annotations

import json
from typing import Any, Dict, List

from app.rpg.story_authoring.prompts import build_story_authoring_prompt
from app.rpg.story_authoring.runtime import author_story_proposal
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
            isinstance(candidate.get("story_authoring_state"), dict)
            or isinstance(candidate.get("campaign_journal_state"), dict)
            or isinstance(candidate.get("story_pack_state"), dict)
            or isinstance(candidate.get("lore_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_story_authoring_m34_m36_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_authoring_prompt":
        prompt = build_story_authoring_prompt(
            simulation_state,
            authoring_goal=str(check.get("authoring_goal") or "Create a story pack."),
            turn_index=int(check.get("turn_index") or 1),
            max_items=int(check.get("max_items") or 10),
        )
        must_contain = check.get("must_contain") or []
        must_not_contain = check.get("must_not_contain") or []
        user_text = prompt.get("user") or ""
        ok = all(text in user_text for text in must_contain) and all(text not in user_text for text in must_not_contain)
        return {
            "check_type": check_type,
            "ok": ok,
            "prompt": prompt,
            "must_contain": must_contain,
            "must_not_contain": must_not_contain,
        }

    if check_type == "story_authoring_run":
        llm_text_override = check.get("llm_text_override")
        if isinstance(llm_text_override, dict):
            llm_text_override = json.dumps(llm_text_override)
        authoring_result = author_story_proposal(
            simulation_state,
            authoring_goal=str(check.get("authoring_goal") or "Create a story pack."),
            turn_index=int(check.get("turn_index") or 1),
            import_if_valid=bool(check.get("import_if_valid", False)),
            repair_once=bool(check.get("repair_once", False)),
            llm_text_override=llm_text_override,
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and authoring_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and authoring_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "authoring_result": authoring_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "story_authoring_attempt":
        state = _safe_dict(simulation_state.get("story_authoring_state"))
        attempts = list(state.get("attempts") or [])
        expected_status = check.get("expected_status")
        expected_validation_ok = check.get("expected_validation_ok")
        expected_import_ok = check.get("expected_import_ok")
        rows = attempts
        if expected_status:
            rows = [row for row in rows if row.get("status") == expected_status]
        if expected_validation_ok is not None:
            rows = [row for row in rows if row.get("validation_ok") is bool(expected_validation_ok)]
        if expected_import_ok is not None:
            rows = [row for row in rows if row.get("import_ok") is bool(expected_import_ok)]
        return {
            "check_type": check_type,
            "ok": bool(rows),
            "attempts": attempts,
            "matched": rows,
            "expected_status": expected_status,
            "expected_validation_ok": expected_validation_ok,
            "expected_import_ok": expected_import_ok,
        }

    if check_type == "story_authoring_imported_pack":
        pack_id = str(check.get("pack_id") or "")
        imported = get_imported_story_pack(simulation_state, pack_id)
        return {
            "check_type": check_type,
            "ok": bool(imported),
            "pack_id": pack_id,
            "imported": imported,
        }

    if check_type == "story_authoring_debug_bounded":
        state = _safe_dict(simulation_state.get("story_authoring_state"))
        attempts = list(state.get("attempts") or [])
        max_attempts = int(check.get("max_attempts") or 100)
        return {
            "check_type": check_type,
            "ok": len(attempts) <= max_attempts,
            "attempt_count": len(attempts),
            "max_attempts": max_attempts,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_authoring_m34_m36_check_type:{check_type}",
    }


def run_story_authoring_m34_m36_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_authoring_m34_m36_check(check=check, result=result, session=session)
        for check in checks
    ]