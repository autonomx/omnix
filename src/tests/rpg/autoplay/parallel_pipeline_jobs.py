"""Split helpers for autoplay background pipeline."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405,F811
from tests.rpg.autoplay.parallel_pipeline_common import *
from tests.rpg.autoplay.parallel_pipeline_narration import *
from tests.rpg.autoplay.parallel_pipeline_provider_payloads import *
from tests.rpg.autoplay.parallel_pipeline_n11616 import *
from tests.rpg.autoplay.parallel_pipeline_n116161 import *
from tests.rpg.autoplay.parallel_pipeline_n11620 import *

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
    runtime_state: Dict[str, Any] | None = None,
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
                runtime_state=freeze_snapshot(_safe_dict(runtime_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                semantic_action_record=freeze_snapshot(_safe_dict(semantic_action_record)),
                turn_index=turn_index,
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
            diagnostics["prompt_debug"] = _safe_dict(provider_payload.get("prompt_debug"))
            diagnostics["current_turn_prompt_contract"] = _safe_dict(
                provider_payload.get("current_turn_prompt_contract")
            )
            diagnostics["prompt_contract_ack"] = _safe_dict(provider_payload.get("prompt_contract_ack"))
            diagnostics["context_packet_keys"] = (
                provider_payload.get("context_packet_keys")
                if isinstance(provider_payload.get("context_packet_keys"), list)
                else []
            )
            diagnostics["profile_context_summary"] = _safe_dict(
                provider_payload.get("profile_context_summary")
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
            presentation_intent = _normalize_presentation_intent(provider_payload.get("presentation_intent"))
            current_action_response = _normalize_current_action_response(
                provider_payload.get("current_action_response")
            )
            diagnostics["provider_intent_parse_source"] = _safe_str(
                provider_payload.get("presentation_intent_parse_source")
            ) or "missing"
            diagnostics["current_action_response_parse_source"] = _safe_str(
                provider_payload.get("current_action_response_parse_source")
            ) or "missing"
            diagnostics["provider_intent_missing"] = presentation_intent.get("primary_category") == "general" and not presentation_intent.get("secondary_categories")
            diagnostics["provider_intent_general"] = presentation_intent.get("primary_category") == "general"
            narration_payload = {
                "format_version": "rpg_narration_v2",
                "source": "provider_runtime_narration",
                "presentation_intent": presentation_intent,
                "current_action_response": current_action_response,
                "prompt_contract_ack": _safe_dict(provider_payload.get("prompt_contract_ack")),
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
            narration_payload["presentation_intent"] = {
                "format_version": "presentation_intent_v1",
                "primary_category": "general",
                "secondary_categories": [],
                "confidence": 0.0,
                "reason": "deterministic_fallback_no_provider_intent",
            }
            fallback_contract = build_current_turn_prompt_contract(
                player_action=player_action,
                turn_contract=_safe_dict(turn_contract),
                semantic_action_record=_safe_dict(semantic_action_record),
            )
            diagnostics["current_turn_prompt_contract"] = fallback_contract
            narration_payload["current_action_response"] = {
                "format_version": "current_action_response_v1",
                "required_focus": _safe_list(fallback_contract.get("required_focus")),
                "npc_line_addresses_current_action": False,
                "reason": "deterministic_fallback_no_provider_response_focus",
            }
            narration_payload["prompt_contract_ack"] = {
                "used_current_turn_prompt_contract": False,
                "answered_current_action_first": False,
                "ignored_forbidden_stale_topics": False,
                "reason": "deterministic_fallback_no_provider_response",
            }
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
            "presentation_intent": _safe_dict(narration_payload.get("presentation_intent")),
            "current_action_response": _safe_dict(narration_payload.get("current_action_response")),
            "prompt_contract_ack": _safe_dict(narration_payload.get("prompt_contract_ack") or diagnostics.get("prompt_contract_ack")),
            "current_turn_prompt_contract": _safe_dict(diagnostics.get("current_turn_prompt_contract")),
            "prompt_debug": _safe_dict(diagnostics.get("prompt_debug")),
            "llm_fallback_diagnostics": {
                "format_version": "llm_fallback_diagnostics_v1",
                "source": source,
                "fallback_source": "llm_valid" if source == "provider_combined_background_llm" else "deterministic_fallback",
                "reason": _safe_str(diagnostics.get("fallback_reason") or diagnostics.get("provider_payload_error") or "llm_valid"),
                "valid_known_reason": bool(
                    source == "provider_combined_background_llm"
                    or _safe_str(diagnostics.get("fallback_reason") or diagnostics.get("provider_payload_error"))
                    in {"provider_missing_or_not_preferred", "provider_missing_or_unsupported", "provider_empty_combined_response", "provider_combined_unavailable"}
                ),
            },
            "profile_context_summary": _safe_dict(diagnostics.get("profile_context_summary")),
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

__all__ = [name for name in globals() if not name.startswith("__")]
