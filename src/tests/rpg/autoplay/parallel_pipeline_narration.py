"""Split helpers for autoplay background pipeline."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405,F811
from tests.rpg.autoplay.parallel_pipeline_common import *

def _deferred_narration_job(
    *,
    queued_at: float,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    started = now_perf()
    wall_started = time.perf_counter()
    before_digest = state_digest(_safe_dict(simulation_state))
    frozen_state = freeze_snapshot(_safe_dict(simulation_state))
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "state_keys": sorted(list(frozen_state.keys()))[:80],
    }
    try:
        build_started = now_perf()
        payload = build_runtime_narration_payload(
            provider=provider,
            player_action=player_action,
            simulation_state=frozen_state,
            turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
            prefer_provider=bool(prefer_provider),
        )
        diagnostics["build_runtime_narration_payload_ms"] = elapsed_ms(build_started)
        diagnostics["payload_source"] = payload.get("source") if isinstance(payload, dict) else ""
        diagnostics["payload_has_narration"] = bool(_safe_str(_safe_dict(payload).get("narration")))
        diagnostics["payload_error"] = _safe_str(_safe_dict(payload).get("error"))
        diagnostics["payload_original_error"] = _safe_str(_safe_dict(payload).get("original_error"))
        after_digest = state_digest(_safe_dict(simulation_state))
        finished = now_perf()
        return {
            "ok": True,
            "kind": "deferred_narration",
            "session_id": session_id,
            "turn_index": turn_index,
            "narration_status": "ready",
            "narration_job_id": f"narration:{session_id}:{turn_index}",
            "narration": _safe_str(payload.get("narration")),
            "npc": _safe_dict(payload.get("npc")),
            "narration_payload": payload,
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "worker_wall_seconds": round(time.perf_counter() - wall_started, 3),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
            "state_digest_before": before_digest,
            "state_digest_after": after_digest,
            "mutated_authoritative_snapshot": before_digest != after_digest,
        }
    except Exception as exc:
        finished = now_perf()
        diagnostics["exception"] = f"{type(exc).__name__}: {exc}"
        return {
            "ok": False,
            "kind": "deferred_narration",
            "session_id": session_id,
            "turn_index": turn_index,
            "narration_status": "error",
            "narration_job_id": f"narration:{session_id}:{turn_index}",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "worker_wall_seconds": round(time.perf_counter() - wall_started, 3),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }


def _provider_text_from_response(response: Any) -> str:
    for attr in ("content", "text", "message"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(response, dict):
        for key in ("content", "text", "message"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_json_object_from_text(text: str) -> Dict[str, Any]:
    """Extract a JSON object from raw provider text.

    Local models often return ```json fences or a short preamble before JSON.
    Advisory extraction is background-only, so be permissive and normalize the
    first valid object we can find.
    """
    import json
    import re

    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty_provider_text")

    cleaned = text.strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find("{")
    if start < 0:
        raise ValueError("no_json_object_start")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : index + 1])

    raise ValueError("unterminated_json_object")


def _candidate_arrays_present(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in (
        "candidates",
        "semantic_intent_candidates",
        "relationship_delta_candidates",
        "memory_candidates",
        "world_signal_candidates",
        "future_hook_candidates",
    ):
        if isinstance(payload.get(key), list):
            return True
    return False


def _has_expected_combined_provider_keys(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    expected_keys = {
        "presentation_intent",
        "current_action_response",
        "response_focus",
        "intent",
        "narration",
        "action",
        "npc",
        "reward",
        "followup_hooks",
        "semantic_intent_candidates",
        "relationship_delta_candidates",
        "memory_candidates",
        "world_signal_candidates",
        "future_hook_candidates",
        "candidates",
    }
    return any(key in payload for key in expected_keys)


def _normalize_followup_hooks(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _extract_nested_combined_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize common provider shapes into the combined background schema.

    Local models may return:
      - the exact requested shape
      - {"narration_payload": {...}, "advisory": {...}}
      - {"narration": {...}, "candidates": [...]}
      - {"result": {...}}
      - {"data": {...}}

    Combined mode should accept any of these if they contain usable narration
    and/or advisory candidates.
    """
    payload = _safe_dict(payload)
    for wrapper_key in ("result", "data", "payload", "response"):
        nested = _safe_dict(payload.get(wrapper_key))
        if nested:
            payload = nested
            break

    normalized: Dict[str, Any] = dict(payload)

    # Preserve the exact combined schema when the model already returned it.
    # Latest artifact showed LM Studio returned all expected keys directly, but
    # the useful-content check still rejected it. Keep these fields explicit.
    if "narration" in payload and isinstance(payload.get("narration"), str):
        normalized["narration"] = payload.get("narration")
    if "action" in payload and isinstance(payload.get("action"), str):
        normalized["action"] = payload.get("action")
    if "npc" in payload and isinstance(payload.get("npc"), dict):
        normalized["npc"] = payload.get("npc")
    if "reward" in payload and isinstance(payload.get("reward"), str):
        normalized["reward"] = payload.get("reward")
    if "followup_hooks" in payload:
        normalized["followup_hooks"] = _normalize_followup_hooks(payload.get("followup_hooks"))
    provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(payload)
    if provider_intent_candidate:
        normalized["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
        normalized["presentation_intent_parse_source"] = provider_intent_source
    response_candidate, response_source = _find_current_action_response_candidate(payload)
    if response_candidate:
        normalized["current_action_response"] = _normalize_current_action_response(response_candidate)
        normalized["current_action_response_parse_source"] = response_source
    if isinstance(payload.get("npc_response_architecture_ack"), dict):
        normalized["npc_response_architecture_ack"] = _safe_dict(payload.get("npc_response_architecture_ack"))

    narration_payload = _safe_dict(
        payload.get("narration_payload")
        or payload.get("structured_narration")
        or payload.get("narration_result")
    )

    narration_value = payload.get("narration")
    if isinstance(narration_value, dict):
        narration_payload = {**narration_value, **narration_payload}
        narration_value = narration_payload.get("narration") or narration_payload.get("text") or ""

    if narration_payload:
        normalized["narration"] = (
            _safe_str(narration_payload.get("narration"))
            or _safe_str(narration_payload.get("text"))
            or _safe_str(narration_value)
        )
        normalized["action"] = (
            _safe_str(narration_payload.get("action"))
            or _safe_str(payload.get("action"))
        )
        normalized["npc"] = _safe_dict(narration_payload.get("npc") or payload.get("npc"))
        normalized["reward"] = _safe_str(narration_payload.get("reward") or payload.get("reward"))
        normalized["followup_hooks"] = (
            _normalize_followup_hooks(narration_payload.get("followup_hooks"))
            or _normalize_followup_hooks(payload.get("followup_hooks"))
        )
        provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(
            {**payload, "narration_payload": narration_payload}
        )
        normalized["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
        normalized["presentation_intent_parse_source"] = provider_intent_source
        response_candidate, response_source = _find_current_action_response_candidate(
            {**payload, "narration_payload": narration_payload}
        )
        if response_candidate:
            normalized["current_action_response"] = _normalize_current_action_response(response_candidate)
            normalized["current_action_response_parse_source"] = response_source
        if isinstance(payload.get("npc_response_architecture_ack"), dict):
            normalized["npc_response_architecture_ack"] = _safe_dict(payload.get("npc_response_architecture_ack"))
        elif isinstance(narration_payload.get("npc_response_architecture_ack"), dict):
            normalized["npc_response_architecture_ack"] = _safe_dict(narration_payload.get("npc_response_architecture_ack"))

    advisory_payload = _safe_dict(
        payload.get("advisory")
        or payload.get("advisory_payload")
        or payload.get("deferred_advisory")
        or payload.get("advisory_candidates")
    )
    if advisory_payload:
        for key in (
            "candidates",
            "semantic_intent_candidates",
            "relationship_delta_candidates",
            "memory_candidates",
            "world_signal_candidates",
            "future_hook_candidates",
        ):
            candidate_list = advisory_payload.get(key)
            if isinstance(candidate_list, list):
                normalized[key] = candidate_list

    return normalized


def _combined_payload_has_useful_content(payload: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    return bool(
        _has_expected_combined_provider_keys(payload)
        or
        _safe_str(payload.get("narration"))
        or _safe_str(payload.get("action"))
        or _safe_dict(payload.get("npc"))
        or _candidate_arrays_present(payload)
    )


def _decode_provider_json_string(value: str) -> str:
    if not isinstance(value, str):
        return ""
    try:
        import json

        return _safe_str(json.loads(f'"{value}"')).strip()
    except Exception:
        try:
            return bytes(value, "utf-8").decode("unicode_escape").strip()
        except Exception:
            return value.strip()


def _extract_provider_string_field(text: str, field_name: str, max_chars: int = 2000) -> str:
    import re

    if not isinstance(text, str) or not field_name:
        return ""
    pattern = r'"' + re.escape(field_name) + r'"\s*:\s*"((?:\\.|[^"\\])*)"'
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return ""
    return _decode_provider_json_string(match.group(1))[:max_chars].strip()


def _extract_provider_bool_field(text: str, field_name: str) -> bool | None:
    import re

    if not isinstance(text, str) or not field_name:
        return None
    pattern = r'"' + re.escape(field_name) + r'"\s*:\s*(true|false)'
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _extract_provider_npc_object_from_text(text: str) -> Dict[str, Any]:
    import re

    if not isinstance(text, str):
        return {}
    npc_match = re.search(r'"npc"\s*:\s*\{(?P<body>.*?)\}', text, flags=re.DOTALL)
    if not npc_match:
        return {}
    body = npc_match.group("body")
    speaker = _extract_provider_string_field("{" + body + "}", "speaker", max_chars=120)
    line = _extract_provider_string_field("{" + body + "}", "line", max_chars=600)
    if not speaker and not line:
        return {}
    return {"speaker": speaker, "line": line}


def _repair_truncated_json_object_text(text: str) -> str:
    """Best-effort close for provider JSON that was cut off near the end.

    This is intentionally conservative: it never invents field values.  It only
    closes an open string, drops a trailing dangling key separator, and appends
    the missing object/array delimiters so json.loads gets one more chance.
    """
    if not isinstance(text, str) or not text.strip():
        return ""
    cleaned = text.strip()
    start = cleaned.find("{")
    if start < 0:
        return ""
    candidate = cleaned[start:]

    in_string = False
    escape = False
    stack: List[str] = []
    for char in candidate:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]" and stack and stack[-1] == char:
            stack.pop()

    repaired = candidate.rstrip()
    if in_string:
        repaired += '"'
    repaired = repaired.rstrip()
    while repaired and repaired[-1] in {":", ","}:
        repaired = repaired[:-1].rstrip()
    repaired += "".join(reversed(stack))
    return repaired


def _try_parse_repaired_combined_json(text: str) -> Dict[str, Any]:
    import json

    repaired = _repair_truncated_json_object_text(text)
    if not repaired:
        return {}
    try:
        parsed = json.loads(repaired)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    normalized = _extract_nested_combined_payload(parsed)
    if not (_combined_payload_has_useful_content(normalized) or _has_expected_combined_provider_keys(parsed)):
        return {}
    normalized["ok"] = True
    normalized["partial"] = True
    normalized["json_repair_applied"] = True
    normalized.setdefault("raw_provider_shape_keys", sorted(list(parsed.keys()))[:80])
    return normalized


def _salvage_combined_narration_from_text(text: str) -> Dict[str, Any]:
    """Recover useful combined payload fields from malformed provider JSON.

    Local providers sometimes return a nearly complete object but omit a final
    brace or truncate one candidate array.  Combined background output is
    non-authoritative, so it is safer to salvage complete visible fields
    (narration/action/npc/intent/ack) than to discard the whole provider result
    and count the turn as deterministic fallback.  Incomplete strings are not
    displayed; they are ignored and the deterministic runtime fallback can still
    handle the turn.
    """
    if not isinstance(text, str):
        return {}

    repaired = _try_parse_repaired_combined_json(text)
    if repaired:
        return repaired

    narration = _extract_provider_string_field(text, "narration", max_chars=2200)
    action = _extract_provider_string_field(text, "action", max_chars=700)
    reward = _extract_provider_string_field(text, "reward", max_chars=300)
    npc = _extract_provider_npc_object_from_text(text)

    category = _extract_provider_string_field(text, "primary_category", max_chars=80)
    intent_reason = _extract_provider_string_field(text, "reason", max_chars=240)
    response_reason = _extract_provider_string_field(text, "reason", max_chars=240)

    if not (narration or action or _safe_str(npc.get("line"))):
        return {}

    payload: Dict[str, Any] = {
        "ok": True,
        "partial": True,
        "regex_salvage_applied": True,
        "narration": narration or "The scene settles after the action.",
        "action": action or "The action has been resolved.",
        "npc": npc or {"speaker": "", "line": ""},
        "reward": reward,
        "followup_hooks": [],
    }
    if category:
        payload["presentation_intent"] = _normalize_presentation_intent(
            {
                "primary_category": category,
                "confidence": 0.45,
                "reason": intent_reason or "salvaged_from_partial_provider_json",
            }
        )
        payload["presentation_intent_parse_source"] = "partial_json_regex.primary_category"

    addresses = _extract_provider_bool_field(text, "npc_line_addresses_current_action")
    if addresses is None:
        addresses = _extract_provider_bool_field(text, "addresses_current_action")
    if addresses is not None:
        payload["current_action_response"] = _normalize_current_action_response(
            {
                "required_focus": [],
                "npc_line_addresses_current_action": addresses,
                "reason": response_reason or "salvaged_from_partial_provider_json",
            }
        )
        payload["current_action_response_parse_source"] = "partial_json_regex.current_action_response"

    used_contract = _extract_provider_bool_field(text, "used_current_turn_prompt_contract")
    answered_first = _extract_provider_bool_field(text, "answered_current_action_first")
    ignored_stale = _extract_provider_bool_field(text, "ignored_forbidden_stale_topics")
    if used_contract is not None or answered_first is not None or ignored_stale is not None:
        payload["prompt_contract_ack"] = {
            "used_current_turn_prompt_contract": bool(used_contract),
            "answered_current_action_first": bool(answered_first),
            "ignored_forbidden_stale_topics": bool(ignored_stale),
            "reason": "salvaged_from_partial_provider_json",
        }
    return payload

__all__ = [name for name in globals() if not name.startswith("__")]
