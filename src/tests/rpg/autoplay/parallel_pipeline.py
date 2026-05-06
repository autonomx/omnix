from __future__ import annotations

import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.narration.runtime_narration_contract import build_runtime_narration_payload
try:
    from app.providers.base import ChatMessage
except Exception:
    ChatMessage = None
from app.rpg.advisory.candidates import (
    advisory_candidate_summary,
    build_deterministic_advisory_candidates,
    normalize_advisory_candidates,
    stable_json_for_prompt,
)
from tests.rpg.autoplay.checkpoints import validate_save_load_checkpoint
from tests.rpg.autoplay.performance import elapsed_ms, now_perf
from tests.rpg.autoplay.progress import state_digest


def _queue_timing(
    *,
    queued_at: float,
    started_at: float,
    finished_at: float,
) -> Dict[str, Any]:
    return {
        "queued_at": round(queued_at, 6),
        "started_at": round(started_at, 6),
        "finished_at": round(finished_at, 6),
        "queue_wait_ms": round((started_at - queued_at) * 1000.0, 3),
        "run_ms": round((finished_at - started_at) * 1000.0, 3),
        "total_ms": round((finished_at - queued_at) * 1000.0, 3),
    }


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def stable_json_for_prompt(value: Any, max_chars: int = 6000) -> str:
    import json

    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text


def compact_json_for_prompt(value: Any, max_chars: int = 6000) -> str:
    """Stable compact JSON for prompt context.

    This preserves information while removing whitespace/token waste.
    Section-level caps should be applied before this where possible.
    """
    import json

    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text


def _short_text(value: Any, max_chars: int = 600) -> str:
    text = _safe_str(value).strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "...[truncated]"
    return text


def _list_tail(value: Any, limit: int) -> List[Any]:
    values = value if isinstance(value, list) else []
    if limit <= 0:
        return []
    return values[-limit:]


def _dict_subset(value: Any, keys: List[str]) -> Dict[str, Any]:
    source = _safe_dict(value)
    return {key: source.get(key) for key in keys if key in source and source.get(key) not in (None, "", [], {}, {})}


def _safe_npc_name(npc: Any) -> str:
    if isinstance(npc, str):
        return npc
    npc_dict = _safe_dict(npc)
    return (
        _safe_str(npc_dict.get("name"))
        or _safe_str(npc_dict.get("id"))
        or _safe_str(npc_dict.get("npc_id"))
        or _safe_str(npc_dict.get("speaker"))
    )


def _compact_present_npcs(simulation_state: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    present = (
        _safe_list(simulation_state.get("present_npcs"))
        or _safe_list(simulation_state.get("nearby_npcs"))
        or _safe_list(simulation_state.get("visible_npcs"))
    )
    npcs_by_id = _safe_dict(simulation_state.get("npcs"))
    compact: List[Dict[str, Any]] = []

    for item in present[:limit]:
        npc_id = _safe_npc_name(item)
        npc_record = _safe_dict(npcs_by_id.get(npc_id)) or _safe_dict(item)
        compact.append(
            {
                "id": npc_id,
                "name": _safe_str(npc_record.get("name")) or npc_id,
                "role": _safe_str(npc_record.get("role") or npc_record.get("occupation")),
                "mood": _safe_str(npc_record.get("mood") or npc_record.get("emotional_state")),
                "relationship": _safe_dict(npc_record.get("relationship")),
            }
        )

    if not compact and npcs_by_id:
        for npc_id, npc_record_any in list(npcs_by_id.items())[:limit]:
            npc_record = _safe_dict(npc_record_any)
            compact.append(
                {
                    "id": str(npc_id),
                    "name": _safe_str(npc_record.get("name")) or str(npc_id),
                    "role": _safe_str(npc_record.get("role") or npc_record.get("occupation")),
                    "mood": _safe_str(npc_record.get("mood") or npc_record.get("emotional_state")),
                }
            )

    return [item for item in compact if item.get("id") or item.get("name")]


def _compact_scene_context(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    scene = _safe_dict(simulation_state.get("scene"))
    location = _safe_dict(simulation_state.get("location"))
    current_location = (
        _safe_str(simulation_state.get("current_location"))
        or _safe_str(location.get("name"))
        or _safe_str(scene.get("location"))
        or _safe_str(scene.get("name"))
    )
    return {
        "location": current_location,
        "scene_title": _safe_str(scene.get("title") or scene.get("name")),
        "scene_summary": _short_text(
            scene.get("summary") or scene.get("description") or simulation_state.get("scene_summary"),
            900,
        ),
        "time": _safe_str(simulation_state.get("time") or simulation_state.get("world_time")),
        "weather": _safe_str(simulation_state.get("weather")),
    }


def _compact_recent_events(simulation_state: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    raw_events = (
        _safe_list(simulation_state.get("recent_events"))
        or _safe_list(simulation_state.get("world_events"))
        or _safe_list(simulation_state.get("event_log"))
    )
    events = []
    for event in _list_tail(raw_events, limit):
        event_dict = _safe_dict(event)
        if event_dict:
            events.append(
                {
                    "kind": _safe_str(event_dict.get("kind") or event_dict.get("type")),
                    "summary": _short_text(
                        event_dict.get("summary")
                        or event_dict.get("description")
                        or event_dict.get("text"),
                        400,
                    ),
                }
            )
        elif isinstance(event, str):
            events.append({"summary": _short_text(event, 400)})
    return [event for event in events if event.get("summary")]


def _compact_player_visible_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player = _safe_dict(simulation_state.get("player"))
    inventory = _safe_dict(simulation_state.get("inventory") or player.get("inventory"))
    currency = _safe_dict(simulation_state.get("currency") or player.get("currency"))
    return {
        "name": _safe_str(player.get("name") or simulation_state.get("player_name")),
        "status": _safe_str(player.get("status")),
        "visible_conditions": _safe_list(player.get("conditions"))[:8],
        "inventory_item_count": len(_safe_list(inventory.get("items"))),
        "currency": currency,
    }


def _compact_turn_contract(turn_contract: Dict[str, Any]) -> Dict[str, Any]:
    contract = _safe_dict(turn_contract)
    semantic_action = _safe_dict(contract.get("semantic_action"))
    state_delta = _safe_dict(contract.get("state_delta"))
    return {
        "version": contract.get("version"),
        "player_input": _short_text(contract.get("player_input"), 500),
        "resolved_action": contract.get("resolved_action"),
        "resolved_result": contract.get("resolved_result"),
        "semantic_action": semantic_action,
        "service_result": contract.get("service_result"),
        "state_delta": _dict_subset(
            state_delta,
            ["summary", "changed_keys", "relationship_delta", "memory_delta", "world_signal_delta"],
        ),
        "narration_brief": _short_text(contract.get("narration_brief"), 700),
        "presentation": _dict_subset(_safe_dict(contract.get("presentation")), ["title", "summary", "npc"]),
    }


def build_combined_background_context_packet(
    *,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Quality-preserving compact context for combined background LLM.

    This intentionally keeps the highest-value world and turn facts while
    excluding raw session/debug/history blobs.
    """
    simulation_state = _safe_dict(simulation_state)
    turn_contract = _safe_dict(turn_contract)
    semantic_action_record = _safe_dict(semantic_action_record)

    return {
        "player_action": _short_text(player_action, 800),
        "scene": _compact_scene_context(simulation_state),
        "present_npcs": _compact_present_npcs(simulation_state, limit=6),
        "player_visible_state": _compact_player_visible_state(simulation_state),
        "recent_events": _compact_recent_events(simulation_state, limit=5),
        "turn_contract": _compact_turn_contract(turn_contract),
        "fast_semantic_action": semantic_action_record,
    }


def prompt_section_metrics(sections: Dict[str, str]) -> Dict[str, Any]:
    by_section: Dict[str, Dict[str, Any]] = {}
    total_chars = 0
    for name, text in sections.items():
        text_value = text if isinstance(text, str) else str(text)
        chars = len(text_value)
        total_chars += chars
        by_section[name] = {
            "chars": chars,
            # Rough heuristic; exact tokenizer is provider/model-dependent.
            "estimated_tokens": round(chars / 4.0, 1),
        }
    return {
        "total_chars": total_chars,
        "estimated_tokens": round(total_chars / 4.0, 1),
        "by_section": by_section,
    }


def _provider_shape(provider: Any) -> Dict[str, Any]:
    if provider is None:
        return {"present": False}
    return {
        "present": True,
        "type": type(provider).__name__,
        "module": getattr(type(provider), "__module__", ""),
        "has_chat_completion": callable(getattr(provider, "chat_completion", None)),
        "has_complete": callable(getattr(provider, "complete", None)),
        "provider_name": getattr(provider, "provider_name", ""),
        "provider_display_name": getattr(provider, "provider_display_name", ""),
    }


def freeze_snapshot(value: Any) -> Any:
    """Create a worker-owned copy so background jobs never touch live state."""
    return deepcopy(value)


def _queue_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    timings = [
        _safe_dict(row.get("queue_timing"))
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("queue_timing"), dict)
    ]
    if not timings:
        return {
            "count": 0,
            "avg_queue_wait_ms": 0.0,
            "max_queue_wait_ms": 0.0,
            "avg_run_ms": 0.0,
            "max_run_ms": 0.0,
            "avg_total_ms": 0.0,
            "max_total_ms": 0.0,
        }

    def avg(key: str) -> float:
        return round(sum(float(item.get(key) or 0.0) for item in timings) / len(timings), 3)

    def maxv(key: str) -> float:
        return round(max(float(item.get(key) or 0.0) for item in timings), 3)

    return {
        "count": len(timings),
        "avg_queue_wait_ms": avg("queue_wait_ms"),
        "max_queue_wait_ms": maxv("queue_wait_ms"),
        "avg_run_ms": avg("run_ms"),
        "max_run_ms": maxv("run_ms"),
        "avg_total_ms": avg("total_ms"),
        "max_total_ms": maxv("total_ms"),
    }


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


def _salvage_combined_narration_from_text(text: str) -> Dict[str, Any]:
    import re

    if not isinstance(text, str):
        return {}
    match = re.search(r'"narration"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
    if not match:
        return {}
    narration = match.group(1)
    try:
        narration = bytes(narration, "utf-8").decode("unicode_escape")
    except Exception:
        pass
    if not narration.strip():
        return {}
    return {
        "ok": True,
        "partial": True,
        "narration": narration.strip(),
        "action": "The action has been resolved.",
        "npc": {"speaker": "", "line": ""},
        "reward": "",
        "followup_hooks": [],
    }


def _provider_messages(messages: List[Dict[str, str]]) -> List[Any]:
    if ChatMessage is None:
        return messages
    converted: List[Any] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        try:
            converted.append(ChatMessage(role=role, content=content))
        except TypeError:
            converted.append(ChatMessage(role, content))
    return converted


def _build_provider_advisory_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {"ok": False, "error": "provider_missing_or_unsupported"}

    messages = [
        {
            "role": "system",
            "content": (
                "You are an RPG advisory extractor. Return JSON only. "
                "You may suggest candidates, but you must not assert authoritative outcomes. "
                "Do not grant items, currency, quest completion, damage, travel, or rewards. "
                "Return one JSON object and no markdown fences, no prose, no commentary."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract advisory candidates from this turn.\n\n"
                f"PLAYER_INPUT:\n{player_action}\n\n"
                f"TURN_CONTRACT_JSON:\n{stable_json_for_prompt(turn_contract)}\n\n"
                f"FAST_SEMANTIC_JSON:\n{stable_json_for_prompt(semantic_action_record)}\n\n"
                "Return JSON with optional arrays: semantic_intent_candidates, "
                "relationship_delta_candidates, memory_candidates, world_signal_candidates, "
                "future_hook_candidates.\n\n"
                "Example shape:\n"
                "{\n"
                '  "semantic_intent_candidates": [\n'
                '    {"intent": "inspect", "summary": "The player studies the room.", "confidence": 0.7}\n'
                "  ],\n"
                '  "future_hook_candidates": [\n'
                '    {"summary": "An NPC may respond to the player noticing suspicious details."}\n'
                "  ]\n"
                "}"
            ),
        },
    ]

    provider_messages = _provider_messages(messages)
    try:
        response = provider.chat_completion(messages=provider_messages, stream=False)
    except TypeError:
        response = provider.chat_completion(provider_messages, stream=False)

    content = _provider_text_from_response(response)
    if not content:
        return {"ok": False, "error": "provider_empty_advisory_response"}

    try:
        parsed = _extract_json_object_from_text(content)
        if isinstance(parsed, dict):
            parsed["ok"] = True
            return parsed
        return {"ok": False, "error": "provider_advisory_json_not_object", "raw": content[:1000]}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"provider_advisory_json_parse_error:{type(exc).__name__}: {exc}",
            "raw": content[:1000],
        }


def _build_combined_background_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    """One provider call that returns both narration and advisory candidates."""
    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {"ok": False, "error": "provider_missing_or_unsupported"}

    context_packet = build_combined_background_context_packet(
        player_action=player_action,
        simulation_state=simulation_state,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
    )
    context_json = compact_json_for_prompt(context_packet, max_chars=7000)
    schema_text = (
        "{"
        '"narration":"2-5 sentences describing the resolved scene without repeating player input.",'
        '"action":"Short result of the player action.",'
        '"npc":{"speaker":"","line":""},'
        '"reward":"",'
        '"followup_hooks":[],'
        '"semantic_intent_candidates":[{"intent":"","summary":"","confidence":0.0}],'
        '"relationship_delta_candidates":[{"target":"","axis":"trust","delta":0,"summary":""}],'
        '"memory_candidates":[{"owner":"","summary":"","importance":0.0}],'
        '"world_signal_candidates":[{"kind":"","summary":""}],'
        '"future_hook_candidates":[{"kind":"","summary":""}]'
        "}"
    )
    prompt_metrics = prompt_section_metrics(
        {
            "system_contract": "combined_background_worker_v1",
            "context_packet": context_json,
            "output_schema": schema_text,
        }
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are an RPG background enrichment worker. Return JSON only. "
                "You must not assert authoritative outcomes that are not in the turn contract. "
                "Do not grant items, currency, quest completion, damage, travel, or rewards. "
                "Return one JSON object and no markdown fences, no prose, no commentary. "
                "Maintain rich 2-5 sentence narration quality. Use only the provided compact context. "
                "Return compact candidate objects. Prefer at most 1 high-quality candidate per category. "
                "Do not include long explanations inside candidates."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create background narration and advisory candidates for this resolved RPG turn.\n\n"
                "COMPACT_CONTEXT_JSON:\n"
                f"{context_json}\n\n"
                "Return exactly this JSON shape:\n"
                f"{schema_text}\n\n"
                "Candidate limits: max 1 semantic_intent, max 1 relationship_delta, "
                "max 1 memory, max 1 world_signal, max 1 future_hook. "
                "Each candidate summary must be under 160 characters. "
                "Narration remains high quality and should not be shortened below 2 sentences."
            ),
        },
    ]

    provider_messages = _provider_messages(messages)
    try:
        response = provider.chat_completion(messages=provider_messages, stream=False)
    except TypeError:
        response = provider.chat_completion(provider_messages, stream=False)

    content = _provider_text_from_response(response)
    if not content:
        return {"ok": False, "error": "provider_empty_combined_response"}

    try:
        parsed = _extract_json_object_from_text(content)
        if isinstance(parsed, dict):
            normalized = _extract_nested_combined_payload(parsed)
            if (
                _combined_payload_has_useful_content(normalized)
                or _has_expected_combined_provider_keys(parsed)
            ):
                normalized["ok"] = True
                normalized.setdefault("raw_provider_shape_keys", sorted(list(parsed.keys()))[:80])
                normalized.setdefault("prompt_metrics", prompt_metrics)
                normalized.setdefault("context_packet_keys", sorted(list(context_packet.keys())))
                return normalized
            return {
                "ok": False,
                "error": "provider_combined_json_missing_useful_content",
                "raw": content[:1000],
                "parsed_keys": sorted(list(parsed.keys()))[:80],
                "prompt_metrics": prompt_metrics,
                "context_packet_keys": sorted(list(context_packet.keys())),
            }
        return {"ok": False, "error": "provider_combined_json_not_object", "raw": content[:4000]}
    except Exception as exc:
        salvaged = _salvage_combined_narration_from_text(content)
        if salvaged:
            salvaged["raw"] = content[:4000]
            salvaged["parse_error"] = f"{type(exc).__name__}: {exc}"
            salvaged["prompt_metrics"] = prompt_metrics
            salvaged["context_packet_keys"] = sorted(list(context_packet.keys()))
            return salvaged
        return {
            "ok": False,
            "error": f"provider_combined_json_parse_error:{type(exc).__name__}: {exc}",
            "raw": content[:4000],
            "prompt_metrics": prompt_metrics,
            "context_packet_keys": sorted(list(context_packet.keys())),
        }


def _deferred_advisory_job(
    *,
    queued_at: float,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    started = now_perf()
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "semantic_keys": sorted(list(_safe_dict(semantic_action_record).keys())),
    }
    try:
        payload: Dict[str, Any] = {}
        source = "deterministic_deferred_advisory"
        if prefer_provider and provider is not None:
            provider_started = now_perf()
            payload = _build_provider_advisory_payload(
                provider=provider,
                player_action=player_action,
                simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                semantic_action_record=freeze_snapshot(_safe_dict(semantic_action_record)),
            )
            diagnostics["provider_advisory_ms"] = elapsed_ms(provider_started)
            diagnostics["provider_payload_error"] = _safe_str(payload.get("error"))
            if payload.get("ok"):
                source = "provider_deferred_advisory"
            else:
                source = "deterministic_deferred_advisory_fallback"

        if source == "provider_deferred_advisory":
            candidates = normalize_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                payload=_safe_dict(payload),
            )
        else:
            candidates = build_deterministic_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                semantic_action_record=_safe_dict(semantic_action_record),
            )

        finished = now_perf()
        return {
            "ok": True,
            "kind": "deferred_advisory",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": source,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "summary": advisory_candidate_summary(candidates),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }
    except Exception as exc:
        finished = now_perf()
        return {
            "ok": False,
            "kind": "deferred_advisory",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": "deferred_advisory_error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }


def _combined_background_llm_job(
    *,
    queued_at: float,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    print(f"Starting combined background LLM job for turn {turn_index}")
    started = now_perf()
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "semantic_keys": sorted(list(_safe_dict(semantic_action_record).keys())),
    }
    try:
        source = "combined_background_llm_fallback"
        provider_payload: Dict[str, Any] = {}
        if prefer_provider and provider is not None:
            provider_started = now_perf()
            provider_payload = _build_combined_background_payload(
                provider=provider,
                player_action=player_action,
                simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                semantic_action_record=freeze_snapshot(_safe_dict(semantic_action_record)),
            )
            diagnostics["provider_combined_ms"] = elapsed_ms(provider_started)
            diagnostics["provider_payload_error"] = _safe_str(provider_payload.get("error"))
            diagnostics["provider_raw_excerpt"] = _safe_str(provider_payload.get("raw"))[:4000]
            diagnostics["provider_payload_keys"] = (
                sorted(list(provider_payload.keys()))[:80]
                if isinstance(provider_payload, dict)
                else []
            )
            diagnostics["prompt_metrics"] = _safe_dict(provider_payload.get("prompt_metrics"))
            diagnostics["context_packet_keys"] = (
                provider_payload.get("context_packet_keys")
                if isinstance(provider_payload.get("context_packet_keys"), list)
                else []
            )
            diagnostics["provider_parsed_keys"] = (
                provider_payload.get("parsed_keys")
                if isinstance(provider_payload.get("parsed_keys"), list)
                else []
            )
            diagnostics["provider_raw_shape_keys"] = (
                provider_payload.get("raw_provider_shape_keys")
                if isinstance(provider_payload.get("raw_provider_shape_keys"), list)
                else []
            )
            if provider_payload.get("ok"):
                source = "provider_combined_background_llm"
            else:
                source = "combined_background_llm_fallback"
        else:
            diagnostics["provider_payload_error"] = "provider_missing_or_not_preferred"
            source = "combined_background_llm_fallback"

        if source == "provider_combined_background_llm":
            narration_payload = {
                "format_version": "rpg_narration_v2",
                "source": "provider_runtime_narration",
                "narration": _safe_str(provider_payload.get("narration")) or "The scene settles after the action.",
                "action": _safe_str(provider_payload.get("action")) or "The action has been resolved.",
                "npc": _safe_dict(provider_payload.get("npc")),
                "reward": _safe_str(provider_payload.get("reward")),
                "followup_hooks": _normalize_followup_hooks(provider_payload.get("followup_hooks")),
            }
            candidates = normalize_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                payload=_safe_dict(provider_payload),
            )
            if not candidates:
                diagnostics["advisory_candidate_fallback_reason"] = "provider_combined_returned_no_candidates"
                candidates = build_deterministic_advisory_candidates(
                    session_id=session_id,
                    turn_index=turn_index,
                    player_input=player_action,
                    turn_contract=_safe_dict(turn_contract),
                    semantic_action_record=_safe_dict(semantic_action_record),
                )
        else:
            # Fallback keeps the same output shape and preserves correctness.
            diagnostics["fallback_reason"] = _safe_str(
                diagnostics.get("provider_payload_error")
            ) or "provider_combined_unavailable"
            narration_payload = build_runtime_narration_payload(
                provider=None,
                player_action=player_action,
                simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                prefer_provider=False,
            )
            candidates = build_deterministic_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                semantic_action_record=_safe_dict(semantic_action_record),
            )

        finished = now_perf()
        print(f"Finished combined background LLM job for turn {turn_index}")
        return {
            "ok": True,
            "kind": "combined_background_llm",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": source,
            "narration": _safe_str(narration_payload.get("narration")),
            "npc": _safe_dict(narration_payload.get("npc")),
            "narration_payload": narration_payload,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "advisory_summary": advisory_candidate_summary(candidates),
            "diagnostics": diagnostics,
            "prompt_metrics": _safe_dict(diagnostics.get("prompt_metrics")),
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }
    except Exception as exc:
        finished = now_perf()
        print(f"Error in combined background LLM job for turn {turn_index}: {exc}")
        diagnostics["exception"] = f"{type(exc).__name__}: {exc}"
        return {
            "ok": False,
            "kind": "combined_background_llm",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": "combined_background_llm_error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }


def _checkpoint_job(
    *,
    session_id: str,
    turn_index: int,
    checkpoint_dir: Any,
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    started = now_perf()
    try:
        result = validate_save_load_checkpoint(
            session_id=session_id,
            turn_index=turn_index,
            checkpoint_dir=checkpoint_dir,
            simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
        )
        result["kind"] = "checkpoint"
        result["turn_index"] = turn_index
        result["worker_ms"] = elapsed_ms(started)
        return result
    except Exception as exc:
        return {
            "ok": False,
            "kind": "checkpoint",
            "turn_index": turn_index,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "worker_ms": elapsed_ms(started),
        }


class AutoplayBackgroundPipeline:
    """Thread pool for non-authoritative autoplay jobs.

    The simulation turn still runs synchronously. Jobs submitted here must only
    receive frozen snapshots and may only return presentation, diagnostic,
    checkpoint, or report artifacts.
    """

    def __init__(self, *, background_workers: int = 4, provider_workers: int = 1) -> None:
        self.background_workers = max(1, int(background_workers or 1))
        self.provider_workers = max(1, int(provider_workers or 1))
        self._background_executor = ThreadPoolExecutor(
            max_workers=self.background_workers,
            thread_name_prefix="rpg-autoplay-bg",
        )
        self._provider_executor = ThreadPoolExecutor(
            max_workers=self.provider_workers,
            thread_name_prefix="rpg-autoplay-provider",
        )
        self._futures: List[Future] = []

    def submit_deferred_narration(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        turn_contract: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"narration:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _deferred_narration_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            prefer_provider=prefer_provider,
        )
        self._futures.append(future)
        return job_id

    def submit_checkpoint(
        self,
        *,
        session_id: str,
        turn_index: int,
        checkpoint_dir: Any,
        simulation_state: Dict[str, Any],
    ) -> str:
        job_id = f"checkpoint:{session_id}:{turn_index}"
        future = self._background_executor.submit(
            _checkpoint_job,
            session_id=session_id,
            turn_index=turn_index,
            checkpoint_dir=checkpoint_dir,
            simulation_state=freeze_snapshot(simulation_state),
        )
        self._futures.append(future)
        return job_id

    def submit_deferred_advisory(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        turn_contract: Dict[str, Any],
        semantic_action_record: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"advisory:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _deferred_advisory_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            semantic_action_record=freeze_snapshot(semantic_action_record),
            prefer_provider=prefer_provider,
        )
        self._futures.append(future)
        return job_id

    def submit_combined_background_llm(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        turn_contract: Dict[str, Any],
        semantic_action_record: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"combined_background_llm:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _combined_background_llm_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            semantic_action_record=freeze_snapshot(semantic_action_record),
            prefer_provider=prefer_provider,
        )
        self._futures.append(future)
        print(f"Submitted combined background LLM job {job_id}")
        return job_id

    def drain(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        futures = list(self._futures)
        self._futures.clear()
        for future in as_completed(futures):
            try:
                value = future.result()
                results.append(
                    value if isinstance(value, dict)
                    else {"ok": False, "error": "worker_returned_non_dict"}
                )
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "kind": "unknown",
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    }
                )
        return results

    def shutdown(self) -> None:
        self._provider_executor.shutdown(wait=True)
        self._background_executor.shutdown(wait=True)


def attach_background_results_to_transcript(
    transcript: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    by_turn = {
        int(row.get("turn_index") or 0): row
        for row in transcript
        if isinstance(row, dict)
    }
    summary = {
        "total_jobs": len(results),
        "ok_jobs": 0,
        "failed_jobs": 0,
        "narration_jobs": 0,
        "checkpoint_jobs": 0,
        "advisory_jobs": 0,
        "combined_background_llm_jobs": 0,
        "background_job_seconds": 0.0,
        "deferred_narration_sources": {},
        "deferred_narration_provider_present": 0,
        "deferred_narration_provider_missing": 0,
        "deferred_narration_payload_errors": {},
        "errors": [],
    }
    for result in results:
        if result.get("ok"):
            summary["ok_jobs"] += 1
        else:
            summary["failed_jobs"] += 1
            if result.get("error"):
                summary["errors"].append(result.get("error"))

        summary["background_job_seconds"] += float(result.get("worker_ms") or 0.0) / 1000.0
        turn_index = int(result.get("turn_index") or 0)
        row = by_turn.get(turn_index)
        if not row:
            continue

        if result.get("kind") == "deferred_narration":
            summary["narration_jobs"] += 1
            payload = _safe_dict(result.get("narration_payload"))
            diagnostics = _safe_dict(result.get("diagnostics"))
            source = _safe_str(payload.get("source")) or "unknown"
            summary["deferred_narration_sources"][source] = (
                int(summary["deferred_narration_sources"].get(source) or 0) + 1
            )
            provider_shape = _safe_dict(diagnostics.get("provider_shape"))
            if provider_shape.get("present"):
                summary["deferred_narration_provider_present"] += 1
            else:
                summary["deferred_narration_provider_missing"] += 1
            payload_error = (
                _safe_str(payload.get("error"))
                or _safe_str(payload.get("original_error"))
                or _safe_str(diagnostics.get("payload_error"))
                or _safe_str(diagnostics.get("payload_original_error"))
            )
            if payload_error:
                summary["deferred_narration_payload_errors"][payload_error] = (
                    int(summary["deferred_narration_payload_errors"].get(payload_error) or 0) + 1
                )
            row["deferred_narration_result"] = result
            row["narration_status"] = result.get("narration_status")
            row["deferred_narration_source"] = _safe_str(payload.get("source"))
            row["deferred_narration_diagnostics"] = diagnostics
            if result.get("ok") and result.get("narration"):
                # Do not overwrite row["turn_result"]. That object represents
                # the blocking/manual runtime result and is used to diagnose
                # whether deferred mode really avoided blocking provider
                # narration. Store background narration separately.
                row["resolved_narration"] = result.get("narration")
                row["resolved_narration_payload"] = result.get("narration_payload") or {}
                row["narration"] = result.get("narration")
        elif result.get("kind") == "checkpoint":
            summary["checkpoint_jobs"] += 1
            row["save_load_checkpoint"] = result
        elif result.get("kind") == "deferred_advisory":
            summary["advisory_jobs"] += 1
            row["deferred_advisory_result"] = result
            row["deferred_advisory_status"] = "ready" if result.get("ok") else "error"
        elif result.get("kind") == "combined_background_llm":
            summary["combined_background_llm_jobs"] += 1
            row["combined_background_llm_result"] = result
            print(f"Attaching combined background LLM result for turn {turn_index}")

            # Attach narration in the same slots used by split narration jobs.
            row["deferred_narration_result"] = {
                "ok": result.get("ok"),
                "kind": "deferred_narration",
                "session_id": result.get("session_id"),
                "turn_index": result.get("turn_index"),
                "narration_status": "ready" if result.get("ok") else "error",
                "narration": result.get("narration"),
                "npc": result.get("npc") or {},
                "narration_payload": result.get("narration_payload") or {},
                "diagnostics": result.get("diagnostics") or {},
                "worker_ms": result.get("worker_ms"),
                "queue_timing": result.get("queue_timing") or {},
            }
            row["narration_status"] = "ready" if result.get("ok") else "error"
            if result.get("ok") and result.get("narration"):
                row["resolved_narration"] = result.get("narration")
                row["resolved_narration_payload"] = result.get("narration_payload") or {}
                row["narration"] = result.get("narration")

            # Attach advisory in the same slots used by split advisory jobs.
            row["deferred_advisory_result"] = {
                "ok": result.get("ok"),
                "kind": "deferred_advisory",
                "session_id": result.get("session_id"),
                "turn_index": result.get("turn_index"),
                "source": result.get("source"),
                "candidate_count": result.get("candidate_count"),
                "candidates": result.get("candidates") or [],
                "summary": result.get("advisory_summary") or {},
                "diagnostics": result.get("diagnostics") or {},
                "worker_ms": result.get("worker_ms"),
                "queue_timing": result.get("queue_timing") or {},
            }
            row["deferred_advisory_status"] = "ready" if result.get("ok") else "error"

    provider_jobs = [
        result
        for result in results
        if result.get("kind") in {"deferred_narration", "deferred_advisory", "combined_background_llm"}
    ]
    summary["provider_queue_summary"] = _queue_summary(provider_jobs)
    summary["provider_queue_by_kind"] = {
        kind: _queue_summary([result for result in provider_jobs if result.get("kind") == kind])
        for kind in ("deferred_narration", "deferred_advisory", "combined_background_llm")
    }

    summary["background_job_seconds"] = round(summary["background_job_seconds"], 3)
    return summary