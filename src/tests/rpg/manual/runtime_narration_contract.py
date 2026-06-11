from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

RUNTIME_NARRATION_CONTRACT_VERSION = "runtime_narration_contract_v1"
RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE = "runtime_deferred_narration_drain_v1"
RUNTIME_DEFERRED_NARRATION_CONTEXT_VERSION = "runtime_deferred_narration_context_v1"
RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION = "runtime_transcript_provenance_normalization_v2"
RUNTIME_DEFERRED_NARRATION_MAX_CONTEXT_CHARS = 6500
RUNTIME_VISIBLE_REPAIR_NARRATION_SOURCES = frozenset({"dialogue_repaired", "quest_repaired", "survival_repaired", "commerce_repaired", "commerce_followup_repaired", "service_repaired", "visible_response_repaired"})


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _source_requires_runtime_narration(source: Any) -> bool:
    text = _safe_str(source).strip()
    return text == "deferred_runtime_narration_pending" or text in RUNTIME_VISIBLE_REPAIR_NARRATION_SOURCES or text.endswith("_repaired")


def _narration_payload_text(payload: Mapping[str, Any]) -> str:
    payload = _safe_dict(payload)
    for key in ("narration", "final_narration", "rendered_narration", "text", "message"):
        text = _safe_str(payload.get(key)).strip()
        if text:
            return text
    return ""


def _payload_is_pending(payload: Mapping[str, Any]) -> bool:
    payload = _safe_dict(payload)
    status = _safe_str(payload.get("narration_status") or payload.get("status")).lower()
    return _safe_str(payload.get("source")) == "deferred_runtime_narration_pending" or status in {"pending", "queued"}


def _payload_is_completed_llm_narration(payload: Mapping[str, Any]) -> bool:
    payload = _safe_dict(payload)
    if not _narration_payload_text(payload) or _payload_is_pending(payload):
        return False
    source = _safe_str(payload.get("source"))
    status = _safe_str(payload.get("narration_status") or payload.get("status")).lower()
    return source in {"provider_runtime_narration", "deferred_llm_narration", "combat_narration"} or status == "completed"


def _iter_mapping_values(value: Any, *, max_depth: int = 6):
    if max_depth < 0:
        return
    if isinstance(value, Mapping):
        yield value
        for nested in value.values():
            yield from _iter_mapping_values(nested, max_depth=max_depth - 1)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_mapping_values(nested, max_depth=max_depth - 1)


def _find_completed_narration_payload(value: Any) -> dict[str, Any]:
    for item in _iter_mapping_values(value):
        payload = _safe_dict(item)
        if _payload_is_completed_llm_narration(payload):
            return payload
    return {}


def completed_provider_payload_for_turn(turn_summary: Mapping[str, Any]) -> dict[str, Any]:
    turn_summary = _safe_dict(turn_summary)
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    for payload in (
        _safe_dict(turn_summary.get("raw_narration_payload")),
        _safe_dict(raw_result.get("narration_payload")),
        _safe_dict(raw_result.get("structured_narration")),
        _safe_dict(_safe_dict(raw_result.get("result")).get("narration_payload")),
    ):
        if _payload_is_completed_llm_narration(payload):
            return payload
    return _find_completed_narration_payload(raw_result)


def _turn_requires_runtime_narration(turn_summary: Mapping[str, Any]) -> bool:
    turn_summary = _safe_dict(turn_summary)
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    nested = _safe_dict(raw_result.get("result"))
    if any(_source_requires_runtime_narration(src) for src in (turn_summary.get("narration_source"), raw_result.get("narration_source"), nested.get("narration_source"))):
        return True
    if _safe_str(raw_result.get("narration_status")).lower() in {"pending", "queued"}:
        return True
    for payload in (_safe_dict(turn_summary.get("raw_narration_payload")), _safe_dict(raw_result.get("narration_payload")), _safe_dict(raw_result.get("structured_narration")), _safe_dict(nested.get("narration_payload"))):
        if _payload_is_pending(payload):
            return True
    return False


_turn_has_pending_deferred_narration = _turn_requires_runtime_narration


def _clip_str(value: Any, *, max_chars: int = 900) -> str:
    text = _safe_str(value).strip()
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…[truncated]"


def _compact(value: Any, *, depth: int = 3, items: int = 8, chars: int = 700) -> Any:
    if depth < 0:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {str(k): _compact(v, depth=depth - 1, items=items, chars=chars) for k, v in list(value.items())[:items]}
    if isinstance(value, list):
        return [_compact(v, depth=depth - 1, items=items, chars=chars) for v in value[:items]]
    if isinstance(value, str):
        return _clip_str(value, max_chars=chars)
    return value if isinstance(value, (int, float, bool)) or value is None else _clip_str(value, max_chars=chars)


def grounded_runtime_narration_context(turn_summary: Mapping[str, Any]) -> dict[str, Any]:
    turn_summary = _safe_dict(turn_summary)
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    nested = _safe_dict(raw_result.get("result"))
    session = _safe_dict(raw_result.get("session"))
    state = _safe_dict(_safe_dict(session.get("simulation_state")).get("player_state"))
    context = {
        "format_version": RUNTIME_DEFERRED_NARRATION_CONTEXT_VERSION,
        "player_input": _clip_str(turn_summary.get("player_input"), max_chars=500),
        "turn_index": turn_summary.get("turn_index"),
        "action_type": _safe_str(nested.get("action_type") or raw_result.get("action_type")),
        "visible_interaction_reason": _safe_str(nested.get("visible_interaction_reason") or raw_result.get("visible_interaction_reason")),
        "resolved_result": _compact(nested or raw_result, depth=2),
        "npc": _compact(raw_result.get("npc") or turn_summary.get("raw_npc"), depth=2),
        "current_scene": _compact(_safe_dict(_safe_dict(session.get("runtime_state")).get("current_scene")), depth=2),
        "player_state": {"location_id": _safe_str(state.get("location_id")), "nearby_npc_ids": _safe_list(state.get("nearby_npc_ids"))[:8], "inventory_state": _compact(state.get("inventory_state"), depth=2)},
    }
    if len(json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)) > RUNTIME_DEFERRED_NARRATION_MAX_CONTEXT_CHARS:
        context["resolved_result"] = _compact(context.get("resolved_result"), depth=1, chars=300)
        context["context_trimmed"] = True
    return context


def classify_runtime_narration_error(error: Any) -> str:
    text = _safe_str(error).lower()
    if "n_keep" in text or "n_ctx" in text or "context length" in text or "context window" in text:
        return "deferred_narration_context_overflow"
    if "timeout" in text or "timed out" in text:
        return "deferred_narration_timeout"
    if "gateway" in text:
        return "live_llm_gateway_unavailable"
    return "deferred_narration_provider_error"


def generate_runtime_deferred_narration_payload(*, turn_summary: Mapping[str, Any], timeout_s: float = 45.0) -> dict[str, Any]:
    try:
        from app.rpg.llm_app_gateway import build_app_llm_gateway
        gateway = build_app_llm_gateway()
    except Exception as exc:
        gateway = None
        error = f"gateway_import_failed:{type(exc).__name__}:{exc}"
    if gateway is None:
        error = locals().get("error", "runtime_llm_gateway_unavailable")
        return {"source": RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE, "narration_status": "failed", "narration": "", "runtime_narration_diagnostics": {"provider_error_type": classify_runtime_narration_error(error), "provider_errors": [error], "provider_valid": False}}
    context = grounded_runtime_narration_context(turn_summary)
    try:
        text = _safe_str(gateway.generate("Write final grounded RPG narration for this already-resolved turn. Return only narration text.", context=context, timeout_s=timeout_s)).strip()
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
        return {"source": RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE, "narration_status": "failed", "narration": "", "runtime_narration_diagnostics": {"provider_error_type": classify_runtime_narration_error(error), "provider_errors": [error], "provider_valid": False}}
    return {"format_version": "rpg_narration_v2", "source": "provider_runtime_narration", "narration_status": "completed", "narration": text, "runtime_narration_diagnostics": {"provider_valid": True, "provider_errors": [], "context_char_count": len(json.dumps(context, default=str))}}


def apply_completed_narration_payload(turn_summary: dict[str, Any], payload: Mapping[str, Any]) -> None:
    payload = deepcopy(_safe_dict(payload))
    text = _narration_payload_text(payload).strip()
    if not text:
        return
    payload["source"] = _safe_str(payload.get("source") or "provider_runtime_narration")
    payload["narration_status"] = "completed"
    payload["narration"] = text
    turn_summary.update({"raw_narration": text, "raw_narration_payload": deepcopy(payload), "llm_called": True, "narration_source": payload["source"], "narration_status": "completed"})
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    if raw_result:
        raw_result.update({"narration": text, "final_narration": text, "narration_status": "completed", "llm_called": True, "narration_source": payload["source"], "narration_payload": deepcopy(payload), "structured_narration": deepcopy(payload)})
        nested = _safe_dict(raw_result.get("result"))
        if nested:
            nested.update({"narration": text, "final_narration": text, "narration_status": "completed", "llm_called": True, "narration_source": payload["source"], "narration_payload": deepcopy(payload)})
            raw_result["result"] = nested
        turn_summary["raw_result"] = raw_result
        if "result" in turn_summary:
            turn_summary["result"] = raw_result


def drain_deferred_runtime_narration_turn(*, turn_summary: dict[str, Any], session_id: str = "", turn_index: int = 0, player_input: str = "", drain_func: Callable[..., Mapping[str, Any] | None] | None = None) -> dict[str, Any]:
    requires = _turn_requires_runtime_narration(turn_summary)
    result = {"turn_index": int(turn_index or turn_summary.get("turn_index") or 0), "player_input": _safe_str(player_input or turn_summary.get("player_input")), "session_id": _safe_str(session_id), "pending_before": requires, "requires_provider_narration": requires, "before_source": _safe_str(turn_summary.get("narration_source")), "completed": False, "timed_out": False, "source": "not_pending", "error": "", "error_type": ""}
    if not requires:
        turn_summary["deferred_narration_drain"] = result
        return result
    payload = completed_provider_payload_for_turn(turn_summary)
    if not payload and drain_func is not None:
        payload = drain_func(turn_summary=turn_summary, session_id=session_id, turn_index=turn_index, player_input=player_input)
    if not payload:
        payload = generate_runtime_deferred_narration_payload(turn_summary=turn_summary)
    if _payload_is_completed_llm_narration(_safe_dict(payload)):
        apply_completed_narration_payload(turn_summary, _safe_dict(payload))
        result.update({"completed": True, "source": _safe_str(_safe_dict(payload).get("source") or "provider_runtime_narration")})
    else:
        diagnostics = _safe_dict(_safe_dict(payload).get("runtime_narration_diagnostics"))
        errors = _safe_list(diagnostics.get("provider_errors"))
        result.update({"timed_out": True, "source": _safe_str(_safe_dict(payload).get("source") or RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE), "error": _safe_str(errors[0] if errors else "runtime_narration_failed"), "error_type": _safe_str(diagnostics.get("provider_error_type") or classify_runtime_narration_error(errors[0] if errors else ""))})
    result["after_source"] = _safe_str(turn_summary.get("narration_source"))
    turn_summary["deferred_narration_drain"] = result
    return result


def normalize_runtime_narration_transcript_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = deepcopy(_safe_dict(payload))
    summary = {"format_version": RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION, "turn_count": 0, "normalized_count": 0, "already_normalized_count": 0, "late_repair_required_count": 0, "late_repair_completed_count": 0, "late_repair_timeout_count": 0, "skipped_count": 0, "error_types": [], "turns": []}
    turns = normalized.get("turns")
    if not isinstance(turns, list):
        summary["skipped_count"] = 1
        return normalized, summary
    summary["turn_count"] = len(turns)
    next_turns = []
    for index, item in enumerate(turns, start=1):
        if not isinstance(item, Mapping):
            summary["skipped_count"] += 1
            next_turns.append(item)
            continue
        turn = dict(item)
        before = _safe_str(turn.get("narration_source"))
        if _source_requires_runtime_narration(before) and not completed_provider_payload_for_turn(turn):
            drain = drain_deferred_runtime_narration_turn(turn_summary=turn, session_id=_safe_str(_safe_dict(normalized.get("summary")).get("session_id")), turn_index=int(turn.get("turn_index") or index), player_input=_safe_str(turn.get("player_input")))
            summary["late_repair_required_count"] += 1
            summary["late_repair_completed_count"] += int(bool(drain.get("completed")))
            summary["late_repair_timeout_count"] += int(bool(drain.get("timed_out")))
            if drain.get("error_type") and drain.get("error_type") not in summary["error_types"]:
                summary["error_types"].append(drain.get("error_type"))
        payload_dict = completed_provider_payload_for_turn(turn)
        if payload_dict:
            apply_completed_narration_payload(turn, payload_dict)
            after = _safe_str(turn.get("narration_source"))
            if before == after == "provider_runtime_narration" and turn.get("llm_called"):
                summary["already_normalized_count"] += 1
            else:
                summary["normalized_count"] += 1
            summary["turns"].append({"turn_index": int(turn.get("turn_index") or index), "before_source": before, "after_source": after, "llm_called": bool(turn.get("llm_called")), "late_repair_required": _source_requires_runtime_narration(before)})
        else:
            summary["skipped_count"] += 1
        next_turns.append(turn)
    normalized["turns"] = next_turns
    normalized["runtime_transcript_provenance_normalization"] = summary
    return normalized, summary


def normalize_runtime_narration_transcript_file(transcript_path: str | Path) -> dict[str, Any]:
    path = Path(transcript_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"format_version": RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION, "error": "transcript_not_found", "normalized_count": 0}
    except json.JSONDecodeError as exc:
        return {"format_version": RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION, "error": f"invalid_transcript_json:{exc}", "normalized_count": 0}
    normalized, summary = normalize_runtime_narration_transcript_payload(payload)
    if summary.get("normalized_count") or summary.get("already_normalized_count") or summary.get("late_repair_required_count"):
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return summary


def new_runtime_narration_contract_summary(*, enabled: bool) -> dict[str, Any]:
    return {"format_version": RUNTIME_NARRATION_CONTRACT_VERSION, "enabled": bool(enabled), "visible_repair_sources_requiring_provider": sorted(RUNTIME_VISIBLE_REPAIR_NARRATION_SOURCES), "deferred_narration_drain": {"format_version": "runtime_deferred_narration_drain_summary_v2", "enabled": bool(enabled), "pending_count": 0, "completed_count": 0, "timeout_count": 0, "visible_repair_required_count": 0, "error_types": [], "turns": []}, "transcript_provenance_normalization": {"format_version": RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION, "normalized_count": 0}}


def record_runtime_narration_drain(summary: dict[str, Any], drain_result: Mapping[str, Any]) -> None:
    drain = _safe_dict(summary.get("deferred_narration_drain"))
    if not drain:
        return
    if drain_result.get("pending_before"):
        drain["pending_count"] += 1
    if _source_requires_runtime_narration(drain_result.get("before_source")) and _safe_str(drain_result.get("before_source")) != "deferred_runtime_narration_pending":
        drain["visible_repair_required_count"] = int(drain.get("visible_repair_required_count") or 0) + 1
    if drain_result.get("completed"):
        drain["completed_count"] += 1
    if drain_result.get("timed_out"):
        drain["timeout_count"] += 1
    error_type = _safe_str(drain_result.get("error_type"))
    if error_type and error_type not in drain["error_types"]:
        drain["error_types"].append(error_type)
    drain["turns"].append(dict(drain_result))
    summary["deferred_narration_drain"] = drain
