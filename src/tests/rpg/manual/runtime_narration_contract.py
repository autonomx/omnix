"""Phase 14.05 — shared manual-runtime narration contract helpers.

The interactive campaign runner owns this contract so live matrix tests exercise the
same path that writes runtime-driven campaign artifacts.  Live playtest wrappers may
orchestrate/scoring, but deferred narration drain and provenance normalization live
here.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

RUNTIME_NARRATION_CONTRACT_VERSION = "runtime_narration_contract_v1"
RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE = "runtime_deferred_narration_drain_v1"
RUNTIME_DEFERRED_NARRATION_CONTEXT_VERSION = "runtime_deferred_narration_context_v1"
RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION = "runtime_transcript_provenance_normalization_v1"
RUNTIME_DEFERRED_NARRATION_MAX_CONTEXT_CHARS = 6500


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _narration_payload_text(payload: Mapping[str, Any]) -> str:
    payload = _safe_dict(payload)
    for key in ("narration", "final_narration", "rendered_narration", "text", "message"):
        text = _safe_str(payload.get(key)).strip()
        if text:
            return text
    return ""


def _payload_is_pending(payload: Mapping[str, Any]) -> bool:
    payload = _safe_dict(payload)
    source = _safe_str(payload.get("source")).strip()
    status = _safe_str(payload.get("narration_status") or payload.get("status")).strip().lower()
    return source == "deferred_runtime_narration_pending" or status in {"pending", "queued"}


def _payload_is_completed_llm_narration(payload: Mapping[str, Any]) -> bool:
    payload = _safe_dict(payload)
    if not _narration_payload_text(payload):
        return False
    if _payload_is_pending(payload):
        return False
    source = _safe_str(payload.get("source")).strip()
    status = _safe_str(payload.get("narration_status") or payload.get("status")).strip().lower()
    return source in {"provider_runtime_narration", "deferred_llm_narration", "combat_narration"} or status == "completed"


def _iter_mapping_values(value: Any, *, max_depth: int = 6):
    seen: set[int] = set()

    def walk(node: Any, depth: int):
        if depth > max_depth or not isinstance(node, (Mapping, list)):
            return
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)
        if isinstance(node, Mapping):
            yield node
            for nested in node.values():
                yield from walk(nested, depth + 1)
        else:
            for nested in node:
                yield from walk(nested, depth + 1)

    yield from walk(value, 0)


def _find_completed_narration_payload(value: Any) -> dict[str, Any]:
    for item in _iter_mapping_values(value):
        payload = _safe_dict(item)
        if _payload_is_completed_llm_narration(payload):
            return payload
    return {}


def _turn_has_pending_deferred_narration(turn_summary: Mapping[str, Any]) -> bool:
    turn_summary = _safe_dict(turn_summary)
    if _safe_str(turn_summary.get("narration_source")) == "deferred_runtime_narration_pending":
        return True
    if _payload_is_pending(_safe_dict(turn_summary.get("raw_narration_payload"))):
        return True
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    if _safe_str(raw_result.get("narration_status")).lower() in {"pending", "queued"}:
        return True
    for key in ("narration_payload", "structured_narration", "narration_result"):
        if _payload_is_pending(_safe_dict(raw_result.get(key))):
            return True
    return False


def _clip_str(value: Any, *, max_chars: int = 900) -> str:
    text = _safe_str(value).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…[truncated]"


def _compact_jsonable(value: Any, *, max_depth: int = 3, max_items: int = 8, max_chars: int = 900) -> Any:
    if max_depth < 0:
        return "[truncated]"
    if isinstance(value, Mapping):
        compact: dict[str, Any] = {}
        for index, (key, nested) in enumerate(value.items()):
            if index >= max_items:
                compact["__truncated_items__"] = max(0, len(value) - max_items)
                break
            compact[_safe_str(key)] = _compact_jsonable(nested, max_depth=max_depth - 1, max_items=max_items, max_chars=max_chars)
        return compact
    if isinstance(value, list):
        items = [_compact_jsonable(item, max_depth=max_depth - 1, max_items=max_items, max_chars=max_chars) for item in value[:max_items]]
        if len(value) > max_items:
            items.append({"__truncated_items__": len(value) - max_items})
        return items
    if isinstance(value, str):
        return _clip_str(value, max_chars=max_chars)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _clip_str(value, max_chars=max_chars)


def _selected_result_fields(raw_result: Mapping[str, Any], resolved: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "ok",
        "action_type",
        "visible_interaction_reason",
        "location_id",
        "target_location_id",
        "service_kind",
        "commerce_kind",
        "price",
        "currency_delta",
        "inventory_delta",
        "xp_delta",
        "level_delta",
        "quest_delta",
        "memory_delta",
        "state_delta",
        "forbidden_narration",
    )
    selected: dict[str, Any] = {}
    for key in keys:
        if key in resolved:
            selected[key] = resolved.get(key)
        elif key in raw_result:
            selected[key] = raw_result.get(key)
    return _compact_jsonable(selected, max_depth=3, max_items=8, max_chars=700)


def grounded_runtime_narration_context(turn_summary: Mapping[str, Any]) -> dict[str, Any]:
    turn_summary = _safe_dict(turn_summary)
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    resolved = _safe_dict(raw_result.get("resolved_result") or _safe_dict(raw_result.get("result")))
    turn_contract = _safe_dict(turn_summary.get("raw_turn_contract") or raw_result.get("turn_contract"))
    session = _safe_dict(raw_result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state") or raw_result.get("runtime_state"))
    simulation_state = _safe_dict(session.get("simulation_state") or raw_result.get("simulation_state"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    narration_context = _safe_dict(raw_result.get("narration_context"))
    context = {
        "format_version": RUNTIME_DEFERRED_NARRATION_CONTEXT_VERSION,
        "player_input": _clip_str(turn_summary.get("player_input"), max_chars=500),
        "turn_index": turn_summary.get("turn_index"),
        "action_type": _safe_str(resolved.get("action_type") or raw_result.get("action_type")),
        "visible_interaction_reason": _safe_str(resolved.get("visible_interaction_reason") or raw_result.get("visible_interaction_reason")),
        "resolved_result": _selected_result_fields(raw_result, resolved),
        "turn_contract": _compact_jsonable(turn_contract, max_depth=2, max_items=8, max_chars=500),
        "combat_result": _compact_jsonable(raw_result.get("combat_result") or resolved.get("combat_result"), max_depth=3, max_items=8, max_chars=500),
        "travel_result": _compact_jsonable(raw_result.get("travel_result") or resolved.get("travel_result"), max_depth=3, max_items=8, max_chars=500),
        "service_result": _compact_jsonable(raw_result.get("service_result") or resolved.get("service_result"), max_depth=3, max_items=8, max_chars=500),
        "npc": _compact_jsonable(raw_result.get("npc") or turn_summary.get("raw_npc"), max_depth=2, max_items=8, max_chars=500),
        "current_scene": _compact_jsonable(runtime_state.get("current_scene"), max_depth=2, max_items=8, max_chars=500),
        "player_state": {
            "location_id": _safe_str(player_state.get("location_id")),
            "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids"))[:8],
            "inventory_state": _compact_jsonable(player_state.get("inventory_state"), max_depth=2, max_items=10, max_chars=400),
        },
        "recent_authoritative_facts": _compact_jsonable(_safe_list(narration_context.get("recent_authoritative_facts"))[:5], max_depth=2, max_items=5, max_chars=500),
        "forbidden_narration": _compact_jsonable(_safe_list(resolved.get("forbidden_narration"))[:12], max_depth=1, max_items=12, max_chars=240),
    }
    encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded) <= RUNTIME_DEFERRED_NARRATION_MAX_CONTEXT_CHARS:
        return context
    context["context_trimmed"] = True
    for key in ("turn_contract", "recent_authoritative_facts", "forbidden_narration"):
        context.pop(key, None)
    context["resolved_result"] = _compact_jsonable(context.get("resolved_result"), max_depth=2, max_items=6, max_chars=300)
    context["player_state"] = _compact_jsonable(context.get("player_state"), max_depth=2, max_items=6, max_chars=300)
    return context


def _context_char_count(context: Mapping[str, Any]) -> int:
    return len(json.dumps(context, ensure_ascii=False, sort_keys=True, default=str))


def classify_runtime_narration_error(error: Any) -> str:
    text = _safe_str(error).lower()
    if "n_keep" in text or "n_ctx" in text or "context length" in text or "context window" in text:
        return "deferred_narration_context_overflow"
    if "timeout" in text or "timed out" in text:
        return "deferred_narration_timeout"
    if "empty_runtime_deferred_narration" in text or "empty_live_deferred_narration" in text:
        return "empty_live_deferred_narration"
    if "live_llm_gateway_unavailable" in text or "runtime_llm_gateway_unavailable" in text:
        return "live_llm_gateway_unavailable"
    if "gateway_import_failed" in text:
        return "live_llm_gateway_import_failed"
    return "deferred_narration_provider_error"


def _failed_drain_payload(*, error: str, provider_attempted: bool, provider_present: bool, context_chars: int = 0) -> dict[str, Any]:
    error_type = classify_runtime_narration_error(error)
    return {
        "source": RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE,
        "narration_status": "failed",
        "narration": "",
        "runtime_narration_diagnostics": {
            "provider_attempted": bool(provider_attempted),
            "provider_present": bool(provider_present),
            "provider_valid": False,
            "provider_error_type": error_type,
            "context_char_count": int(context_chars or 0),
            "provider_errors": [error],
        },
    }


def generate_runtime_deferred_narration_payload(*, turn_summary: Mapping[str, Any], timeout_s: float = 45.0) -> dict[str, Any]:
    try:
        from app.rpg.llm_app_gateway import build_app_llm_gateway
    except Exception as exc:  # pragma: no cover - import failure is environment-specific
        return _failed_drain_payload(error=f"gateway_import_failed:{type(exc).__name__}:{exc}", provider_attempted=False, provider_present=False)

    gateway = build_app_llm_gateway()
    if gateway is None:
        return _failed_drain_payload(error="runtime_llm_gateway_unavailable", provider_attempted=False, provider_present=False)

    context = grounded_runtime_narration_context(turn_summary)
    context_chars = _context_char_count(context)
    prompt = (
        "Write the final player-visible RPG narration for this already-resolved turn.\n"
        "Use only the compact grounded context. Do not invent locations, rewards, injuries, NPCs, prices, or quest progress.\n"
        "If an NPC speaks, keep it consistent with the provided NPC/context.\n"
        "Return only narration text in 1-3 short paragraphs, with one concrete next choice when appropriate."
    )
    try:
        text = _safe_str(gateway.generate(prompt, context=context, timeout_s=timeout_s)).strip()
    except Exception as exc:  # pragma: no cover - provider failures are live-environment specific
        return _failed_drain_payload(error=f"{type(exc).__name__}:{exc}", provider_attempted=True, provider_present=True, context_chars=context_chars)
    if not text:
        return _failed_drain_payload(error="empty_runtime_deferred_narration", provider_attempted=True, provider_present=True, context_chars=context_chars)
    return {
        "format_version": "rpg_narration_v2",
        "source": "provider_runtime_narration",
        "narration_status": "completed",
        "narration": text,
        "npc": {},
        "runtime_narration_diagnostics": {
            "provider_attempted": True,
            "provider_present": True,
            "provider_valid": True,
            "provider_errors": [],
            "context_format_version": RUNTIME_DEFERRED_NARRATION_CONTEXT_VERSION,
            "context_char_count": context_chars,
            "provider_call_diagnostics": {"source": RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE},
        },
    }


def apply_completed_narration_payload(turn_summary: dict[str, Any], payload: Mapping[str, Any]) -> None:
    payload = deepcopy(_safe_dict(payload))
    text = _narration_payload_text(payload).strip()
    if not text:
        return
    payload.setdefault("format_version", "rpg_narration_v2")
    payload["source"] = _safe_str(payload.get("source") or "provider_runtime_narration")
    payload["narration_status"] = "completed"
    payload["narration"] = text
    diagnostics = _safe_dict(payload.get("runtime_narration_diagnostics"))
    diagnostics.setdefault("provider_attempted", True)
    diagnostics.setdefault("provider_valid", True)
    diagnostics.setdefault("provider_errors", [])
    payload["runtime_narration_diagnostics"] = diagnostics

    turn_summary["raw_narration"] = text
    turn_summary["raw_narration_payload"] = deepcopy(payload)
    turn_summary["runtime_narration_diagnostics"] = deepcopy(diagnostics)
    turn_summary["llm_called"] = True
    turn_summary["narration_source"] = payload["source"]
    turn_summary["narration_status"] = "completed"

    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    if raw_result:
        raw_result["narration"] = text
        raw_result["final_narration"] = text
        raw_result["narration_status"] = "completed"
        raw_result["llm_called"] = True
        raw_result["narration_source"] = payload["source"]
        raw_result["narration_payload"] = deepcopy(payload)
        raw_result["structured_narration"] = deepcopy(payload)
        nested = _safe_dict(raw_result.get("result"))
        if nested:
            nested["narration"] = text
            nested["final_narration"] = text
            nested["narration_status"] = "completed"
            nested["llm_called"] = True
            nested["narration_source"] = payload["source"]
            nested["narration_payload"] = deepcopy(payload)
            nested["structured_narration"] = deepcopy(payload)
            raw_result["result"] = nested
        turn_summary["raw_result"] = raw_result
        if "result" in turn_summary:
            turn_summary["result"] = raw_result


def completed_provider_payload_for_turn(turn_summary: Mapping[str, Any]) -> dict[str, Any]:
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    for key in ("narration_payload", "structured_narration", "narration_result"):
        payload = _safe_dict(raw_result.get(key))
        if _payload_is_completed_llm_narration(payload):
            return payload
    nested = _safe_dict(raw_result.get("result"))
    for key in ("narration_payload", "structured_narration", "narration_result"):
        payload = _safe_dict(nested.get(key))
        if _payload_is_completed_llm_narration(payload):
            return payload
    return _find_completed_narration_payload(raw_result)


def normalize_runtime_narration_transcript_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = deepcopy(_safe_dict(payload))
    summary = {
        "format_version": RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION,
        "turn_count": 0,
        "normalized_count": 0,
        "already_normalized_count": 0,
        "skipped_count": 0,
        "turns": [],
    }
    turns = normalized.get("turns")
    if not isinstance(turns, list):
        summary["skipped_count"] = 1
        return normalized, summary
    summary["turn_count"] = len(turns)
    next_turns: list[Any] = []
    for index, item in enumerate(turns, start=1):
        if not isinstance(item, Mapping):
            summary["skipped_count"] += 1
            next_turns.append(item)
            continue
        turn = dict(item)
        payload_dict = completed_provider_payload_for_turn(turn)
        drain = _safe_dict(turn.get("deferred_narration_drain"))
        should_normalize = bool(drain.get("completed")) or bool(payload_dict)
        if not should_normalize:
            summary["skipped_count"] += 1
            next_turns.append(turn)
            continue
        before_source = _safe_str(turn.get("narration_source"))
        if payload_dict:
            apply_completed_narration_payload(turn, payload_dict)
        after_source = _safe_str(turn.get("narration_source"))
        if before_source == after_source and after_source == "provider_runtime_narration" and bool(turn.get("llm_called")):
            summary["already_normalized_count"] += 1
        else:
            summary["normalized_count"] += 1
        summary["turns"].append(
            {
                "turn_index": int(turn.get("turn_index") or index),
                "before_source": before_source,
                "after_source": after_source,
                "llm_called": bool(turn.get("llm_called")),
            }
        )
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
    if summary.get("normalized_count") or summary.get("already_normalized_count"):
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return summary


def drain_deferred_runtime_narration_turn(
    *,
    turn_summary: dict[str, Any],
    session_id: str = "",
    turn_index: int = 0,
    player_input: str = "",
    drain_func: Callable[..., Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    pending = _turn_has_pending_deferred_narration(turn_summary)
    result = {
        "turn_index": int(turn_index or turn_summary.get("turn_index") or 0),
        "player_input": _safe_str(player_input or turn_summary.get("player_input")),
        "session_id": _safe_str(session_id),
        "pending_before": bool(pending),
        "completed": False,
        "timed_out": False,
        "source": "not_pending",
        "error": "",
        "error_type": "",
    }
    if not pending:
        turn_summary["deferred_narration_drain"] = result
        return result

    payload: Mapping[str, Any] | None = None
    if drain_func is not None:
        try:
            payload = drain_func(turn_summary=turn_summary, session_id=session_id, turn_index=turn_index, player_input=player_input)
        except Exception as exc:  # pragma: no cover - defensive hook isolation
            result["error"] = f"drain_func_error:{type(exc).__name__}:{exc}"
            result["error_type"] = classify_runtime_narration_error(result["error"])

    if not payload:
        payload = _find_completed_narration_payload(turn_summary)
    if not payload:
        payload = generate_runtime_deferred_narration_payload(turn_summary=turn_summary)

    payload_dict = _safe_dict(payload)
    if _payload_is_completed_llm_narration(payload_dict):
        apply_completed_narration_payload(turn_summary, payload_dict)
        result["completed"] = True
        result["source"] = _safe_str(payload_dict.get("source") or "provider_runtime_narration")
    else:
        result["timed_out"] = True
        result["source"] = _safe_str(payload_dict.get("source") or RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE)
        diagnostics = _safe_dict(payload_dict.get("runtime_narration_diagnostics"))
        errors = _safe_list(diagnostics.get("provider_errors"))
        if errors and not result["error"]:
            result["error"] = _safe_str(errors[0])
        result["error_type"] = _safe_str(diagnostics.get("provider_error_type") or classify_runtime_narration_error(result["error"]))
    turn_summary["deferred_narration_drain"] = result
    return result


def new_runtime_narration_contract_summary(*, enabled: bool) -> dict[str, Any]:
    return {
        "format_version": RUNTIME_NARRATION_CONTRACT_VERSION,
        "enabled": bool(enabled),
        "deferred_narration_drain": {
            "format_version": "runtime_deferred_narration_drain_summary_v1",
            "enabled": bool(enabled),
            "pending_count": 0,
            "completed_count": 0,
            "timeout_count": 0,
            "error_types": [],
            "turns": [],
        },
        "transcript_provenance_normalization": {
            "format_version": RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION,
            "normalized_count": 0,
        },
    }


def record_runtime_narration_drain(summary: dict[str, Any], drain_result: Mapping[str, Any]) -> None:
    drain = _safe_dict(summary.get("deferred_narration_drain"))
    if not drain:
        return
    if drain_result.get("pending_before"):
        drain["pending_count"] += 1
    if drain_result.get("completed"):
        drain["completed_count"] += 1
    if drain_result.get("timed_out"):
        drain["timeout_count"] += 1
    error_type = _safe_str(drain_result.get("error_type"))
    if error_type and error_type not in drain["error_types"]:
        drain["error_types"].append(error_type)
    drain["turns"].append(dict(drain_result))
    summary["deferred_narration_drain"] = drain
