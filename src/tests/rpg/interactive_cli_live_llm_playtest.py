"""Phase 13.97+ — opt-in live LLM RPG playtest runner with quality evaluation.

This module intentionally does not run in normal deterministic CI unless the caller
explicitly opts in. It drives the existing interactive CLI campaign with scripted
commands, drains deferred live narration when requested, then evaluates the final
transcript with the deterministic live quality evaluator.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_cli_campaign as cli  # noqa: E402
from tests.rpg.interactive_cli_live_quality_eval import (  # noqa: E402
    evaluate_live_quality_transcript,
    read_live_quality_transcript,
    write_live_quality_eval_summary,
)

LIVE_LLM_PLAYTEST_VERSION = "rpg_live_llm_playtest_v1"
LIVE_LLM_PLAYTEST_STATUS_MARKER = "RPG_LIVE_LLM_PLAYTEST"
LIVE_LLM_PLAYTEST_ENV_FLAG = "RPG_RUN_LIVE_LLM_PLAYTEST"
LIVE_DEFERRED_NARRATION_DRAIN_SOURCE = "live_llm_playtest_deferred_narration_drain_v1"
LIVE_DEFERRED_NARRATION_CONTEXT_VERSION = "live_deferred_narration_context_v2"
LIVE_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION = "live_transcript_provenance_normalization_v1"
LIVE_DEFERRED_NARRATION_MAX_CONTEXT_CHARS = 6500
DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS = (
    "Bran, remember this: my trail name is Ash Lantern.",
    "I ask Bran what trouble he has heard on the road.",
    "I buy two rations for the trail.",
    "I head north toward the old road and watch for bandits.",
    "I ask what choice I should make next.",
)
LIVE_LLM_PLAYTEST_SCENARIO_PACKS: dict[str, tuple[str, ...]] = {
    "tavern-memory": (
        "Bran, remember this: my trail name is Ash Lantern.",
        "I ask Bran what trouble he has heard on the road tonight.",
        "I ask Bran what name he should use if he needs to warn me later.",
        "I ask what concrete lead I should follow next.",
    ),
    "commerce-travel": (
        "I ask Elara what trail food she recommends for the north road.",
        "I buy two rations and ask the exact price.",
        "I check my pack and coin before leaving the market.",
        "I head north toward the old road and watch for landmarks.",
        "I ask what choices I have now that I am on the road.",
    ),
    "combat-tension": (
        "I follow the bandit tracks north from the tavern.",
        "I draw my sword and warn the bandit to drop his weapon.",
        "I attack only if the bandit lunges first.",
        "I check whether the fight changed my injuries, gear, or reward.",
        "I ask what danger remains nearby.",
    ),
}


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_run_id() -> str:
    return f"live_llm_playtest_{uuid.uuid4().hex[:8]}"


def _default_output_dir(run_id: str) -> Path:
    return cli.DEFAULT_OUTPUT_ROOT / f"interactive-cli-live-llm-playtest-{run_id}"


def list_live_llm_playtest_scenario_packs() -> dict[str, list[str]]:
    """Return deterministic named live playtest scenario packs."""

    return {name: list(commands) for name, commands in sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS.items())}


def resolve_live_llm_playtest_scenario_pack(name: str) -> list[str]:
    """Resolve one named scenario pack or raise a stable ValueError."""

    key = _safe_str(name).strip()
    if not key:
        return []
    if key not in LIVE_LLM_PLAYTEST_SCENARIO_PACKS:
        available = ", ".join(sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS))
        raise ValueError(f"unknown_live_llm_playtest_scenario_pack:{key};available={available}")
    return list(LIVE_LLM_PLAYTEST_SCENARIO_PACKS[key])


def _load_commands(
    *,
    script_file: str | Path | None = None,
    commands: Sequence[str] | None = None,
    scenario_pack: str = "",
) -> list[str]:
    if script_file:
        return cli.read_scripted_commands(script_file)
    explicit = [_safe_str(command).strip() for command in commands or [] if _safe_str(command).strip()]
    if explicit:
        return explicit
    packed = resolve_live_llm_playtest_scenario_pack(scenario_pack)
    return packed or list(DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS)


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
        elif isinstance(node, list):
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
    """Return a compact JSON-safe snapshot for live narration prompts."""

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
        return [
            _compact_jsonable(item, max_depth=max_depth - 1, max_items=max_items, max_chars=max_chars)
            for item in value[:max_items]
        ] + ([{"__truncated_items__": len(value) - max_items}] if len(value) > max_items else [])
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


def _grounded_live_narration_context(turn_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact post-runtime context for deferred live narration drain."""

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
        "format_version": LIVE_DEFERRED_NARRATION_CONTEXT_VERSION,
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
    if len(encoded) <= LIVE_DEFERRED_NARRATION_MAX_CONTEXT_CHARS:
        return context
    context["context_trimmed"] = True
    for key in ("turn_contract", "recent_authoritative_facts", "forbidden_narration"):
        context.pop(key, None)
    context["resolved_result"] = _compact_jsonable(context.get("resolved_result"), max_depth=2, max_items=6, max_chars=300)
    context["player_state"] = _compact_jsonable(context.get("player_state"), max_depth=2, max_items=6, max_chars=300)
    return context


def _context_char_count(context: Mapping[str, Any]) -> int:
    return len(json.dumps(context, ensure_ascii=False, sort_keys=True, default=str))


def _classify_live_deferred_narration_error(error: Any) -> str:
    text = _safe_str(error).lower()
    if "n_keep" in text or "n_ctx" in text or "context length" in text or "context window" in text:
        return "deferred_narration_context_overflow"
    if "timeout" in text or "timed out" in text:
        return "deferred_narration_timeout"
    if "empty_live_deferred_narration" in text:
        return "empty_live_deferred_narration"
    if "live_llm_gateway_unavailable" in text:
        return "live_llm_gateway_unavailable"
    if "gateway_import_failed" in text:
        return "live_llm_gateway_import_failed"
    return "deferred_narration_provider_error"


def _failed_drain_payload(*, error: str, provider_attempted: bool, provider_present: bool, context_chars: int = 0) -> dict[str, Any]:
    error_type = _classify_live_deferred_narration_error(error)
    return {
        "source": LIVE_DEFERRED_NARRATION_DRAIN_SOURCE,
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


def _generate_live_deferred_narration_payload(
    *,
    turn_summary: Mapping[str, Any],
    timeout_s: float = 45.0,
) -> dict[str, Any]:
    """Best-effort compact live provider drain for deferred runtime narration."""

    try:
        from app.rpg.llm_app_gateway import build_app_llm_gateway
    except Exception as exc:  # pragma: no cover - import failure is environment-specific
        return _failed_drain_payload(error=f"gateway_import_failed:{type(exc).__name__}:{exc}", provider_attempted=False, provider_present=False)

    gateway = build_app_llm_gateway()
    if gateway is None:
        return _failed_drain_payload(error="live_llm_gateway_unavailable", provider_attempted=False, provider_present=False)

    context = _grounded_live_narration_context(turn_summary)
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
        return _failed_drain_payload(error="empty_live_deferred_narration", provider_attempted=True, provider_present=True, context_chars=context_chars)
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
            "context_format_version": LIVE_DEFERRED_NARRATION_CONTEXT_VERSION,
            "context_char_count": context_chars,
            "provider_call_diagnostics": {"source": LIVE_DEFERRED_NARRATION_DRAIN_SOURCE},
        },
    }


def _apply_completed_narration_payload(turn_summary: dict[str, Any], payload: Mapping[str, Any]) -> None:
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


def _completed_provider_payload_for_turn(turn_summary: Mapping[str, Any]) -> dict[str, Any]:
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


def normalize_deferred_live_narration_transcript_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize stale transcript-level provenance after deferred live narration drain."""

    normalized = deepcopy(_safe_dict(payload))
    summary = {
        "format_version": LIVE_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION,
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
        payload_dict = _completed_provider_payload_for_turn(turn)
        drain = _safe_dict(turn.get("deferred_narration_drain"))
        should_normalize = bool(drain.get("completed")) or bool(payload_dict)
        if not should_normalize:
            summary["skipped_count"] += 1
            next_turns.append(turn)
            continue
        before_source = _safe_str(turn.get("narration_source"))
        if payload_dict:
            _apply_completed_narration_payload(turn, payload_dict)
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
    normalized["live_transcript_provenance_normalization"] = summary
    return normalized, summary


def normalize_deferred_live_narration_transcript_file(transcript_path: str | Path) -> dict[str, Any]:
    path = Path(transcript_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "format_version": LIVE_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION,
            "error": "transcript_not_found",
            "normalized_count": 0,
        }
    except json.JSONDecodeError as exc:
        return {
            "format_version": LIVE_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION,
            "error": f"invalid_transcript_json:{exc}",
            "normalized_count": 0,
        }
    normalized, summary = normalize_deferred_live_narration_transcript_payload(payload)
    if summary.get("normalized_count") or summary.get("already_normalized_count"):
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return summary


def drain_deferred_live_narration_turn(
    *,
    turn_summary: dict[str, Any],
    session_id: str = "",
    turn_index: int = 0,
    player_input: str = "",
    drain_func: Callable[..., Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Resolve one pending deferred narration turn before artifacts are scored."""

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
            result["error_type"] = _classify_live_deferred_narration_error(result["error"])

    if not payload:
        payload = _find_completed_narration_payload(turn_summary)
    if not payload:
        payload = _generate_live_deferred_narration_payload(turn_summary=turn_summary)

    payload_dict = _safe_dict(payload)
    if _payload_is_completed_llm_narration(payload_dict):
        _apply_completed_narration_payload(turn_summary, payload_dict)
        result["completed"] = True
        result["source"] = _safe_str(payload_dict.get("source") or "provider_runtime_narration")
    else:
        result["timed_out"] = True
        result["source"] = _safe_str(payload_dict.get("source") or LIVE_DEFERRED_NARRATION_DRAIN_SOURCE)
        diagnostics = _safe_dict(payload_dict.get("runtime_narration_diagnostics"))
        errors = _safe_list(diagnostics.get("provider_errors"))
        if errors and not result["error"]:
            result["error"] = _safe_str(errors[0])
        result["error_type"] = _safe_str(diagnostics.get("provider_error_type") or _classify_live_deferred_narration_error(result["error"]))
    turn_summary["deferred_narration_drain"] = result
    return result


def _new_deferred_drain_summary() -> dict[str, Any]:
    return {
        "format_version": "live_deferred_narration_drain_summary_v2",
        "enabled": True,
        "pending_count": 0,
        "completed_count": 0,
        "timeout_count": 0,
        "error_types": [],
        "turns": [],
    }


def _build_deferred_narration_after_turn_hook(
    summary: dict[str, Any],
    *,
    drain_func: Callable[..., Mapping[str, Any] | None] | None = None,
):
    def after_turn_hook(**kwargs: Any) -> None:
        turn_summary = kwargs.get("turn_summary")
        if not isinstance(turn_summary, dict):
            return
        drain_result = drain_deferred_live_narration_turn(
            turn_summary=turn_summary,
            session_id=_safe_str(kwargs.get("session_id")),
            turn_index=int(kwargs.get("turn_index") or turn_summary.get("turn_index") or 0),
            player_input=_safe_str(kwargs.get("player_input") or turn_summary.get("player_input")),
            drain_func=drain_func,
        )
        if drain_result.get("pending_before"):
            summary["pending_count"] += 1
        if drain_result.get("completed"):
            summary["completed_count"] += 1
        if drain_result.get("timed_out"):
            summary["timeout_count"] += 1
        error_type = _safe_str(drain_result.get("error_type"))
        if error_type and error_type not in summary["error_types"]:
            summary["error_types"].append(error_type)
        summary["turns"].append(drain_result)

    return after_turn_hook


def render_live_llm_playtest_status_marker(result: Mapping[str, Any]) -> str:
    """Render a one-line marker for scraping live playtest logs."""

    quality = _safe_dict(result.get("quality"))
    ok = "true" if bool(result.get("ok")) else "false"
    skipped = "true" if bool(result.get("skipped")) else "false"
    turn_count = int(quality.get("turn_count") or result.get("turn_count") or 0)
    avg_score = float(quality.get("avg_score") or 0.0)
    fun_score = float(_safe_dict(quality.get("scores")).get("fun") or 0.0)
    quality_failures = quality.get("failures") if isinstance(quality.get("failures"), list) else []
    drain = _safe_dict(result.get("deferred_narration_drain"))
    drain_errors = _safe_list(drain.get("error_types"))
    error = _safe_str(
        result.get("error")
        or quality.get("error")
        or (drain_errors[0] if drain_errors else "")
        or (quality_failures[0] if quality_failures else "none")
    )
    return (
        f"[{LIVE_LLM_PLAYTEST_STATUS_MARKER}] ok={ok} skipped={skipped} "
        f"turn_count={turn_count} avg_score={avg_score:.3f} fun={fun_score:.3f} error={error}"
    )


def run_live_llm_playtest(
    *,
    turns: int | None = None,
    session_id: str = "",
    run_id: str = "",
    output_dir: str | Path | None = None,
    commands: Sequence[str] | None = None,
    script_file: str | Path | None = None,
    scenario_pack: str = "",
    allow_live: bool = False,
    reset_session: bool = True,
    console_llm: bool = False,
    seed_live_survival: bool = True,
    artifact_detail: str = "debug",
    summary_path: str | Path | None = None,
    defer_runtime_narration: bool = True,
    drain_deferred_narration: bool = True,
    deferred_narration_drain_func: Callable[..., Mapping[str, Any] | None] | None = None,
    campaign_runner: Any | None = None,
) -> dict[str, Any]:
    """Run an opt-in scripted live LLM playtest and evaluate its transcript."""

    if not allow_live and not _truthy_env(LIVE_LLM_PLAYTEST_ENV_FLAG):
        return {
            "format_version": LIVE_LLM_PLAYTEST_VERSION,
            "ok": False,
            "skipped": True,
            "error": "live_llm_playtest_not_enabled",
            "required_env": LIVE_LLM_PLAYTEST_ENV_FLAG,
        }

    try:
        scripted_commands = _load_commands(script_file=script_file, commands=commands, scenario_pack=scenario_pack)
    except ValueError as exc:
        return {
            "format_version": LIVE_LLM_PLAYTEST_VERSION,
            "ok": False,
            "skipped": False,
            "error": str(exc),
        }
    resolved_run_id = _safe_str(run_id).strip() or _default_run_id()
    resolved_session_id = _safe_str(session_id).strip() or f"interactive_cli_{resolved_run_id}"
    resolved_output_dir = Path(output_dir) if output_dir else _default_output_dir(resolved_run_id)
    resolved_turns = int(turns or len(scripted_commands) or len(DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS))
    runner = campaign_runner or cli.run_interactive_campaign
    deferred_drain_summary = _new_deferred_drain_summary()
    deferred_drain_summary["enabled"] = bool(defer_runtime_narration and drain_deferred_narration)
    after_turn_hook = (
        _build_deferred_narration_after_turn_hook(deferred_drain_summary, drain_func=deferred_narration_drain_func)
        if defer_runtime_narration and drain_deferred_narration
        else None
    )

    campaign_result = runner(
        turns=resolved_turns,
        session_id=resolved_session_id,
        output_dir=resolved_output_dir,
        scripted_commands=scripted_commands,
        reset_session=reset_session,
        console_llm=console_llm,
        include_raw_result=True,
        artifact_detail=artifact_detail,
        enable_llm_intent_fallback=True,
        seed_live_survival=seed_live_survival,
        defer_runtime_narration=defer_runtime_narration,
        after_turn_hook=after_turn_hook,
    )
    artifacts = _safe_dict(campaign_result.get("artifacts"))
    transcript_path = Path(_safe_str(artifacts.get("transcript_path")) or (resolved_output_dir / "interactive-transcript.json"))
    transcript_normalization = {
        "format_version": LIVE_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION,
        "normalized_count": 0,
    }
    if transcript_path.exists():
        transcript_normalization = normalize_deferred_live_narration_transcript_file(transcript_path)
        quality = read_live_quality_transcript(transcript_path)
    else:
        quality = evaluate_live_quality_transcript(campaign_result)
    resolved_summary_path = Path(summary_path) if summary_path else resolved_output_dir / "live-quality-summary.json"
    write_live_quality_eval_summary(result=quality, summary_path=resolved_summary_path)

    result = {
        "format_version": LIVE_LLM_PLAYTEST_VERSION,
        "ok": bool(quality.get("ok")),
        "skipped": False,
        "run_id": resolved_run_id,
        "session_id": resolved_session_id,
        "turn_count": int(quality.get("turn_count") or 0),
        "scenario_pack": _safe_str(scenario_pack).strip(),
        "commands": scripted_commands,
        "output_dir": str(resolved_output_dir),
        "transcript_path": str(transcript_path),
        "quality_summary_path": str(resolved_summary_path),
        "defer_runtime_narration": bool(defer_runtime_narration),
        "drain_deferred_narration": bool(drain_deferred_narration),
        "deferred_narration_drain": deferred_drain_summary,
        "transcript_provenance_normalization": transcript_normalization,
        "campaign_artifacts": artifacts,
        "quality": quality,
    }
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an opt-in scripted live LLM RPG playtest and evaluate transcript quality.")
    parser.add_argument("--turns", type=int, default=0, help="Number of scripted turns to run; defaults to the command count.")
    parser.add_argument("--session-id", default="", help="Optional session id. Defaults to interactive_cli_<run>.")
    parser.add_argument("--run-id", default="", help="Optional run id for artifact folder naming.")
    parser.add_argument("--output-dir", default="", help="Optional output directory for campaign artifacts.")
    parser.add_argument("--script-file", default="", help="Optional newline-delimited player commands for the live playtest.")
    parser.add_argument("--command", action="append", default=[], help="Scripted player command; may be repeated.")
    parser.add_argument("--scenario-pack", choices=sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS), default="", help="Named built-in live playtest command pack.")
    parser.add_argument("--list-scenario-packs", action="store_true", help="List built-in scenario packs and exit without running a provider.")
    parser.add_argument("--allow-live", action="store_true", help=f"Allow live provider execution without setting {LIVE_LLM_PLAYTEST_ENV_FLAG}=1.")
    parser.add_argument("--no-reset-session-state", action="store_true", help="Do not delete saved session files before starting.")
    parser.add_argument("--console-llm", action="store_true", help="Print manual LLM console diagnostics per turn.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival needs/items/currency.")
    parser.add_argument("--no-deferred-runtime-narration", action="store_true", help="Debug only: do not force deferred post-runtime LLM narration.")
    parser.add_argument("--no-drain-deferred-narration", action="store_true", help="Debug only: score artifacts without draining pending deferred narration first.")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    parser.add_argument("--summary-path", default="", help="Optional path to persist the live-quality summary JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.list_scenario_packs:
        print(json.dumps({"scenario_packs": list_live_llm_playtest_scenario_packs()}, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    result = run_live_llm_playtest(
        turns=int(args.turns or 0) or None,
        session_id=args.session_id,
        run_id=args.run_id,
        output_dir=args.output_dir or None,
        commands=args.command,
        script_file=args.script_file or None,
        scenario_pack=args.scenario_pack,
        allow_live=bool(args.allow_live),
        reset_session=not bool(args.no_reset_session_state),
        console_llm=bool(args.console_llm),
        seed_live_survival=not bool(args.no_live_survival_seed),
        defer_runtime_narration=not bool(args.no_deferred_runtime_narration),
        drain_deferred_narration=not bool(args.no_drain_deferred_narration),
        artifact_detail=args.artifact_detail,
        summary_path=args.summary_path or None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_live_llm_playtest_status_marker(result), file=sys.stderr)
    if result.get("skipped"):
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
