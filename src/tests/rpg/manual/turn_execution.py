from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict

from tests.rpg.manual import output_artifacts
from tests.rpg.manual.perf_trace import (
    record_manual_harness_trace,
    record_manual_harness_trace_stack,
    traced_manual_stage,
)
from tests.rpg.manual.safe import _safe_dict, _safe_str
from tests.rpg.manual.scenario_summary import _compact_result_for_summary
from tests.rpg.manual.story_event_queue_m25_m27_checks import (
    run_story_event_queue_m25_m27_check,
)
from tests.rpg.manual.summary_sanitizer import sanitize_turn_for_summary
from tests.rpg.manual.token_usage import _record_token_usage


def _timestamped_print(*args, **kwargs):
    """Print with timestamp prefix."""
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{timestamp}]", *args, **kwargs)


def _trace_value_shape(value):
    if isinstance(value, dict):
        return {
            "type": "dict",
            "keys": sorted([str(k) for k in value.keys()])[:50],
        }
    if isinstance(value, list):
        return {"type": "list", "len": len(value)}
    return {"type": type(value).__name__}


def _get_apply_turn() -> Callable:
    """Robustly locate apply_turn from the actual module path."""
    candidates = [
        ("app.rpg.session.runtime", "apply_turn"),
        ("app.rpg.session.service", "apply_turn"),
        ("app.rpg.session.turn_runtime", "apply_turn"),
        ("app.rpg.session.runtime_service", "apply_turn"),
    ]
    errors = []
    for module_name, attr in candidates:
        try:
            module = __import__(module_name, fromlist=[attr])
            fn = getattr(module, attr)
            if callable(fn):
                record_manual_harness_trace(
                    "manual_harness_selected_apply_turn",
                    module_name=module_name,
                    attr=attr,
                    callable_module=getattr(fn, "__module__", ""),
                    callable_name=getattr(fn, "__name__", ""),
                    callable_qualname=getattr(fn, "__qualname__", ""),
                )
                return fn
        except Exception as exc:
            errors.append(f"{module_name}.{attr}:{type(exc).__name__}:{exc}")
    raise ImportError("manual_apply_turn_not_found:" + " | ".join(errors))


def _extract_player_input_from_turn(turn: Any) -> str:
    if isinstance(turn, str):
        return turn.strip()
    turn_dict = _safe_dict(turn)
    return _safe_str(
        turn_dict.get("player")
        or turn_dict.get("input")
        or turn_dict.get("player_input")
    ).strip()


def _run_one_manual_turn(
    *,
    session_id: str,
    turn: Any,
    turn_index: int,
    scenario_name: str,
    target_channel: str,
    console_llm: bool = True,
    console_llm_raw: bool = True,
    console_llm_max_chars: int = 1200,
    story_event_queue_checks: list | None = None,
    include_raw_result: bool = False,
    artifact_detail: str = "debug",
    performance_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run a single turn for a manual scenario."""
    raw_turn = turn
    player_input = _extract_player_input_from_turn(raw_turn)

    record_manual_harness_trace_stack(
        "manual_harness_enter",
        function="_run_one_manual_turn",
    )

    record_manual_harness_trace("checkpoint_01_enter_run_one_manual_turn")

    if not player_input:
        record_manual_harness_trace("checkpoint_99_before_return", result_shape=_trace_value_shape({
            "turn_index": turn_index,
            "error": "no_player_input",
            "scenario_warnings": ["no_player_input"],
            "regression_warnings": ["no_player_input"],
        }))
        record_manual_harness_trace("manual_harness_exit")
        return {
            "turn_index": turn_index,
            "error": "no_player_input",
            "scenario_warnings": ["no_player_input"],
            "regression_warnings": ["no_player_input"],
        }

    with traced_manual_stage("manual_harness_total"):
        try:
            with traced_manual_stage("manual_harness_get_apply_turn"):
                record_manual_harness_trace_stack("checkpoint_03_before_get_apply_turn")
                apply_turn = _get_apply_turn()

            with traced_manual_stage("manual_harness_apply_turn"):
                record_manual_harness_trace_stack("checkpoint_04_before_apply_turn")
                result = apply_turn(
                    session_id=session_id,
                    player_input=player_input,
                    performance_override=performance_override,
                )

            record_manual_harness_trace("checkpoint_05_after_apply_turn", result_shape=_trace_value_shape(result))
            record_manual_harness_trace(
                "manual_harness_apply_turn_result_sources",
                llm_called=bool(
                    _safe_dict(result).get("llm_called")
                    or _safe_dict(_safe_dict(result).get("result")).get("llm_called")
                ),
                narration_source=_safe_dict(
                    _safe_dict(result).get("narration_payload")
                    or _safe_dict(result).get("structured_narration")
                ).get("source"),
            )

            with traced_manual_stage("manual_harness_record_token_usage"):
                _record_token_usage(
                scope="service_scenario",
                label=scenario_name,
                turn=turn_index,
                player_input=player_input,
                result=result,
            )

            # Log to console if requested
            if console_llm:
                with traced_manual_stage("manual_harness_console_llm_log"):
                    _log_llm_response(
                        scope="service",
                        label=scenario_name,
                        turn=turn_index,
                        player_input=player_input,
                        result=result,
                        raw=console_llm_raw,
                        max_chars=console_llm_max_chars,
                    )

            # Emit to output artifacts
            with traced_manual_stage("manual_harness_emit_artifacts"):
                output_artifacts._emit(f"TURN {turn_index}", channel=target_channel)
                output_artifacts._emit(f"PLAYER: {player_input}", channel=target_channel)
                narration = _extract_narration(result)
                output_artifacts._emit("NARRATION:", channel=target_channel)
                output_artifacts._emit(narration or "[no narration found]", channel=target_channel)
                output_artifacts._emit("RAW RESULT KEYS:", channel=target_channel)
                output_artifacts._emit(", ".join(sorted(result.keys())), channel=target_channel)

                # Run story event queue checks if provided
            story_event_queue_check_results = []
            if story_event_queue_checks:
                with traced_manual_stage("manual_harness_story_event_queue_checks"):
                    from tests.rpg.manual.session_helpers import get_active_session
                    session_obj = get_active_session(session_id)
                    for check_def in story_event_queue_checks:
                        check_result = run_story_event_queue_m25_m27_check(
                            check=check_def,
                            result=result,
                            session=session_obj,
                        )
                        story_event_queue_check_results.append(check_result)

            record_manual_harness_trace_stack("checkpoint_05_before_summary_or_narration")

            with traced_manual_stage("manual_harness_summary_compact_result"):
                compact_result = _compact_result_for_summary(
                    result,
                    detail=artifact_detail if artifact_detail in {"summary", "debug", "full"} else "debug",
                )

            with traced_manual_stage("manual_harness_summary_initial_build"):
                turn_summary = {
                    "turn_index": turn_index,
                    "player_input": player_input,
                    "result": compact_result,
                    "raw_result_keys": sorted([str(k) for k in _safe_dict(result).keys()]),
                    "story_event_queue_checks": story_event_queue_check_results,
                }

            if include_raw_result:
                with traced_manual_stage("manual_harness_include_raw_result_first_pass"):
                    turn_summary["raw_result"] = result
                    turn_summary["raw_narration"] = _extract_narration(result)
                    turn_summary["raw_turn_contract"] = _safe_dict(
                        result.get("turn_contract")
                        or _safe_dict(result.get("result")).get("turn_contract")
                    )
                    turn_summary["raw_npc"] = _safe_dict(
                        result.get("npc")
                        or _safe_dict(result.get("result")).get("npc")
                        or _safe_dict(result.get("turn_contract")).get("npc")
                    )
                    turn_summary["raw_narration_payload"] = _safe_dict(
                        result.get("narration_payload")
                        or result.get("structured_narration")
                        or result.get("narration_result")
                        or _safe_dict(result.get("result")).get("narration_payload")
                        or _safe_dict(result.get("result")).get("structured_narration")
                        or _safe_dict(result.get("session")).get("last_narration_payload")
                        or _safe_dict(result.get("session")).get("narration_payload")
                    )
                    turn_summary["llm_called"] = bool(
                        result.get("llm_called")
                        or _safe_dict(result.get("result")).get("llm_called")
                        or _safe_dict(turn_summary["raw_narration_payload"]).get("source") == "provider_runtime_narration"
                    )
                    turn_summary["runtime_narration_diagnostics"] = _safe_dict(
                        _safe_dict(turn_summary["raw_narration_payload"]).get("runtime_narration_diagnostics")
                    )

                # Apply sanitization for summary output
            with traced_manual_stage("manual_harness_sanitize_turn_for_summary"):
                turn_summary = sanitize_turn_for_summary(
                    turn_summary,
                    detail=artifact_detail if artifact_detail in {"summary", "debug", "full"} else "debug",
                )

            if include_raw_result:
                # The sanitizer is designed for compact manual scenario summaries.
                # Autoplay needs the raw apply_turn result for diagnostics and
                # progress evaluation, so restore these fields after sanitization.
                with traced_manual_stage("manual_harness_restore_raw_result_after_sanitize"):
                    turn_summary["raw_result"] = result
                    turn_summary["raw_narration"] = _extract_narration(result)
                    turn_summary["raw_turn_contract"] = _safe_dict(
                        result.get("turn_contract")
                        or _safe_dict(result.get("result")).get("turn_contract")
                    )
                    turn_summary["raw_npc"] = _safe_dict(
                        result.get("npc")
                        or _safe_dict(result.get("result")).get("npc")
                        or _safe_dict(result.get("turn_contract")).get("npc")
                    )
                    turn_summary["raw_narration_payload"] = _safe_dict(
                        result.get("narration_payload")
                        or result.get("structured_narration")
                        or result.get("narration_result")
                        or _safe_dict(result.get("result")).get("narration_payload")
                        or _safe_dict(result.get("result")).get("structured_narration")
                        or _safe_dict(result.get("session")).get("last_narration_payload")
                        or _safe_dict(result.get("session")).get("narration_payload")
                    )
                    turn_summary["llm_called"] = bool(
                        result.get("llm_called")
                        or _safe_dict(result.get("result")).get("llm_called")
                        or _safe_dict(turn_summary["raw_narration_payload"]).get("source") == "provider_runtime_narration"
                    )
                    turn_summary["runtime_narration_diagnostics"] = _safe_dict(
                        _safe_dict(turn_summary["raw_narration_payload"]).get("runtime_narration_diagnostics")
                    )

            record_manual_harness_trace("checkpoint_99_before_return", result_shape=_trace_value_shape(turn_summary))
            record_manual_harness_trace("manual_harness_exit")
            return turn_summary

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            output_artifacts._emit(f"TURN {turn_index} ERROR: {error_msg}", channel=target_channel)
            record_manual_harness_trace("checkpoint_99_before_return", result_shape=_trace_value_shape({
                "turn_index": turn_index,
                "player_input": player_input,
                "error": error_msg,
                "scenario_warnings": [f"turn_runtime_error:{error_msg}"],
                "regression_warnings": [f"turn_runtime_error:{error_msg}"],
            }))
            record_manual_harness_trace("manual_harness_exit")
            return {
                "turn_index": turn_index,
                "player_input": player_input,
                "error": error_msg,
                "scenario_warnings": [f"turn_runtime_error:{error_msg}"],
                "regression_warnings": [f"turn_runtime_error:{error_msg}"],
            }


def _extract_narration(result: Dict[str, Any]) -> str:
    """Extract narration text from result."""
    # Check direct keys
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in result subdict
    result_sub = _safe_dict(result.get("result"))
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result_sub.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in session runtime_state
    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    for key in ("last_narration", "last_turn_narration"):
        value = runtime_state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check authoritative
    authoritative = _safe_dict(result.get("authoritative"))
    for key in ("summary", "deterministic_fallback_narration"):
        value = authoritative.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _compact_json(value: Any) -> str:
    """Compact JSON representation."""
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _extract_visible_interaction_reason(result: Dict[str, Any]) -> str:
    """Extract visible interaction reason from result."""
    result_sub = _safe_dict(result.get("result"))
    interaction_result = _safe_dict(result_sub.get("interaction_result"))
    if interaction_result:
        reason = _safe_str(interaction_result.get("reason"))
        if reason and reason.strip() and reason not in ("", "unknown"):
            return reason.strip()
    return ""


def _one_line_text(value: Any, *, max_chars: int = 1200) -> str:
    text = "" if value is None else str(value)
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def _extract_raw_llm_text(result: Dict[str, Any]) -> str:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    raw_text = (
        raw_payload.get("raw_llm_narrative")
        or raw_payload.get("raw_llm_text")
        or result_sub.get("raw_llm_narrative")
        or result_sub.get("raw_llm_text")
    )
    if isinstance(raw_text, dict):
        return _compact_json(raw_text)
    return _safe_str(raw_text)


def _extract_raw_llm_request(result: Dict[str, Any]) -> str:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    raw_request = (
        raw_payload.get("raw_llm_request")
        or result_sub.get("raw_llm_request")
    )
    if isinstance(raw_request, dict):
        return _compact_json(raw_request)
    return _safe_str(raw_request)


def _extract_llm_console_response(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    narration_json = _safe_dict(raw_payload.get("narration_json"))
    npc = _safe_dict(narration_json.get("npc"))

    final_narration = _extract_narration(result)
    json_narration = _safe_str(narration_json.get("narration"))
    json_action = _safe_str(narration_json.get("action"))
    npc_speaker = _safe_str(npc.get("speaker"))
    npc_line = _safe_str(npc.get("line"))
    raw_text = _extract_raw_llm_text(result)
    raw_request = _extract_raw_llm_request(result)

    return {
        "final": final_narration,
        "json_narration": json_narration,
        "json_action": json_action,
        "npc_speaker": npc_speaker,
        "npc_line": npc_line,
        "raw": raw_text,
        "raw_request": raw_request,
        "used_llm": result_sub.get("used_llm"),
        "narration_status": result_sub.get("narration_status"),
    }


def _log_llm_response(
    *,
    scope: str,
    label: str,
    turn: int,
    player_input: str,
    result: Dict[str, Any],
    raw: bool = True,
    max_chars: int = 1200,
) -> None:
    """Log LLM response to console for debugging."""
    payload = _extract_llm_console_response(result)
    final_text = _one_line_text(payload.get("final"), max_chars=max_chars)
    json_narration = _one_line_text(payload.get("json_narration"), max_chars=max_chars)
    json_action = _one_line_text(payload.get("json_action"), max_chars=max_chars)

    visible_interaction_reason = _extract_visible_interaction_reason(result)

    if visible_interaction_reason and _safe_str(json_action) in {
        "",
        "unknown",
        "unknown_item",
        "item_not_found",
        "Action: You act.",
        "You act.",
    }:
        json_action = visible_interaction_reason

    if visible_interaction_reason and (
        _safe_str(json_action).startswith("Result: unknown_item")
        or _safe_str(json_action).startswith("Result: item_not_found")
    ):
        json_action = visible_interaction_reason
    npc_speaker = _safe_str(payload.get("npc_speaker"))
    npc_line = _one_line_text(payload.get("npc_line"), max_chars=max_chars)
    raw_text = _one_line_text(payload.get("raw"), max_chars=max_chars)
    raw_request = _one_line_text(payload.get("raw_request"), max_chars=max_chars)

    prefix = f"[manual][llm][{scope}:{label}][turn {turn}]"
    _timestamped_print("", flush=True)
    _timestamped_print(f"{prefix} PLAYER: {player_input}", flush=True)
    _timestamped_print(
        f"{prefix} used_llm={payload.get('used_llm')} "
        f"narration_status={payload.get('narration_status')}",
        flush=True,
    )
    if raw and raw_request:
        _timestamped_print(f"{prefix} RAW LLM REQUEST:", flush=True)
        _timestamped_print(raw_request, flush=True)
    if final_text:
        _timestamped_print(f"{prefix} FINAL RESPONSE:", flush=True)
        _timestamped_print(final_text, flush=True)
    elif json_narration or json_action or npc_line:
        _timestamped_print(f"{prefix} STRUCTURED RESPONSE:", flush=True)
        if json_narration:
            _timestamped_print(json_narration, flush=True)
        if json_action:
            _timestamped_print(f"Result: {json_action}", flush=True)
        if npc_speaker and npc_line:
            _timestamped_print(f'{npc_speaker}: "{npc_line}"', flush=True)
    else:
        _timestamped_print(f"{prefix} FINAL RESPONSE: [no narration found]", flush=True)
    if raw and raw_text:
        _timestamped_print(f"{prefix} RAW LLM RESPONSE:", flush=True)
        _timestamped_print(raw_text, flush=True)
    _timestamped_print("", flush=True)
