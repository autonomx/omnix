from __future__ import annotations

import json
from typing import Any, Dict, List

from app.rpg.dialogue_context.arc_context import build_arc_dialogue_context
from app.rpg.dialogue_context.rumors import propagate_rumor
from app.rpg.lore.state import get_lore_entry
from app.rpg.memory.causal_retrieval import retrieve_causal_memories


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


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
            isinstance(candidate.get("lore_state"), dict)
            or isinstance(candidate.get("story_arc_state"), dict)
            or isinstance(candidate.get("causal_memory_state"), dict)
            or isinstance(candidate.get("memory_state"), dict)
        ):
            return candidate
    return first_non_empty


def _extract_first_call_grounding_diagnostics(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    grounding_validation = _safe_dict(result.get("grounding_validation") or nested.get("grounding_validation"))
    candidates = [
        result.get("first_call_grounding_diagnostics"),
        nested.get("first_call_grounding_diagnostics"),
        grounding_validation.get("first_call_grounding_diagnostics"),
        _safe_dict(result.get("first_call_semantic_advisory")).get("first_call_grounding_diagnostics"),
        _safe_dict(result.get("first_call_action_advisory")).get("first_call_grounding_diagnostics"),
        _safe_dict(nested.get("first_call_semantic_advisory")).get("first_call_grounding_diagnostics"),
        _safe_dict(nested.get("first_call_action_advisory")).get("first_call_grounding_diagnostics"),
        _safe_dict(result.get("first_call_visible_response")).get("first_call_grounding_diagnostics"),
        _safe_dict(nested.get("first_call_visible_response")).get("first_call_grounding_diagnostics"),
        _safe_dict(result.get("first_call_visible_response_selection")).get("first_call_grounding_diagnostics"),
        _safe_dict(nested.get("first_call_visible_response_selection")).get("first_call_grounding_diagnostics"),
    ]
    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate
    packet = _safe_dict(grounding_validation.get("turn_grounding_packet"))
    if packet:
        return {
            "format_version": "first_call_grounding_diagnostics_v1",
            "turn_grounding_packet": packet,
            "source": "grounding_validation_bridge",
        }
    return {}


def _extract_first_call_packet(result: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = _extract_first_call_grounding_diagnostics(result)
    packet = _safe_dict(diagnostics.get("turn_grounding_packet"))
    if packet:
        return packet
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    grounding_validation = _safe_dict(result.get("grounding_validation") or nested.get("grounding_validation"))
    return _safe_dict(grounding_validation.get("turn_grounding_packet"))


def _extract_visible_text(result: Dict[str, Any]) -> str:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    pieces: List[str] = []
    for source in (result, nested, _safe_dict(result.get("visible_response")), _safe_dict(nested.get("visible_response"))):
        for key in ("narration", "final_narration", "summary", "text"):
            value = _safe_str(source.get(key)).strip()
            if value:
                pieces.append(value)
        npc = _safe_dict(source.get("npc"))
        for key in ("speaker", "line"):
            value = _safe_str(npc.get(key)).strip()
            if value:
                pieces.append(value)
    return "\n".join(pieces)


def _run_first_call_grounding_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    packet = _extract_first_call_packet(result)
    diagnostics = _extract_first_call_grounding_diagnostics(result)
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    failures: List[str] = []

    expected_npc_id = _safe_str(check.get("expected_npc_id") or "npc:bran")
    expected_format = _safe_str(check.get("expected_packet_version") or "turn_grounding_packet_v1")

    if not diagnostics:
        failures.append("missing_first_call_grounding_diagnostics")
    if _safe_str(packet.get("format_version")) != expected_format:
        failures.append("missing_or_wrong_turn_grounding_packet_version")

    priority = _safe_dict(packet.get("priority_context"))
    addressed_ids = [_safe_str(v) for v in _safe_list(priority.get("addressed_npc_ids"))]
    if expected_npc_id and expected_npc_id not in addressed_ids:
        failures.append("expected_addressed_npc_missing")

    npc_context = _safe_dict(packet.get("npc_context"))
    addressed_profiles = [_safe_dict(v) for v in _safe_list(npc_context.get("addressed_npcs"))]
    bran_profile = {}
    for profile in addressed_profiles:
        if _safe_str(profile.get("id")) == expected_npc_id:
            bran_profile = profile
            break
    if not bran_profile:
        failures.append("expected_npc_profile_missing")

    biography = _safe_dict(bran_profile.get("biography"))
    personality = _safe_dict(bran_profile.get("personality_profile"))
    visible_profile = _safe_dict(bran_profile.get("visible_profile"))
    if check.get("require_biography", True) and not (
        _safe_str(biography.get("public")) or _safe_str(visible_profile.get("public_biography"))
    ):
        failures.append("missing_public_biography")
    if check.get("require_personality", True) and not _safe_str(personality.get("summary")):
        failures.append("missing_personality_summary")
    if check.get("require_speech_examples", True) and not _safe_list(personality.get("speech_examples")):
        failures.append("missing_speech_examples")

    expected_non_stateful = check.get("expected_non_stateful")
    if expected_non_stateful is not None:
        stateful_values = [
            result.get("stateful"),
            nested.get("stateful"),
            _safe_dict(result.get("resolved_result")).get("stateful"),
            _safe_dict(nested.get("resolved_result")).get("stateful"),
        ]
        explicit_stateful = [v for v in stateful_values if isinstance(v, bool)]
        if bool(expected_non_stateful) and explicit_stateful and any(explicit_stateful):
            failures.append("expected_non_stateful_but_stateful_true")

        needs_runtime_values = [
            result.get("needs_runtime_resolution"),
            nested.get("needs_runtime_resolution"),
            _safe_dict(result.get("resolved_result")).get("needs_runtime_resolution"),
            _safe_dict(nested.get("resolved_result")).get("needs_runtime_resolution"),
        ]
        explicit_runtime = [v for v in needs_runtime_values if isinstance(v, bool)]
        if bool(expected_non_stateful) and explicit_runtime and any(explicit_runtime):
            failures.append("expected_no_runtime_resolution_but_runtime_required")

    text = _extract_visible_text(result).lower()
    for term in _safe_list(check.get("forbidden_private_terms")):
        term_text = _safe_str(term).lower().strip()
        if term_text and term_text in text:
            failures.append(f"private_term_leaked:{term_text[:40]}")

    return {
        "check_type": "dialogue_first_call_grounding",
        "ok": not failures,
        "failures": failures,
        "error": ";".join(failures),
        "expected_npc_id": expected_npc_id,
        "addressed_npc_ids": addressed_ids,
        "packet_version": _safe_str(packet.get("format_version")),
        "has_diagnostics": bool(diagnostics),
        "has_bran_profile": bool(bran_profile),
        "has_public_biography": bool(_safe_str(biography.get("public")) or _safe_str(visible_profile.get("public_biography"))),
        "has_personality_summary": bool(_safe_str(personality.get("summary"))),
        "speech_example_count": len(_safe_list(personality.get("speech_examples"))),
        "visible_text_preview": text[:500],
    }


def run_dialogue_m16_m18_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "dialogue_first_call_grounding":
        return _run_first_call_grounding_check(check=check, result=result)

    if check_type == "dialogue_context":
        npc_id = str(check.get("npc_id") or "")
        context = build_arc_dialogue_context(
            simulation_state,
            npc_id,
            arc_id=str(check.get("arc_id") or ""),
            topic_lore_id=str(check.get("topic_lore_id") or ""),
        )
        expected_can_discuss = check.get("expected_can_discuss")
        expected_lore_id = check.get("expected_lore_id")
        expected_arc_id = check.get("expected_arc_id")
        expected_must_mark_as_rumor = check.get("expected_must_mark_as_rumor")

        ok = True
        if expected_can_discuss is not None:
            ok = ok and context.get("can_discuss") is bool(expected_can_discuss)
        if expected_lore_id:
            ok = ok and expected_lore_id in [row.get("lore_id") for row in context.get("known_lore") or []]
        if expected_arc_id:
            ok = ok and expected_arc_id in [row.get("arc_id") for row in context.get("known_story_arcs") or []]
        if expected_must_mark_as_rumor is not None:
            ok = ok and context.get("rumor_permissions", {}).get("must_mark_as_rumor") is bool(expected_must_mark_as_rumor)

        return {
            "check_type": check_type,
            "ok": ok,
            "npc_id": npc_id,
            "context": context,
            "expected_can_discuss": expected_can_discuss,
            "expected_lore_id": expected_lore_id,
            "expected_arc_id": expected_arc_id,
            "expected_must_mark_as_rumor": expected_must_mark_as_rumor,
        }

    if check_type == "rumor_propagation":
        propagation = propagate_rumor(
            simulation_state,
            speaker_id=str(check.get("speaker_id") or ""),
            lore_id=str(check.get("lore_id") or ""),
            summary=str(check.get("summary") or ""),
            explicit_hearers=check.get("explicit_hearers"),
            turn_index=int(check.get("turn_index") or 1),
        )
        expected_ok = check.get("expected_ok")
        expected_hearer = check.get("expected_hearer")
        expected_truth_promoted = check.get("expected_truth_promoted")
        ok = True
        if expected_ok is not None:
            ok = ok and propagation.get("ok") is bool(expected_ok)
        if expected_hearer:
            ok = ok and expected_hearer in propagation.get("hearers", [])
        if expected_truth_promoted is not None:
            ok = ok and propagation.get("truth_promoted") is bool(expected_truth_promoted)
        return {
            "check_type": check_type,
            "ok": ok,
            "propagation": propagation,
            "expected_ok": expected_ok,
            "expected_hearer": expected_hearer,
            "expected_truth_promoted": expected_truth_promoted,
        }

    if check_type == "rumor_memory":
        subject_id = str(check.get("subject_id") or "")
        expected_lore_id = str(check.get("expected_lore_id") or "")
        rows = retrieve_causal_memories(
            simulation_state,
            subject_id,
            tags=check.get("tags") or ["rumor"],
            max_items=10,
        )
        matched = []
        for row in rows:
            facts = _safe_dict(row.get("facts"))
            if facts.get("lore_id") == expected_lore_id or _safe_str(row.get("lore_id")) == expected_lore_id:
                matched.append(row)
        return {
            "check_type": check_type,
            "ok": bool(matched),
            "subject_id": subject_id,
            "expected_lore_id": expected_lore_id,
            "matched": matched,
            "retrieved": rows,
        }

    if check_type == "rumor_truth_status":
        lore_id = str(check.get("lore_id") or "")
        expected_truth_status = str(check.get("expected_truth_status") or "")
        entry = get_lore_entry(simulation_state, lore_id)
        actual = str((_safe_dict(entry)).get("truth_status") or "")
        return {
            "check_type": check_type,
            "ok": actual == expected_truth_status,
            "lore_id": lore_id,
            "expected_truth_status": expected_truth_status,
            "actual_truth_status": actual,
            "entry": entry,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_dialogue_m16_m18_check_type:{check_type}",
    }


def run_dialogue_m16_m18_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_dialogue_m16_m18_check(check=check, result=result, session=session)
        for check in checks
    ]
