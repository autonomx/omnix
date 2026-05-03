from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from app.rpg.story_authoring.parsing import parse_story_authoring_json
from app.rpg.story_authoring.prompts import (
    build_story_authoring_prompt,
    build_story_repair_prompt,
)
from app.rpg.story_authoring.provider import call_story_authoring_provider
from app.rpg.story_authoring.state import record_story_authoring_attempt
from app.rpg.story_packs.importer import import_story_pack
from app.rpg.story_proposals.validation import validate_story_proposal


def _stable_attempt_id(*, authoring_goal: str, turn_index: int, raw: Any = "") -> str:
    payload = json.dumps(
        {
            "authoring_goal": authoring_goal,
            "turn_index": int(turn_index or 0),
            "raw": str(raw)[:1000],
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"story_authoring:{digest}"


def _error_row(reason: str, **kwargs: Any) -> Dict[str, Any]:
    row = {"reason": reason}
    row.update(kwargs)
    return row


def author_story_proposal(
    simulation_state: Dict[str, Any],
    *,
    authoring_goal: str,
    app_context: Any = None,
    turn_index: int = 0,
    import_if_valid: bool = False,
    repair_once: bool = False,
    llm_text_override: Any = None,
) -> Dict[str, Any]:
    prompt = build_story_authoring_prompt(
        simulation_state,
        authoring_goal=authoring_goal,
        turn_index=turn_index,
    )

    provider_result = {
        "ok": True,
        "reason": "override_used",
        "text": llm_text_override,
        "provider": "override",
        "model": "override",
    }
    if llm_text_override is None:
        provider_result = call_story_authoring_provider(
            app_context,
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
        )
    if not provider_result.get("ok"):
        attempt_id = _stable_attempt_id(
            authoring_goal=authoring_goal,
            turn_index=turn_index,
            raw=provider_result.get("reason"),
        )
        record_story_authoring_attempt(
            simulation_state,
            attempt_id=attempt_id,
            turn_index=turn_index,
            status="provider_failed",
            provider=provider_result.get("provider") or "",
            model=provider_result.get("model") or "",
            errors=[_error_row(provider_result.get("reason") or "provider_failed")],
            metadata={"provider_result": provider_result},
        )
        return {
            "ok": False,
            "reason": "provider_failed",
            "attempt_id": attempt_id,
            "provider_result": provider_result,
            "prompt": prompt,
        }

    parsed = parse_story_authoring_json(provider_result.get("text"))
    attempt_id = _stable_attempt_id(
        authoring_goal=authoring_goal,
        turn_index=turn_index,
        raw=provider_result.get("text"),
    )
    if not parsed.get("ok"):
        record_story_authoring_attempt(
            simulation_state,
            attempt_id=attempt_id,
            turn_index=turn_index,
            status="parse_failed",
            provider=provider_result.get("provider") or "",
            model=provider_result.get("model") or "",
            errors=[_error_row(parsed.get("error") or "parse_failed")],
            metadata={"raw": parsed.get("raw", "")},
        )
        return {
            "ok": False,
            "reason": "parse_failed",
            "attempt_id": attempt_id,
            "parse": parsed,
            "provider_result": provider_result,
            "prompt": prompt,
        }

    validation = validate_story_proposal(simulation_state, parsed["proposal"])
    repair_result: Dict[str, Any] | None = None
    proposal = parsed["proposal"]
    repair_attempted = False

    if not validation.get("ok") and repair_once and app_context is not None and llm_text_override is None:
        repair_attempted = True
        repair_prompt = build_story_repair_prompt(
            invalid_proposal=proposal,
            validation=validation,
            authoring_goal=authoring_goal,
        )
        repair_provider_result = call_story_authoring_provider(
            app_context,
            system_prompt=repair_prompt["system"],
            user_prompt=repair_prompt["user"],
        )
        repair_parsed = parse_story_authoring_json(repair_provider_result.get("text"))
        if repair_provider_result.get("ok") and repair_parsed.get("ok"):
            repair_validation = validate_story_proposal(simulation_state, repair_parsed["proposal"])
            repair_result = {
                "provider_result": repair_provider_result,
                "parse": repair_parsed,
                "validation": repair_validation,
            }
            if repair_validation.get("ok"):
                proposal = repair_parsed["proposal"]
                validation = repair_validation
        else:
            repair_result = {
                "provider_result": repair_provider_result,
                "parse": repair_parsed,
            }

    if not validation.get("ok"):
        record_story_authoring_attempt(
            simulation_state,
            attempt_id=attempt_id,
            turn_index=turn_index,
            status="validation_failed",
            provider=provider_result.get("provider") or "",
            model=provider_result.get("model") or "",
            proposal_id=str(proposal.get("proposal_id") or ""),
            proposal_type=str(proposal.get("proposal_type") or ""),
            validation_ok=False,
            errors=validation.get("errors") or [],
            repair_attempted=repair_attempted,
            metadata={"repair_result": repair_result or {}},
        )
        return {
            "ok": False,
            "reason": "validation_failed",
            "attempt_id": attempt_id,
            "proposal": proposal,
            "validation": validation,
            "repair_result": repair_result,
            "prompt": prompt,
        }

    import_result: Dict[str, Any] | None = None
    if import_if_valid:
        import_result = import_story_pack(
            simulation_state,
            proposal,
            turn_index=turn_index,
        )

    import_ok = bool(import_result and import_result.get("ok"))
    status = "imported" if import_ok else "validated"
    record_story_authoring_attempt(
        simulation_state,
        attempt_id=attempt_id,
        turn_index=turn_index,
        status=status,
        provider=provider_result.get("provider") or "",
        model=provider_result.get("model") or "",
        proposal_id=str(proposal.get("proposal_id") or ""),
        proposal_type=str(proposal.get("proposal_type") or ""),
        validation_ok=True,
        import_ok=import_ok,
        imported_pack_id=str((import_result or {}).get("pack_id") or ""),
        errors=[],
        repair_attempted=repair_attempted,
        metadata={
            "authoring_goal": authoring_goal,
            "import_if_valid": import_if_valid,
        },
    )
    return {
        "ok": True,
        "reason": status,
        "attempt_id": attempt_id,
        "proposal": proposal,
        "validation": validation,
        "import_result": import_result,
        "repair_result": repair_result,
        "prompt": prompt,
    }


def import_authored_story_proposal(
    simulation_state: Dict[str, Any],
    proposal: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    validation = validate_story_proposal(simulation_state, proposal)
    if not validation.get("ok"):
        return {
            "ok": False,
            "reason": "validation_failed",
            "validation": validation,
        }
    return import_story_pack(
        simulation_state,
        proposal,
        turn_index=turn_index,
    )