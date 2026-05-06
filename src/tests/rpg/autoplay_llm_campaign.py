from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.rpg.player_action_context.runtime import build_player_action_context
from tests.rpg.autoplay.base_runtime_response import (
    build_autoplay_base_response,
)
from tests.rpg.autoplay.campaign_report import write_campaign_report
from tests.rpg.autoplay.checkpoints import (
    collect_state_bounds,
    validate_save_load_checkpoint,
)
from tests.rpg.autoplay.evaluators import (
    compute_progress_metrics,
    evaluate_autoplay_health,
)
from tests.rpg.autoplay.manual_turn_driver import (
    merge_autoplay_simulation_state,
    prepare_autoplay_manual_session,
    run_autoplay_manual_turn,
)
from tests.rpg.autoplay.parallel_pipeline import (
    AutoplayBackgroundPipeline,
    attach_background_results_to_transcript,
)
from tests.rpg.autoplay.performance import (
    elapsed_ms,
    now_perf,
    summarize_performance,
    timed_stage,
)
from tests.rpg.autoplay.player_agent import (
    build_player_agent_prompt,
    choose_fallback_player_action,
    parse_player_agent_response,
    validate_player_action_against_context,
)
from tests.rpg.autoplay.progress import classify_progress_delta, state_digest
from tests.rpg.autoplay.progress_quality import (
    classify_turn_progress_quality,
    compute_progress_quality_metrics,
    evaluate_progress_quality_health,
    post_objective_false_progress_warnings,
)
from tests.rpg.autoplay.provider_adapter import (
    call_provider_text,
    describe_provider_shape,
)
from tests.rpg.autoplay.reporting import write_autoplay_artifacts
from tests.rpg.autoplay.seeding import (
    available_campaign_seeds,
    resolve_campaign_seed_name,
    seed_campaign,
)
from tests.rpg.autoplay.story_hooks import (
    apply_autoplay_story_hooks,
    autoplay_story_hook_player_hints,
)
from tests.rpg.autoplay.story_variety import compute_story_variety_metrics
from tests.rpg.autoplay.strategy_profiles import (
    action_diversity_metrics,
    build_strategy_guidance,
    rerank_suggested_actions_for_strategy,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _autoplay_report_action_type(player_action: str) -> str:
    text = " ".join(str(player_action or "").lower().strip().split())
    if any(word in text for word in ["ask", "talk", "tell", "speak", "question", "report", "explain", "share", "approach"]):
        return "social"
    return "other"


def _digest_counts(value: Dict[str, Any]) -> Dict[str, int]:
    return _safe_dict(state_digest(_safe_dict(value)).get("counts"))


def _baseline_mismatch_warning(
    *,
    expected_state: Dict[str, Any],
    actual_before_state: Dict[str, Any],
) -> Dict[str, Any]:
    expected_counts = _digest_counts(expected_state)
    actual_counts = _digest_counts(actual_before_state)
    mismatch_keys = sorted(
        key
        for key in set(expected_counts) | set(actual_counts)
        if expected_counts.get(key) != actual_counts.get(key)
    )
    return {
        "ok": not mismatch_keys,
        "mismatch_keys": mismatch_keys,
        "expected_counts": expected_counts,
        "actual_counts": actual_counts,
    }


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _summarize_player_agent_trace(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "turns": 0,
        "fallback_turns": 0,
        "llm_turns": 0,
        "unknown_turns": 0,
        "avg_player_agent_ms": 0.0,
        "max_player_agent_ms": 0.0,
        "selected_source_counts": {},
        "fallback_reason_counts": {},
        "errors": {},
    }
    timings: List[float] = []
    for row in transcript:
        if not isinstance(row, dict):
            continue
        summary["turns"] += 1
        perf = _safe_dict(row.get("performance"))
        ms = float(perf.get("player_agent_ms") or 0.0)
        if ms:
            timings.append(ms)

        selected = _safe_dict(row.get("selected_player_action"))
        source = (
            _safe_str(selected.get("source"))
            or _safe_str(selected.get("agent_source"))
            or _safe_str(selected.get("mode"))
            or "unknown"
        )
        if source == "unknown" and selected.get("ok") is True and selected.get("raw"):
            source = "llm_player_agent"
        summary["selected_source_counts"][source] = (
            int(summary["selected_source_counts"].get(source) or 0) + 1
        )
        if "fallback" in source:
            summary["fallback_turns"] += 1
        elif "llm" in source or "provider" in source:
            summary["llm_turns"] += 1
        else:
            summary["unknown_turns"] += 1

        reason = _safe_str(selected.get("fallback_reason")) or _safe_str(selected.get("reason_code"))
        if reason:
            summary["fallback_reason_counts"][reason] = (
                int(summary["fallback_reason_counts"].get(reason) or 0) + 1
            )
        error = _safe_str(selected.get("error")) or _safe_str(selected.get("provider_error"))
        if error:
            summary["errors"][error] = int(summary["errors"].get(error) or 0) + 1

    if timings:
        summary["avg_player_agent_ms"] = round(sum(timings) / len(timings), 3)
        summary["max_player_agent_ms"] = round(max(timings), 3)
    return summary


def _summarize_deferred_narration_trace(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "turns": 0,
        "ok_jobs": 0,
        "failed_jobs": 0,
        "sources": {},
        "avg_worker_ms": 0.0,
        "max_worker_ms": 0.0,
        "provider_present": 0,
        "provider_missing": 0,
        "errors": {},
        "diagnostics_examples": [],
    }
    timings: List[float] = []
    for row in transcript:
        if not isinstance(row, dict):
            continue
        result = _safe_dict(row.get("deferred_narration_result"))
        if not result:
            continue
        summary["turns"] += 1
        if result.get("ok"):
            summary["ok_jobs"] += 1
        else:
            summary["failed_jobs"] += 1
        ms = float(result.get("worker_ms") or 0.0)
        if ms:
            timings.append(ms)
        payload = _safe_dict(result.get("narration_payload"))
        source = _safe_str(payload.get("source")) or "unknown"
        summary["sources"][source] = int(summary["sources"].get(source) or 0) + 1
        diagnostics = _safe_dict(result.get("diagnostics"))
        provider_shape = _safe_dict(diagnostics.get("provider_shape"))
        if provider_shape.get("present"):
            summary["provider_present"] += 1
        else:
            summary["provider_missing"] += 1
        error = (
            _safe_str(result.get("error"))
            or _safe_str(payload.get("error"))
            or _safe_str(payload.get("original_error"))
            or _safe_str(diagnostics.get("exception"))
            or _safe_str(diagnostics.get("payload_error"))
            or _safe_str(diagnostics.get("payload_original_error"))
        )
        if error:
            summary["errors"][error] = int(summary["errors"].get(error) or 0) + 1
        if len(summary["diagnostics_examples"]) < 3:
            summary["diagnostics_examples"].append(
                {
                    "turn_index": row.get("turn_index"),
                    "source": source,
                    "worker_ms": ms,
                    "provider_shape": provider_shape,
                    "payload_error": diagnostics.get("payload_error"),
                    "payload_original_error": diagnostics.get("payload_original_error"),
                }
            )
    if timings:
        summary["avg_worker_ms"] = round(sum(timings) / len(timings), 3)
        summary["max_worker_ms"] = round(max(timings), 3)
    return summary


def _summarize_deferred_advisory_trace(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "turns": 0,
        "ok_jobs": 0,
        "failed_jobs": 0,
        "sources": {},
        "candidate_count": 0,
        "candidate_kinds": {},
        "avg_worker_ms": 0.0,
        "max_worker_ms": 0.0,
        "errors": {},
    }
    timings: List[float] = []
    for row in transcript:
        result = _safe_dict(row.get("deferred_advisory_result"))
        if not result:
            continue
        summary["turns"] += 1
        if result.get("ok"):
            summary["ok_jobs"] += 1
        else:
            summary["failed_jobs"] += 1
        source = _safe_str(result.get("source")) or "unknown"
        summary["sources"][source] = int(summary["sources"].get(source) or 0) + 1
        ms = float(result.get("worker_ms") or 0.0)
        if ms:
            timings.append(ms)
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        summary["candidate_count"] += len(candidates)
        for candidate in candidates:
            kind = _safe_str(_safe_dict(candidate).get("kind")) or "unknown"
            summary["candidate_kinds"][kind] = int(summary["candidate_kinds"].get(kind) or 0) + 1
        error = _safe_str(result.get("error")) or _safe_str(_safe_dict(result.get("diagnostics")).get("provider_payload_error"))
        if error:
            summary["errors"][error] = int(summary["errors"].get(error) or 0) + 1
    if timings:
        summary["avg_worker_ms"] = round(sum(timings) / len(timings), 3)
        summary["max_worker_ms"] = round(max(timings), 3)
    return summary


def _commit_authoritative_state(
    *,
    session_id: str,
    authoritative_state: Dict[str, Any],
    runtime_narration: str = "blocking",
) -> Dict[str, Any]:
    """Persist and return the runner-owned authoritative autoplay state.

    Manual/app turn paths may write partial session roots. The runner state is
    canonical for autoplay progress comparison, so commits must never reload
    and replace it from the manual session.
    """
    committed = deepcopy(_safe_dict(authoritative_state))
    prepare_autoplay_manual_session(
        session_id=session_id,
        simulation_state=committed,
        reset_session_state=False,
        runtime_narration=runtime_narration,
    )
    return committed


def _default_output_dir() -> Path:
    return Path("resources") / "data" / "test-results" / "autoplay"





def _load_provider():
    from app.shared import get_provider

    return get_provider()


def _call_turn_runtime(
    *,
    session_id: str,
    player_action: str,
    turn_index: int,
    runtime_narration: str = "blocking",
    debug_narration_trace: bool = False,
) -> Dict[str, Any]:
    return run_autoplay_manual_turn(
        session_id=session_id,
        player_input=player_action,
        turn_index=turn_index,
        target_channel="autoplay_runtime",
        console_llm=False,
        console_llm_raw=False,
        runtime_narration=runtime_narration,
        debug_narration_trace=debug_narration_trace,
    )


def _extract_narration(turn_result: Dict[str, Any]) -> str:
    candidates = [
        turn_result.get("narration"),
        _safe_dict(turn_result.get("raw_result")).get("narration"),
        _safe_dict(turn_result.get("result")).get("narration"),
        _safe_dict(turn_result.get("turn_contract")).get("narration"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _turn_result_narration_source(turn_result: Dict[str, Any]) -> str:
    """Return the source from the exact turn_result shape written to transcript."""
    if not isinstance(turn_result, dict):
        return ""
    candidate_containers = [
        turn_result,
        turn_result.get("raw_result") if isinstance(turn_result.get("raw_result"), dict) else {},
        turn_result.get("result") if isinstance(turn_result.get("result"), dict) else {},
        turn_result.get("turn_result") if isinstance(turn_result.get("turn_result"), dict) else {},
    ]
    for container in candidate_containers:
        if not isinstance(container, dict):
            continue
        payload = (
            container.get("narration_payload")
            or container.get("structured_narration")
            or {}
        )
        if not isinstance(payload, dict):
            continue
        source = payload.get("source")
        if isinstance(source, str) and source:
            return source
    return ""


def _replace_turn_result_narration_with_pending(turn_result: Dict[str, Any]) -> None:
    """Replace visible blocking narration with a deferred placeholder.

    This does not undo time already spent in the provider call. It makes the
    transcript/report truthful and prevents a blocking provider narration from
    being presented as the final turn narration in deferred mode.
    """
    if not isinstance(turn_result, dict):
        return
    pending_payload = _pending_deferred_narration_payload()
    turn_result["narration_payload"] = pending_payload
    turn_result["structured_narration"] = pending_payload
    turn_result["narration"] = pending_payload["narration"]

    raw_result = turn_result.get("raw_result") if isinstance(turn_result.get("raw_result"), dict) else {}
    if raw_result:
        raw_result["narration_payload"] = pending_payload
        raw_result["structured_narration"] = pending_payload
        raw_result["narration"] = pending_payload["narration"]

    nested_result = turn_result.get("result") if isinstance(turn_result.get("result"), dict) else {}
    if nested_result:
        nested_result["narration_payload"] = pending_payload
        nested_result["structured_narration"] = pending_payload
        nested_result["narration"] = pending_payload["narration"]

    nested_turn_result = (
        turn_result.get("turn_result")
        if isinstance(turn_result.get("turn_result"), dict)
        else {}
    )
    if nested_turn_result:
        nested_turn_result["narration_payload"] = pending_payload
        nested_turn_result["structured_narration"] = pending_payload
        nested_turn_result["narration"] = pending_payload["narration"]


def _apply_deferred_narration_violation_detection(
    *,
    record: Dict[str, Any],
    narration_mode: str,
) -> None:
    """Inspect the final transcript record and mark deferred-mode violations.

    Latest artifacts proved the real source is here:
        record["turn_result"]["narration_payload"]["source"]

    So detection must run after the transcript record is built and before it is
    appended/written.
    """
    if not isinstance(record, dict):
        return
    turn_result = _dict_or_empty(record.get("turn_result"))
    source = _turn_result_narration_source(turn_result)
    record["blocking_narration_source"] = source
    violation = (
        narration_mode == "deferred"
        and source == "provider_runtime_narration"
    )
    record["deferred_blocking_provider_violation"] = bool(violation)
    record["blocking_provider_call_suppressed_after_the_fact"] = bool(violation)
    if violation:
        _replace_turn_result_narration_with_pending(turn_result)
        record["narration"] = "Narration is being prepared..."


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _find_narration_payload(container: Dict[str, Any]) -> Dict[str, Any]:
    """Find the actual narration payload regardless of wrapper shape.

    Autoplay/manual turn results have changed shape several times:
    - result.narration_payload
    - result.structured_narration
    - result.turn_result.narration_payload
    - result.result.narration_payload

    Deferred-mode violation detection must inspect all of these or the report
    can falsely show blocking_narration_source=None while the nested turn result
    still contains provider_runtime_narration.
    """
    if not isinstance(container, dict):
        return {}

    direct = (
        container.get("narration_payload")
        or container.get("structured_narration")
    )
    if isinstance(direct, dict):
        return direct

    nested_turn = _dict_or_empty(container.get("turn_result"))
    nested_payload = (
        nested_turn.get("narration_payload")
        or nested_turn.get("structured_narration")
    )
    if isinstance(nested_payload, dict):
        return nested_payload

    nested_result = _dict_or_empty(container.get("result"))
    result_payload = (
        nested_result.get("narration_payload")
        or nested_result.get("structured_narration")
    )
    if isinstance(result_payload, dict):
        return result_payload

    return {}


def _narration_source(container: Dict[str, Any]) -> str:
    payload = _find_narration_payload(container)
    source = payload.get("source") if isinstance(payload, dict) else ""
    return source if isinstance(source, str) else ""


def _pending_deferred_narration_payload() -> Dict[str, Any]:
    return {
        "format_version": "rpg_narration_v2",
        "source": "deferred_runtime_narration_pending",
        "deferred": True,
        "narration_status": "pending",
        "narration": "Narration is being prepared...",
        "action": "The action has been resolved.",
        "npc": {"speaker": "", "line": ""},
        "reward": "",
        "followup_hooks": [],
    }


def _replace_blocking_narration_with_pending(turn_result: Dict[str, Any]) -> None:
    """Replace blocking narration artifacts with a deferred placeholder.

    This does not undo time already spent in a provider call. It makes the
    transcript/report truthful and prevents blocking provider narration from
    being presented as the canonical turn narration in deferred mode.
    """
    if not isinstance(turn_result, dict):
        return
    pending_payload = _pending_deferred_narration_payload()

    turn_result["narration_payload"] = pending_payload
    turn_result["structured_narration"] = pending_payload
    turn_result["narration"] = pending_payload["narration"]

    nested_turn = _dict_or_empty(turn_result.get("turn_result"))
    if nested_turn:
        nested_turn["narration_payload"] = pending_payload
        nested_turn["structured_narration"] = pending_payload
        nested_turn["narration"] = pending_payload["narration"]

    nested_result = _dict_or_empty(turn_result.get("result"))
    if nested_result:
        nested_result["narration_payload"] = pending_payload
        nested_result["structured_narration"] = pending_payload
        nested_result["narration"] = pending_payload["narration"]


def _select_player_action(
    *,
    provider: Any,
    player_action_context: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    strategy: str,
    use_llm_player: bool,
    max_tokens: int,
    progress_quality_metrics: Dict[str, Any] | None = None,
    diversity_metrics: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not use_llm_player:
        return choose_fallback_player_action(
            player_action_context=player_action_context,
            recent_transcript=transcript,
        )

    prompt = build_player_agent_prompt(
        player_action_context=player_action_context,
        recent_transcript=transcript,
        strategy=strategy,
        progress_quality_metrics=progress_quality_metrics,
        diversity_metrics=diversity_metrics,
    )
    try:
        raw = call_provider_text(provider, prompt, max_tokens=max_tokens)
        parsed = parse_player_agent_response(raw)
        if not parsed.get("ok"):
            fallback = choose_fallback_player_action(
                player_action_context=player_action_context,
                recent_transcript=transcript,
            )
            fallback["player_agent_error"] = parsed
            return fallback
        validation = validate_player_action_against_context(
            player_action=parsed,
            player_action_context=player_action_context,
        )
        if not validation.get("ok"):
            fallback = choose_fallback_player_action(
                player_action_context=player_action_context,
                recent_transcript=transcript,
            )
            fallback["player_agent_validation"] = validation
            fallback["raw_player_agent_action"] = parsed
            return fallback
        parsed["strategy"] = strategy
        parsed["strategy_guidance"] = build_strategy_guidance(
            strategy=strategy,
            progress_quality_metrics=progress_quality_metrics,
            diversity_metrics=diversity_metrics,
            recent_transcript=transcript,
        )
        return parsed
    except Exception as exc:
        fallback = choose_fallback_player_action(
            player_action_context=player_action_context,
            recent_transcript=transcript,
        )
        fallback["player_agent_exception"] = f"{type(exc).__name__}: {exc}"
        return fallback


def run_autoplay_campaign(args: argparse.Namespace) -> Dict[str, Any]:
    campaign_perf_start = now_perf()
    artifact_write_ms = 0.0
    session_id = args.session_id or f"autoplay_{uuid.uuid4().hex[:12]}"
    simulation_state: Dict[str, Any] = {}
    seed_resolution = resolve_campaign_seed_name(
        args.scenario_seed,
        random_seed=args.random_seed,
    )
    seed_result = seed_campaign(simulation_state, seed_resolution["resolved_seed"])
    seed_result["seed_resolution"] = seed_resolution
    authoritative_state: Dict[str, Any] = deepcopy(simulation_state)
    authoritative_state = _commit_authoritative_state(
        session_id=session_id,
        authoritative_state=authoritative_state,
        runtime_narration=args.narration_mode,
    )
    last_committed_state: Dict[str, Any] = deepcopy(authoritative_state)
    checkpoint_dir = Path(args.output_dir) / "checkpoints"

    provider = _load_provider() if args.player_agent == "llm" else None
    provider_shape = describe_provider_shape(provider) if provider is not None else {}
    if args.debug_provider_shape and provider_shape:
        print("Player-agent provider shape:")
        print(provider_shape)

    pipeline = AutoplayBackgroundPipeline(
        background_workers=int(args.background_workers),
        provider_workers=int(args.provider_workers),
    )
    background_results_summary: Dict[str, Any] = {}


    transcript: List[Dict[str, Any]] = []
    regression_warnings: List[Dict[str, Any]] = []
    started = time.time()
    stopped_reason = ""

    for turn_index in range(1, int(args.turns) + 1):
        turn_perf_start = now_perf()
        turn_performance: Dict[str, Any] = {
            "turn_index": turn_index,
        }
        # The previous turn's committed state is the only valid baseline.
        # Never derive the next before_state from manual session reloads.
        expected_baseline_state = deepcopy(last_committed_state)
        authoritative_state = deepcopy(last_committed_state)
        authoritative_state = _commit_authoritative_state(
            session_id=session_id,
            authoritative_state=authoritative_state,
        )
        simulation_state = deepcopy(authoritative_state)
        context = build_player_action_context(
            authoritative_state,
            turn_index=turn_index,
            limit=args.suggested_action_limit,
        )
        context["story_hook_hints"] = autoplay_story_hook_player_hints(simulation_state)
        current_progress_quality_metrics = compute_progress_quality_metrics(transcript)
        current_diversity_metrics = action_diversity_metrics(
            transcript,
            window=int(args.action_diversity_window),
        )
        context["suggested_actions"] = rerank_suggested_actions_for_strategy(
            list(context.get("suggested_actions") or []),
            strategy=args.strategy,
            recent_transcript=transcript,
            progress_quality_metrics=current_progress_quality_metrics,
        )
        context["strategy_guidance"] = build_strategy_guidance(
            strategy=args.strategy,
            progress_quality_metrics=current_progress_quality_metrics,
            diversity_metrics=current_diversity_metrics,
            recent_transcript=transcript,
        )
        with timed_stage(turn_performance, "player_agent_ms"):
            selected = _select_player_action(
                provider=provider,
                player_action_context=context,
                transcript=transcript,
                strategy=args.strategy,
                use_llm_player=args.player_agent == "llm",
                max_tokens=args.player_agent_max_tokens,
                progress_quality_metrics=current_progress_quality_metrics,
                diversity_metrics=current_diversity_metrics,
            )
            player_action = _safe_str(selected.get("action"))

        runtime_error = ""
        turn_result: Dict[str, Any]
        before_state = deepcopy(expected_baseline_state)
        before_digest = state_digest(before_state)
        baseline_check = _baseline_mismatch_warning(
            expected_state=expected_baseline_state,
            actual_before_state=before_state,
        )
        story_hook_result: Dict[str, Any] = {}
        try:
            with timed_stage(turn_performance, "manual_turn_ms"):
                turn_result = _call_turn_runtime(
                    session_id=session_id,
                    player_action=player_action,
                    turn_index=turn_index,
                    runtime_narration=args.narration_mode,
                    debug_narration_trace=args.debug_provider_shape,
                )
            returned_state = _safe_dict(turn_result.get("simulation_state"))
            if returned_state:
                authoritative_state = merge_autoplay_simulation_state(
                    before_state=authoritative_state,
                    returned_state=returned_state,
                )
            simulation_state = deepcopy(authoritative_state)
            with timed_stage(turn_performance, "story_hooks_ms"):
                story_hook_result = apply_autoplay_story_hooks(
                    simulation_state=authoritative_state,
                    player_action=player_action,
                    turn_index=turn_index,
                )
            if story_hook_result.get("changed"):
                authoritative_state = merge_autoplay_simulation_state(
                    before_state=authoritative_state,
                    returned_state=_safe_dict(story_hook_result.get("simulation_state")),
                )
            authoritative_state = _commit_authoritative_state(
                session_id=session_id,
                authoritative_state=authoritative_state,
                runtime_narration=args.narration_mode,
            )
            simulation_state = deepcopy(authoritative_state)

        except Exception as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"
            turn_result = {
                "ok": False,
                "error": runtime_error,
                "traceback": traceback.format_exc(),
            }
            story_hook_result = {}

        base_response_payload: Dict[str, Any] = {}
        raw_payload = _safe_dict(
            _safe_dict(turn_result.get("manual_turn_summary")).get("raw_narration_payload")
        )
        raw_npc = _safe_dict(
            _safe_dict(turn_result.get("manual_turn_summary")).get("raw_npc")
        )
        runtime_has_dialogue = bool(
            _safe_str(raw_payload.get("narration"))
            and (
                _safe_dict(raw_payload.get("npc")).get("line")
                or raw_npc.get("line")
                or _autoplay_report_action_type(player_action) != "social"
            )
        )
        with timed_stage(turn_performance, "base_response_ms"):
            if args.autoplay_base_response != "off" and not runtime_has_dialogue:
                base_response_payload = build_autoplay_base_response(
                    provider=provider,
                    player_action=player_action,
                    simulation_state=authoritative_state,
                    turn_index=turn_index,
                    use_provider=args.autoplay_base_response == "provider",
                    max_tokens=int(args.base_response_max_tokens),
                )

        # Final turn commit. This is the state that the next turn must use as
        # before_state. Do not reload from the manual session here.
        authoritative_state = _commit_authoritative_state(
            session_id=session_id,
            authoritative_state=authoritative_state,
        )
        final_turn_state = deepcopy(authoritative_state)
        with timed_stage(turn_performance, "progress_eval_ms"):
            progress_delta = classify_progress_delta(
                before_state=before_state,
                after_state=final_turn_state,
            )
            after_digest = state_digest(final_turn_state)
        state_preservation_debug = {
            "baseline_source": "runner_authoritative_state",
            "commit_policy": "no_manual_reload_after_turn_start",
            "next_turn_baseline_source": "last_committed_state",
            "baseline_check": baseline_check,
            "before_counts": before_digest.get("counts", {}),
            "after_counts": after_digest.get("counts", {}),
            "committed_counts": after_digest.get("counts", {}),
            "journal_entries_delta": (
                after_digest.get("counts", {}).get("journal_entries", 0)
                - before_digest.get("counts", {}).get("journal_entries", 0)
            ),
        }
        progress_quality = classify_turn_progress_quality(
            {
                "progress_delta": progress_delta,
                "player_action_context": context,
                "selected_player_action": selected,
                "player_action": player_action,
            }
        )
        with timed_stage(turn_performance, "state_bounds_ms"):
            state_bounds = collect_state_bounds(
                final_turn_state,
                max_state_bytes=int(args.max_state_bytes),
                max_root_count=int(args.max_roots),
                max_list_length=int(args.max_state_list_length),
                max_dict_keys=int(args.max_state_dict_keys),
            )
        save_load_checkpoint = {}
        checkpoint_every = int(args.checkpoint_every or 0)
        if checkpoint_every > 0 and turn_index % checkpoint_every == 0:
            if args.checkpoint_mode == "background":
                with timed_stage(turn_performance, "background_enqueue_ms"):
                    checkpoint_job_id = pipeline.submit_checkpoint(
                        session_id=session_id,
                        turn_index=turn_index,
                        checkpoint_dir=checkpoint_dir,
                        simulation_state=final_turn_state,
                    )
                save_load_checkpoint = {
                    "ok": True,
                    "status": "pending",
                    "job_id": checkpoint_job_id,
                    "mode": "background",
                }
            else:
                with timed_stage(turn_performance, "checkpoint_ms"):
                    save_load_checkpoint = validate_save_load_checkpoint(
                        session_id=session_id,
                        turn_index=turn_index,
                        checkpoint_dir=checkpoint_dir,
                        simulation_state=final_turn_state,
                    )
            # validate_save_load_checkpoint() already verifies checkpoint
            # rehydration. Do not make the checkpoint reload the live baseline;
            # the runner-owned authoritative_state remains canonical.
            simulation_state = deepcopy(final_turn_state)
        last_committed_state = deepcopy(final_turn_state)
        simulation_state = deepcopy(final_turn_state)
        narration = _extract_narration(turn_result)
        narration_status = "ready"
        narration_job_id = ""
        advisory_status = "disabled"
        advisory_job_id = ""
        if args.narration_mode == "deferred":
            narration_status = "pending"
            advisory_status = "pending"
            with timed_stage(turn_performance, "background_enqueue_ms"):
                narration_job_id = pipeline.submit_deferred_narration(
                    provider=provider,
                    session_id=session_id,
                    turn_index=turn_index,
                    player_action=player_action,
                    simulation_state=final_turn_state,
                    turn_contract=turn_result.get("turn_contract") or {},
                    prefer_provider=True,
                )
                semantic_action_record = (
                    _safe_dict(turn_result.get("semantic_action_v2"))
                    or _safe_dict(_safe_dict(turn_result.get("turn_contract")).get("semantic_action_v2"))
                    or _safe_dict(_safe_dict(turn_result.get("raw_result")).get("semantic_action_v2"))
                    or _safe_dict(_safe_dict(turn_result.get("manual_turn_summary")).get("semantic_action_v2"))
                    or {}
                )
                advisory_job_id = pipeline.submit_deferred_advisory(
                    provider=provider,
                    session_id=session_id,
                    turn_index=turn_index,
                    player_action=player_action,
                    simulation_state=final_turn_state,
                    turn_contract=turn_result.get("turn_contract") or {},
                    semantic_action_record=semantic_action_record,
                    prefer_provider=True,
                )
            if not narration:
                narration = "Narration is being prepared..."

        blocking_narration_payload = (
            turn_result.get("narration_payload")
            or turn_result.get("structured_narration")
            or {}
        )
        blocking_narration_source = (
            blocking_narration_payload.get("source")
            if isinstance(blocking_narration_payload, dict)
            else ""
        )
        deferred_blocking_provider_violation = (
            args.narration_mode == "deferred"
            and blocking_narration_source == "provider_runtime_narration"
        )

        record_build_start = now_perf()
        if deferred_blocking_provider_violation:
            pending_payload = _pending_deferred_narration_payload()
            turn_result["narration_payload"] = pending_payload
            turn_result["structured_narration"] = pending_payload
            turn_result["narration"] = pending_payload["narration"]
            narration = pending_payload["narration"]
            regression_warnings.append(
                {
                    "turn_index": turn_index,
                    "category": "deferred_narration_blocked_on_provider",
                    "message": "Deferred narration mode still called provider_runtime_narration inside the blocking turn path.",
                    "blocking_source": "provider_runtime_narration",
                }
            )

        record = {
            "turn_index": turn_index,
            "session_id": session_id,
            "player_action_context": context if args.artifact_detail == "full" else {
                "format_version": context.get("format_version"),
                "mode": context.get("mode"),
                "location": context.get("location"),
                "active_objectives": context.get("active_objectives"),
                "suggested_actions": context.get("suggested_actions"),
            },
            "selected_player_action": selected,
            "selected_action_reason": selected.get("reason"),
            "strategy_guidance": context.get("strategy_guidance") or selected.get("strategy_guidance") or {},
            "action_diversity_before_turn": current_diversity_metrics,
            "progress_quality_before_turn": current_progress_quality_metrics,
            "player_action": player_action,
            "turn_result": turn_result if args.artifact_detail == "full" else {
                "ok": turn_result.get("ok"),
                "warning": turn_result.get("warning"),
                "compatibility_turn_runtime": turn_result.get("compatibility_turn_runtime"),
                "runtime_name": turn_result.get("runtime_name"),
            },
            "narration_trace": turn_result.get("narration_trace") if args.debug_provider_shape else [],
            "provider_trace": turn_result.get("provider_trace") if args.debug_provider_shape else [],
            "manual_stage_trace": turn_result.get("manual_stage_trace") if args.debug_provider_shape else [],
            "manual_harness_trace": turn_result.get("manual_harness_trace") if args.debug_provider_shape else [],
            "manual_harness_trace_summary": turn_result.get("manual_harness_trace_summary") if args.debug_provider_shape else {},
            "turn_perf_trace": turn_result.get("turn_perf_trace") if args.debug_provider_shape else [],
            "turn_perf_trace_summary": turn_result.get("turn_perf_trace_summary") if args.debug_provider_shape else {},
            "turn_contract": turn_result.get("turn_contract") or {},
            "narration": narration,
            "narration_mode": args.narration_mode,
            "narration_status": narration_status,
            "narration_job_id": narration_job_id,
            "deferred_advisory_status": advisory_status,
            "deferred_advisory_job_id": advisory_job_id,
            "blocking_narration_source": blocking_narration_source,
            "deferred_blocking_provider_violation": deferred_blocking_provider_violation,
            "blocking_provider_call_suppressed_after_the_fact": bool(deferred_blocking_provider_violation),
            "latency_profile": args.latency_profile,
            "runtime_error": runtime_error,
            "before_state_digest": before_digest,
            "after_state_digest": after_digest,
            "progress_delta": progress_delta,
             "state_preservation_debug": state_preservation_debug,
            "authoritative_state_digest": after_digest,
            "committed_next_turn_digest": state_digest(last_committed_state),
            "before_state": before_state if args.artifact_detail == "full" else {},
            "final_authoritative_state": final_turn_state,
             "progress_quality": progress_quality,
            "state_bounds": state_bounds,
            "save_load_checkpoint": save_load_checkpoint,
            "story_hook_result": story_hook_result,
            "base_response_payload": base_response_payload,
        }

        turn_performance["record_build_ms"] = elapsed_ms(record_build_start)

        playable_blocking_keys = [
            "manual_turn_ms",
            "story_hooks_ms",
            "base_response_ms",
            "progress_eval_ms",
            "state_bounds_ms",
            "record_build_ms",
        ]

        autoplay_blocking_keys = ["player_agent_ms"] + playable_blocking_keys

        if args.checkpoint_mode == "blocking":
            playable_blocking_keys.append("checkpoint_ms")
            autoplay_blocking_keys.append("checkpoint_ms")

        turn_performance["human_playable_blocking_ms"] = round(
            sum(float(turn_performance.get(key) or 0.0) for key in playable_blocking_keys),
            3,
        )

        turn_performance["playable_blocking_ms"] = round(
            sum(float(turn_performance.get(key) or 0.0) for key in autoplay_blocking_keys),
            3,
        )
        turn_performance["turn_total_ms"] = elapsed_ms(turn_perf_start)
        record["performance"] = turn_performance

        # Final source detection must run against the exact record object that
        # will be appended/written. Recent artifacts showed:
        #   record["turn_result"]["narration_payload"]["source"]
        # was provider_runtime_narration while blocking_narration_source stayed
        # empty, so do this directly and overwrite the record fields here.
        record_turn_result = (
            record.get("turn_result")
            if isinstance(record.get("turn_result"), dict)
            else {}
        )
        record_payload = (
            record_turn_result.get("narration_payload")
            or record_turn_result.get("structured_narration")
            or {}
        )
        record_source = (
            record_payload.get("source")
            if isinstance(record_payload, dict)
            else ""
        )
        record["blocking_narration_source"] = record_source
        record_violation = (
            args.narration_mode == "deferred"
            and record_source == "provider_runtime_narration"
        )
        record["deferred_blocking_provider_violation"] = bool(record_violation)
        record["blocking_provider_call_suppressed_after_the_fact"] = bool(record_violation)
        if record_violation:
            pending_payload = _pending_deferred_narration_payload()
            record_turn_result["narration_payload"] = pending_payload
            record_turn_result["structured_narration"] = pending_payload
            record_turn_result["narration"] = pending_payload["narration"]
            record["narration"] = pending_payload["narration"]
            regression_warnings.append(
                {
                    "turn_index": turn_index,
                    "category": "deferred_narration_blocked_on_provider",
                    "message": "Deferred narration mode still called provider_runtime_narration inside the blocking turn path.",
                    "blocking_source": "provider_runtime_narration",
                }
            )

        transcript.append(record)

        health = evaluate_autoplay_health(
            transcript,
            latest_context=context,
            max_repeated_actions=args.max_repeated_actions,
            max_runtime_errors=0 if args.fail_on_runtime_error else 999999,
            allow_compatibility_turn_runtime=not args.fail_on_compatibility_turn_runtime,
            max_player_agent_fallback_rate=args.max_player_agent_fallback_rate,
            max_no_progress_turns=args.max_no_progress_turns,
            fail_on_checkpoint_failure=not args.allow_checkpoint_failures,
            fail_on_state_bound_warnings=not args.allow_state_bound_warnings,
            min_action_diversity_rate=float(args.min_action_diversity_rate),
            min_category_diversity_rate=float(args.min_category_diversity_rate),
        )
        if args.stop_on_loop and health.get("loop", {}).get("ok") is False:
            stopped_reason = "repeated_action_loop"
            break
        if runtime_error and args.fail_on_runtime_error:
            stopped_reason = "runtime_error"
            break

    background_results = pipeline.drain()
    background_results_summary = attach_background_results_to_transcript(transcript, background_results)
    pipeline.shutdown()

    latest_context = (
        transcript[-1].get("player_action_context")
        if transcript and isinstance(transcript[-1].get("player_action_context"), dict)
        else {}
    )
    progress_quality_metrics = compute_progress_quality_metrics(transcript)
    performance_metrics = summarize_performance(
        transcript=transcript,
        campaign_wall_ms=elapsed_ms(campaign_perf_start),
        artifact_write_ms=artifact_write_ms,
    )
    metrics = compute_progress_metrics(transcript, latest_context=latest_context)
    metrics["player_agent_trace_summary"] = _summarize_player_agent_trace(transcript)
    metrics["deferred_narration_trace_summary"] = _summarize_deferred_narration_trace(transcript)
    metrics["deferred_advisory_trace_summary"] = _summarize_deferred_advisory_trace(transcript)
    manual_harness_slowest = []
    for row in transcript:
        summary = row.get("manual_harness_trace_summary") or {}
        for stage in summary.get("slowest_stages") or []:
            manual_harness_slowest.append(
                {
                    "turn_index": row.get("turn_index"),
                    "event": stage.get("event"),
                    "elapsed_seconds": stage.get("elapsed_seconds"),
                }
            )
    metrics["manual_harness_trace_summary"] = {
        "enabled": bool(args.debug_provider_shape),
        "slowest_stages": sorted(
            manual_harness_slowest,
            key=lambda item: float(item.get("elapsed_seconds") or 0.0),
            reverse=True,
        )[:20],
    }

    turn_perf_slowest = []
    for row in transcript:
        summary = row.get("turn_perf_trace_summary") or {}
        for stage in summary.get("slowest_stages") or []:
            turn_perf_slowest.append(
                {
                    "turn_index": row.get("turn_index"),
                    "event": stage.get("event"),
                    "elapsed_seconds": stage.get("elapsed_seconds"),
                }
            )
    metrics["turn_perf_trace_summary"] = {
        "enabled": bool(args.debug_provider_shape),
        "slowest_stages": sorted(
            turn_perf_slowest,
            key=lambda item: float(item.get("elapsed_seconds") or 0.0),
            reverse=True,
        )[:30],
    }
    provider_trace_rows = [
        item
        for row in transcript
        for item in (row.get("provider_trace") or [])
        if isinstance(item, dict)
    ]
    metrics["provider_trace_summary"] = {
        "provider_call_count": sum(1 for row in provider_trace_rows if row.get("event") == "provider_call"),
        "provider_call_seconds": round(
            sum(float(row.get("elapsed_seconds") or 0.0) for row in provider_trace_rows if row.get("event") == "provider_call"),
            3,
        ),
        "by_purpose": {},
    }
    for row in provider_trace_rows:
        if row.get("event") != "provider_call":
            continue
        purpose = str(row.get("purpose") or "unknown")
        bucket = metrics["provider_trace_summary"]["by_purpose"].setdefault(
            purpose,
            {"count": 0, "seconds": 0.0, "prompt_chars": 0},
        )
        bucket["count"] += 1
        bucket["seconds"] = round(bucket["seconds"] + float(row.get("elapsed_seconds") or 0.0), 3)
        bucket["prompt_chars"] += int(row.get("prompt_chars") or 0)
    metrics["narration_trace_summary"] = {
        "guard_enter_count": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "guard_enter"
        ),
        "provider_accessor_calls": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "get_runtime_llm_provider_called"
        ),
        "build_payload_calls": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "before_build_runtime_narration_payload"
        ),
        "provider_runtime_sources": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "after_build_runtime_narration_payload"
            and item.get("source") == "provider_runtime_narration"
        ),
    }
    metrics["progress_quality"] = progress_quality_metrics
    metrics["performance"] = performance_metrics
    metrics["background_jobs"] = background_results_summary
    health = evaluate_autoplay_health(
        transcript,
        latest_context=latest_context,
        max_repeated_actions=args.max_repeated_actions,
        max_runtime_errors=0 if args.fail_on_runtime_error else 999999,
        allow_compatibility_turn_runtime=not args.fail_on_compatibility_turn_runtime,
        max_player_agent_fallback_rate=args.max_player_agent_fallback_rate,
        max_no_progress_turns=args.max_no_progress_turns,
        fail_on_checkpoint_failure=not args.allow_checkpoint_failures,
        fail_on_state_bound_warnings=not args.allow_state_bound_warnings,
        min_action_diversity_rate=float(args.min_action_diversity_rate),
        min_category_diversity_rate=float(args.min_category_diversity_rate),
    )

    deferred_blocking_violations = [
        row for row in transcript
        if row.get("deferred_blocking_provider_violation")
    ]
    if deferred_blocking_violations:
        health["ok"] = False
        health.setdefault("warnings", []).append(
            f"deferred_narration_blocked_on_provider:{len(deferred_blocking_violations)}"
        )

    progress_quality_health = evaluate_progress_quality_health(
        transcript,
        min_meaningful_progress_rate=float(args.min_meaningful_progress_rate),
        max_churn_only_rate=float(args.max_churn_only_rate),
        max_churn_only_streak=int(args.max_churn_only_streak),
        max_objective_target_no_progress_streak=int(args.max_objective_target_no_progress_streak),
    )
    health.setdefault("warnings", [])
    if not progress_quality_health.get("ok"):
        health["warnings"].extend(
            [
                "progress_quality:" + str(warning)
                for warning in progress_quality_health.get("warnings") or []
            ]
        )
    if args.fail_on_post_objective_weak_progress:
        post_objective_warnings = post_objective_false_progress_warnings(transcript)
        if post_objective_warnings:
            progress_quality_health.setdefault("warnings", [])
            progress_quality_health["warnings"].extend(post_objective_warnings)
            progress_quality_health["ok"] = False
            health["ok"] = False
    health["progress_quality"] = progress_quality_health
    summary = {
        "ok": bool(health.get("ok")) and not stopped_reason,
        "session_id": session_id,
        "scenario_seed": args.scenario_seed,
        "resolved_scenario_seed": seed_resolution["resolved_seed"],
        "seed_resolution": seed_resolution,
        "turn_runtime": "manual_harness",
        "server_runtime_used": False,
        "latency_profile": args.latency_profile,
        "narration_mode": args.narration_mode,
        "checkpoint_mode": args.checkpoint_mode,
        "background_workers": int(args.background_workers),
        "provider_workers": int(args.provider_workers),
        "checkpoint_every": int(args.checkpoint_every or 0),
        "state_bounds_limits": {
            "max_state_bytes": int(args.max_state_bytes),
            "max_roots": int(args.max_roots),
            "max_state_list_length": int(args.max_state_list_length),
            "max_state_dict_keys": int(args.max_state_dict_keys),
        },
        "progress_quality_thresholds": {
            "min_meaningful_progress_rate": float(args.min_meaningful_progress_rate),
            "max_churn_only_rate": float(args.max_churn_only_rate),
            "max_churn_only_streak": int(args.max_churn_only_streak),
            "max_objective_target_no_progress_streak": int(args.max_objective_target_no_progress_streak),
            "fail_on_post_objective_weak_progress": bool(args.fail_on_post_objective_weak_progress),
            "fail_on_dialogue_coverage_gap": bool(args.fail_on_dialogue_coverage_gap),
        },
        "strategy_profile": args.strategy,
        "base_response_mode": args.autoplay_base_response,
        "action_diversity_thresholds": {
            "action_diversity_window": int(args.action_diversity_window),
            "min_action_diversity_rate": float(args.min_action_diversity_rate),
            "min_category_diversity_rate": float(args.min_category_diversity_rate),
        },
        "seed_result": seed_result,
        "requested_turns": int(args.turns),
        "turns_executed": len(transcript),
        "stopped_reason": stopped_reason,
        "player_agent": args.player_agent,
        "provider_shape": provider_shape if args.artifact_detail == "full" else {
            "type": provider_shape.get("type"),
            "module": provider_shape.get("module"),
            "methods": provider_shape.get("methods", [])[:20],
        },
        "strategy": args.strategy,
        "artifact_detail": args.artifact_detail,
        "duration_seconds": round(time.time() - started, 3),
        "health": health,
        "performance": performance_metrics,
        "background_jobs": background_results_summary,
        "player_agent_trace_summary": metrics.get("player_agent_trace_summary") or {},
        "deferred_narration_trace_summary": metrics.get("deferred_narration_trace_summary") or {},
        "deferred_advisory_trace_summary": metrics.get("deferred_advisory_trace_summary") or {},
    }
    artifact_start = now_perf()
    extra_paths = {}
    # First compute current performance without report write timing.
    metrics["performance"] = summarize_performance(
        transcript=transcript,
        campaign_wall_ms=elapsed_ms(campaign_perf_start),
        artifact_write_ms=0.0,
    )
    metrics["story_variety"] = compute_story_variety_metrics(
        summary=summary,
        state=last_committed_state,
        transcript=transcript,
    )
    summary["performance"] = metrics["performance"]
    summary["story_variety"] = metrics["story_variety"]
    metrics["background_jobs"] = background_results_summary

    # Write the campaign report once for human-readable output.
    if args.artifact_detail == "full":
        extra_paths.update(
            write_campaign_report(
                output_dir=Path(args.output_dir),
                transcript=transcript,
                summary=summary,
                metrics=metrics,
                health=health,
            )
        )

    artifact_write_ms = elapsed_ms(artifact_start)
    metrics["performance"] = summarize_performance(
        transcript=transcript,
        campaign_wall_ms=elapsed_ms(campaign_perf_start),
        artifact_write_ms=artifact_write_ms,
    )
    metrics["story_variety"] = compute_story_variety_metrics(
        summary=summary,
        state=last_committed_state,
        transcript=transcript,
    )
    summary["performance"] = metrics["performance"]
    summary["story_variety"] = metrics["story_variety"]
    metrics["background_jobs"] = background_results_summary

    # Rewrite the report with final performance metrics so the HTML/JSON report
    # agrees with autoplay-performance.json.
    if args.artifact_detail == "full":
        extra_paths.update(
            write_campaign_report(
                output_dir=Path(args.output_dir),
                transcript=transcript,
                summary=summary,
                metrics=metrics,
                health=health,
            )
        )
    paths = write_autoplay_artifacts(
        output_dir=Path(args.output_dir),
        transcript=transcript,
        summary=summary,
        metrics=metrics,
        health=health,
        artifact_detail=args.artifact_detail,
    )
    paths.update(extra_paths)
    summary["artifact_paths"] = paths
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an LLM autoplay RPG campaign.")
    parser.add_argument("--turns", type=int, default=25)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--scenario-seed", default="tavern_story_seed")
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument("--list-scenario-seeds", action="store_true")
    parser.add_argument("--player-agent", choices=["llm", "fallback"], default="llm")
    parser.add_argument("--strategy", default="balanced_story_player")
    parser.add_argument("--player-agent-max-tokens", type=int, default=600)
    parser.add_argument("--debug-provider-shape", action="store_true")
    parser.add_argument("--debug-turn-runtime-shape", action="store_true")
    parser.add_argument("--suggested-action-limit", type=int, default=12)
    parser.add_argument("--artifact-detail", choices=["summary", "full"], default="summary")
    parser.add_argument("--output-dir", default=str(Path("resources") / "data" / "test-results" / "autoplay"))
    parser.add_argument("--base-url", default=os.environ.get("RPG_AUTOPLAY_BASE_URL", "http://127.0.0.1:5000"), help="Ignored by default manual-harness runtime; reserved for optional HTTP smoke tests.")
    parser.add_argument("--start-app-server", action="store_true", help="Ignored by default manual-harness runtime; reserved for optional HTTP smoke tests.")
    parser.add_argument("--server-startup-timeout", type=int, default=60, help="Ignored by default manual-harness runtime.")
    parser.add_argument("--max-repeated-actions", type=int, default=5)
    parser.add_argument("--max-no-progress-turns", type=int, default=0)
    parser.add_argument("--stop-on-loop", action="store_true")
    parser.add_argument("--fail-on-runtime-error", action="store_true")
    parser.add_argument("--fail-on-compatibility-turn-runtime", action="store_true")
    parser.add_argument("--max-player-agent-fallback-rate", type=float, default=1.0)
    parser.add_argument("--fail-on-regression-warnings", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=0)
    parser.add_argument("--max-state-bytes", type=int, default=2_000_000)
    parser.add_argument("--max-roots", type=int, default=80)
    parser.add_argument("--max-state-list-length", type=int, default=500)
    parser.add_argument("--max-state-dict-keys", type=int, default=500)
    parser.add_argument("--allow-checkpoint-failures", action="store_true")
    parser.add_argument("--allow-state-bound-warnings", action="store_true")
    parser.add_argument("--min-meaningful-progress-rate", type=float, default=0.0)
    parser.add_argument("--max-churn-only-rate", type=float, default=1.0)
    parser.add_argument("--max-churn-only-streak", type=int, default=0)
    parser.add_argument("--max-objective-target-no-progress-streak", type=int, default=0)
    parser.add_argument("--fail-on-post-objective-weak-progress", action="store_true")
    parser.add_argument("--autoplay-base-response", choices=["off", "deterministic", "provider"], default="deterministic")
    parser.add_argument("--base-response-max-tokens", type=int, default=220)
    parser.add_argument("--fail-on-dialogue-coverage-gap", action="store_true")
    parser.add_argument("--action-diversity-window", type=int, default=12)
    parser.add_argument("--min-action-diversity-rate", type=float, default=0.0)
    parser.add_argument("--min-category-diversity-rate", type=float, default=0.0)
    parser.add_argument("--latency-profile", choices=["evaluation", "playable"], default="evaluation")
    parser.add_argument("--narration-mode", choices=["blocking", "deferred"], default="blocking")
    parser.add_argument("--checkpoint-mode", choices=["blocking", "background"], default="blocking")
    parser.add_argument("--background-workers", type=int, default=4)
    parser.add_argument("--provider-workers", type=int, default=1)
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if getattr(args, "list_scenario_seeds", False):
        for name in available_campaign_seeds():
            print(name)
        return 0
    summary = run_autoplay_campaign(args)

    print("Autoplay RPG Campaign Summary")
    print(f"session_id: {summary['session_id']}")
    print(f"requested_turns: {summary['requested_turns']}")
    print(f"turns_executed: {summary['turns_executed']}")
    print(f"stopped_reason: {summary['stopped_reason']}")
    print(f"ok: {summary['ok']}")
    print(f"latency_profile: {summary.get('latency_profile')}")
    print(f"narration_mode: {summary.get('narration_mode')}")
    print(f"checkpoint_mode: {summary.get('checkpoint_mode')}")
    artifact_paths = summary.get("artifact_paths") or {}
    story_variety = summary.get("story_variety") or {}
    seed_result = summary.get("seed_result") or {}
    output_dir_abs = Path(args.output_dir).resolve()

    print(f"requested_seed: {story_variety.get('requested_seed') or seed_result.get('requested_seed')}")
    print(f"resolved_seed: {story_variety.get('resolved_seed') or seed_result.get('resolved_seed')}")
    print(f"output_dir: {args.output_dir}")
    print(f"output_dir_abs: {output_dir_abs}")
    print(f"results_zip: {artifact_paths.get('zip')}")
    print(f"results_zip_abs: {Path(artifact_paths.get('zip')).resolve() if artifact_paths.get('zip') else ''}")
    print(f"campaign_report_html: {artifact_paths.get('campaign_report_html') or ''}")
    print(f"campaign_report_html_abs: {Path(artifact_paths.get('campaign_report_html')).resolve() if artifact_paths.get('campaign_report_html') else ''}")
    print(f"campaign_report_json: {artifact_paths.get('campaign_report_json') or ''}")
    print(f"story_variety_json: {artifact_paths.get('story_variety') or ''}")

    if args.artifact_detail == "full" and not artifact_paths.get("campaign_report_html"):
        print("missing_full_artifacts: campaign_report_html")

    metrics = summary.get("health", {}).get("metrics", {})
    print(f"real_turn_runtime_count: {metrics.get('real_turn_runtime_count')}")
    print(f"compatibility_turn_runtime_count: {metrics.get('compatibility_turn_runtime_count')}")
    player_agent_trace_summary = summary.get("player_agent_trace_summary") or {}
    deferred_trace_summary = summary.get("deferred_narration_trace_summary") or {}
    print(f"player_agent_sources: {player_agent_trace_summary.get('selected_source_counts')}")
    print(f"player_agent_fallback_reasons: {player_agent_trace_summary.get('fallback_reason_counts')}")
    print(f"deferred_narration_sources: {deferred_trace_summary.get('sources')}")
    print(f"deferred_narration_provider_present: {deferred_trace_summary.get('provider_present')}")
    print(f"deferred_narration_provider_missing: {deferred_trace_summary.get('provider_missing')}")
    print(f"deferred_narration_errors: {deferred_trace_summary.get('errors')}")
    deferred_advisory_summary = summary.get("deferred_advisory_trace_summary") or {}
    print(f"deferred_advisory_sources: {deferred_advisory_summary.get('sources')}")
    print(f"deferred_advisory_candidate_count: {deferred_advisory_summary.get('candidate_count')}")
    print(f"deferred_advisory_candidate_kinds: {deferred_advisory_summary.get('candidate_kinds')}")
    print(f"deferred_advisory_errors: {deferred_advisory_summary.get('errors')}")

    warnings = summary.get("health", {}).get("warnings") or []
    if args.fail_on_regression_warnings and warnings:
        return 1
    if args.fail_on_runtime_error and summary.get("health", {}).get("metrics", {}).get("runtime_errors"):
        return 1
    if (
        args.fail_on_compatibility_turn_runtime
        and summary.get("health", {}).get("metrics", {}).get("compatibility_turn_runtime_count")
    ):
        return 1
    if summary.get("stopped_reason"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))