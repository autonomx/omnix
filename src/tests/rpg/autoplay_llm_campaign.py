from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.rpg.player_action_context.runtime import build_player_action_context
from tests.rpg.autoplay.evaluators import (
    compute_progress_metrics,
    evaluate_autoplay_health,
)
from tests.rpg.autoplay.player_agent import (
    build_player_agent_prompt,
    choose_fallback_player_action,
    parse_player_agent_response,
    validate_player_action_against_context,
)
from tests.rpg.autoplay.provider_adapter import call_provider_text, describe_provider_shape
from tests.rpg.autoplay.reporting import write_autoplay_artifacts
from tests.rpg.autoplay.seeding import seed_campaign


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _default_output_dir() -> Path:
    return Path("resources") / "data" / "test-results" / "autoplay"


def _load_provider():
    from app.shared import get_provider

    return get_provider()


def _call_turn_runtime(
    *,
    simulation_state: Dict[str, Any],
    session_id: str,
    player_action: str,
    turn_index: int,
) -> Dict[str, Any]:
    """Call the in-process RPG turn runtime.

    This uses a compatibility ladder because the project has evolved across
    FastAPI/session/runtime layers. Prefer an in-process function when present;
    otherwise fall back to a simple state-preserving record so early harness
    tests can still validate the player-agent loop.
    """
    try:
        from app.rpg.session import apply_player_turn  # type: ignore

        return apply_player_turn(
            simulation_state=simulation_state,
            session_id=session_id,
            player_input=player_action,
            turn_index=turn_index,
        )
    except Exception as first_exc:
        first_error = first_exc

    try:
        from app.rpg.session_runtime import run_player_turn  # type: ignore

        return run_player_turn(
            simulation_state=simulation_state,
            session_id=session_id,
            player_input=player_action,
            turn_index=turn_index,
        )
    except Exception:
        pass

    # Last-resort compatibility mode for the first N1-N3 harness. This still
    # lets us test player action selection, context generation, artifacts,
    # metrics, and loop detection before binding to the exact app turn function.
    return {
        "ok": True,
        "compatibility_turn_runtime": True,
        "warning": f"used_compatibility_turn_runtime_after:{type(first_error).__name__}",
        "turn_contract": {
            "turn_index": turn_index,
            "player_action": player_action,
        },
        "narration": f"You choose to act: {player_action}",
        "simulation_state": simulation_state,
    }


def _extract_narration(turn_result: Dict[str, Any]) -> str:
    candidates = [
        turn_result.get("narration"),
        _safe_dict(turn_result.get("result")).get("narration"),
        _safe_dict(turn_result.get("turn_contract")).get("narration"),
        _safe_dict(_safe_dict(turn_result.get("result")).get("turn_contract")).get("narration"),
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

    provider = _load_provider() if args.player_agent == "llm" else None
    provider_shape = describe_provider_shape(provider) if provider is not None else {}
    if args.debug_provider_shape and provider_shape:
        print("Player-agent provider shape:")
        print(provider_shape)
    transcript: List[Dict[str, Any]] = []
    started = time.time()
    stopped_reason = ""

    for turn_index in range(1, int(args.turns) + 1):
        context = build_player_action_context(
            simulation_state,
            turn_index=turn_index,
            limit=args.suggested_action_limit,
        )
        selected = _select_player_action(
            provider=provider,
            player_action_context=context,
            transcript=transcript,
            strategy=args.strategy,
            use_llm_player=args.player_agent == "llm",
            max_tokens=args.player_agent_max_tokens,
        )
        player_action = _safe_str(selected.get("action"))

        runtime_error = ""
        turn_result: Dict[str, Any]
        try:
            turn_result = _call_turn_runtime(
                simulation_state=simulation_state,
                session_id=session_id,
                player_action=player_action,
                turn_index=turn_index,
            )
            returned_state = _safe_dict(turn_result.get("simulation_state"))
            if returned_state:
                simulation_state = returned_state
        except Exception as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"
            turn_result = {"ok": False, "error": runtime_error}

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
            "player_action": player_action,
            "turn_result": turn_result if args.artifact_detail == "full" else {
                "ok": turn_result.get("ok"),
                "warning": turn_result.get("warning"),
                "compatibility_turn_runtime": turn_result.get("compatibility_turn_runtime"),
            },
            "narration": narration,
            "runtime_error": runtime_error,
        }
        transcript.append(record)

        health = evaluate_autoplay_health(
            transcript,
            latest_context=context,
            max_repeated_actions=args.max_repeated_actions,
            max_runtime_errors=0 if args.fail_on_runtime_error else 999999,
            allow_compatibility_turn_runtime=not args.fail_on_compatibility_turn_runtime,
            max_player_agent_fallback_rate=args.max_player_agent_fallback_rate,
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
    )
    summary = {
        "ok": bool(health.get("ok")) and not stopped_reason,
        "session_id": session_id,
        "scenario_seed": args.scenario_seed,
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
    parser.add_argument("--suggested-action-limit", type=int, default=12)
    parser.add_argument("--artifact-detail", choices=["summary", "full"], default="summary")
    parser.add_argument("--output-dir", default=str(Path("resources") / "data" / "test-results" / "autoplay"))
    parser.add_argument("--max-repeated-actions", type=int, default=5)
    parser.add_argument("--stop-on-loop", action="store_true")
    parser.add_argument("--fail-on-runtime-error", action="store_true")
    parser.add_argument("--fail-on-compatibility-turn-runtime", action="store_true")
    parser.add_argument("--max-player-agent-fallback-rate", type=float, default=1.0)
    parser.add_argument("--fail-on-regression-warnings", action="store_true")
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