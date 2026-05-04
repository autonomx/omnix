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
from tests.rpg.autoplay.evaluators import (
    compute_progress_metrics,
    evaluate_autoplay_health,
)
from tests.rpg.autoplay.manual_turn_driver import (
    load_autoplay_simulation_state,
    merge_autoplay_simulation_state,
    prepare_autoplay_manual_session,
    run_autoplay_manual_turn,
)
from tests.rpg.autoplay.checkpoints import (
    collect_state_bounds,
    validate_save_load_checkpoint,
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
from tests.rpg.autoplay.strategy_profiles import (
    action_diversity_metrics,
    build_strategy_guidance,
    rerank_suggested_actions_for_strategy,
)
from tests.rpg.autoplay.provider_adapter import (
    call_provider_text,
    describe_provider_shape,
)
from tests.rpg.autoplay.story_hooks import (
    apply_autoplay_story_hooks,
    autoplay_story_hook_player_hints,
)
from tests.rpg.autoplay.reporting import write_autoplay_artifacts
from tests.rpg.autoplay.seeding import seed_campaign


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _commit_authoritative_state(
    *,
    session_id: str,
    authoritative_state: Dict[str, Any],
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
) -> Dict[str, Any]:
    return run_autoplay_manual_turn(
        session_id=session_id,
        player_input=player_action,
        turn_index=turn_index,
        scenario_name="autoplay_campaign",
        target_channel="autoplay_runtime",
        console_llm=False,
        console_llm_raw=False,
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
    session_id = args.session_id or f"autoplay_{uuid.uuid4().hex[:12]}"
    simulation_state: Dict[str, Any] = {}
    seed_result = seed_campaign(simulation_state, args.scenario_seed)
    authoritative_state: Dict[str, Any] = deepcopy(simulation_state)
    authoritative_state = _commit_authoritative_state(
        session_id=session_id,
        authoritative_state=authoritative_state,
    )
    last_committed_state: Dict[str, Any] = deepcopy(authoritative_state)
    checkpoint_dir = Path(args.output_dir) / "checkpoints"

    provider = _load_provider() if args.player_agent == "llm" else None
    provider_shape = describe_provider_shape(provider) if provider is not None else {}
    if args.debug_provider_shape and provider_shape:
        print("Player-agent provider shape:")
        print(provider_shape)


    transcript: List[Dict[str, Any]] = []
    started = time.time()
    stopped_reason = ""

    for turn_index in range(1, int(args.turns) + 1):
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
            turn_result = _call_turn_runtime(
                session_id=session_id,
                player_action=player_action,
                turn_index=turn_index,
            )
            returned_state = _safe_dict(turn_result.get("simulation_state"))
            if returned_state:
                authoritative_state = merge_autoplay_simulation_state(
                    before_state=authoritative_state,
                    returned_state=returned_state,
                )
            simulation_state = deepcopy(authoritative_state)
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

        # Final turn commit. This is the state that the next turn must use as
        # before_state. Do not reload from the manual session here.
        authoritative_state = _commit_authoritative_state(
            session_id=session_id,
            authoritative_state=authoritative_state,
        )
        final_turn_state = deepcopy(authoritative_state)
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
        state_bounds = collect_state_bounds(
            final_turn_state,
            max_state_bytes=int(args.max_state_bytes),
            max_root_count=int(args.max_state_roots),
            max_list_length=int(args.max_state_list_length),
            max_dict_keys=int(args.max_state_dict_keys),
        )
        save_load_checkpoint = {}
        checkpoint_every = int(args.checkpoint_every or 0)
        if checkpoint_every > 0 and turn_index % checkpoint_every == 0:
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
            "turn_contract": turn_result.get("turn_contract") or {},
            "narration": narration,
            "runtime_error": runtime_error,
            "before_state_digest": before_digest,
            "after_state_digest": after_digest,
            "progress_delta": progress_delta,
            "state_preservation_debug": state_preservation_debug,
            "authoritative_state_digest": after_digest,
            "committed_next_turn_digest": state_digest(last_committed_state),
            "progress_quality": progress_quality,
            "state_bounds": state_bounds,
            "save_load_checkpoint": save_load_checkpoint,
            "story_hook_result": story_hook_result,
        }
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

    latest_context = (
        transcript[-1].get("player_action_context")
        if transcript and isinstance(transcript[-1].get("player_action_context"), dict)
        else {}
    )
    metrics = compute_progress_metrics(transcript, latest_context=latest_context)
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
        "turn_runtime": "manual_harness",
        "server_runtime_used": False,
        "checkpoint_every": int(args.checkpoint_every or 0),
        "state_bounds_limits": {
            "max_state_bytes": int(args.max_state_bytes),
            "max_state_roots": int(args.max_state_roots),
            "max_state_list_length": int(args.max_state_list_length),
            "max_state_dict_keys": int(args.max_state_dict_keys),
        },
        "progress_quality_thresholds": {
            "min_meaningful_progress_rate": float(args.min_meaningful_progress_rate),
            "max_churn_only_rate": float(args.max_churn_only_rate),
            "max_churn_only_streak": int(args.max_churn_only_streak),
            "max_objective_target_no_progress_streak": int(args.max_objective_target_no_progress_streak),
            "fail_on_post_objective_weak_progress": bool(args.fail_on_post_objective_weak_progress),
        },
        "strategy_profile": args.strategy,
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
    }
    paths = write_autoplay_artifacts(
        output_dir=Path(args.output_dir),
        transcript=transcript,
        summary=summary,
        metrics=metrics,
        health=health,
        artifact_detail=args.artifact_detail,
    )
    summary["artifact_paths"] = paths
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an LLM autoplay RPG campaign.")
    parser.add_argument("--turns", type=int, default=25)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--scenario-seed", default="tavern_story_seed")
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
    parser.add_argument("--max-state-roots", type=int, default=80)
    parser.add_argument("--max-state-list-length", type=int, default=500)
    parser.add_argument("--max-state-dict-keys", type=int, default=500)
    parser.add_argument("--allow-checkpoint-failures", action="store_true")
    parser.add_argument("--allow-state-bound-warnings", action="store_true")
    parser.add_argument("--min-meaningful-progress-rate", type=float, default=0.0)
    parser.add_argument("--max-churn-only-rate", type=float, default=1.0)
    parser.add_argument("--max-churn-only-streak", type=int, default=0)
    parser.add_argument("--max-objective-target-no-progress-streak", type=int, default=0)
    parser.add_argument("--fail-on-post-objective-weak-progress", action="store_true")
    parser.add_argument("--action-diversity-window", type=int, default=12)
    parser.add_argument("--min-action-diversity-rate", type=float, default=0.0)
    parser.add_argument("--min-category-diversity-rate", type=float, default=0.0)
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    summary = run_autoplay_campaign(args)

    print("Autoplay RPG Campaign Summary")
    print(f"session_id: {summary['session_id']}")
    print(f"requested_turns: {summary['requested_turns']}")
    print(f"turns_executed: {summary['turns_executed']}")
    print(f"stopped_reason: {summary['stopped_reason']}")
    print(f"ok: {summary['ok']}")
    print(f"results_zip: {summary['artifact_paths']['zip']}")
    metrics = summary.get("health", {}).get("metrics", {})
    print(f"real_turn_runtime_count: {metrics.get('real_turn_runtime_count')}")
    print(f"compatibility_turn_runtime_count: {metrics.get('compatibility_turn_runtime_count')}")

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