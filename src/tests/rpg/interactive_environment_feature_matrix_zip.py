"""Run the environment-specific live feature matrix and zip the result directory."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.rpg.interactive_cli_response_quality import apply_response_quality_to_matrix_result  # noqa: E402
from app.rpg.session.environment_time import advance_environment_time  # noqa: E402
from tests.rpg import interactive_feature_matrix_environment as env_matrix  # noqa: E402
from tests.rpg import interactive_intent_matrix as matrix  # noqa: E402
from tests.rpg import interactive_intent_matrix_zip as matrix_zip  # noqa: E402

ENVIRONMENT_FEATURE_MATRIX_VERSION = "interactive_environment_feature_matrix_v1"
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "resources"
    / "data"
    / "test-results"
    / "interactive-environment-feature-matrix"
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run environment-specific live-provider feature matrix probes and zip results."
    )
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider.")
    parser.add_argument("--scenario", action="append", default=[], help="Environment scenario id to run.")
    parser.add_argument("--output-root", default="", help="Optional output root.")
    parser.add_argument("--zip-path", default="", help="Optional zip path. Defaults to <output-root>.zip.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival state.")
    parser.add_argument("--no-response-quality-cleanup", action="store_true", help="Disable presentation cleanup.")
    return parser


def _select_environment_scenarios(names: Sequence[str]) -> list[Any]:
    scenarios = env_matrix.environment_feature_matrix_scenarios()
    if not names:
        return scenarios
    wanted = set(names)
    return [scenario for scenario in scenarios if scenario.scenario_id in wanted]


def _classify_environment_results(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    adjusted_results: list[dict[str, Any]] = []
    hard_failures: list[dict[str, Any]] = []
    for item in results:
        adjusted = dict(item)
        scenario = adjusted.get("scenario")
        scenario_result = matrix._safe_dict(adjusted.get("result"))
        validation = matrix._safe_dict(adjusted.get("validation"))
        if scenario is not None:
            validation = matrix.validate_matrix_run(scenario, scenario_result)
        validation = env_matrix.apply_environment_feature_validators(adjusted, validation)
        adjusted["validation"] = validation
        if validation and not bool(validation.get("ok")):
            hard_failures.append(dict(validation))
        adjusted_results.append(adjusted)
    return {"results": adjusted_results, "hard_failures": hard_failures}


def _write_environment_summary_artifacts(result: Mapping[str, Any], output_root: Path) -> None:
    summary = matrix._safe_dict(result.get("summary"))
    summary_path = output_root / "interactive-environment-feature-matrix-summary.json"
    performance_path = output_root / "interactive-environment-feature-matrix-performance.json"
    report_path = output_root / "interactive-environment-feature-matrix-report.html"
    summary["summary_path"] = str(summary_path)
    summary["performance_path"] = str(performance_path)
    summary["html_report_path"] = str(report_path)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str),
        encoding="utf-8",
    )
    performance_path.write_text(
        json.dumps(
            matrix._safe_dict(summary.get("performance")),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        matrix.render_matrix_html(
            summary,
            list(result.get("results") or []),
            matrix._safe_dict(summary.get("details")),
        ),
        encoding="utf-8",
    )


def _load_environment_session(session_id: str) -> Dict[str, Any]:
    try:
        from app.rpg.session.runtime import load_runtime_session
    except Exception:
        return {}
    session = load_runtime_session(session_id)
    return matrix._safe_dict(session)


def _save_environment_session(session: Mapping[str, Any]) -> None:
    try:
        from app.rpg.session.runtime import save_runtime_session
    except Exception:
        return
    save_runtime_session(dict(session))


def _turn_action_type(turn_summary: Mapping[str, Any]) -> str:
    diagnostics = matrix._safe_dict(turn_summary.get("interactive_cli_intent_diagnostics"))
    final = matrix._safe_dict(diagnostics.get("final_classification"))
    action_type = matrix._safe_str(final.get("action_type"))
    if action_type:
        return action_type
    raw = matrix._safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    advisory = matrix._safe_dict(raw.get("first_call_action_advisory"))
    if advisory.get("action_type"):
        return matrix._safe_str(advisory.get("action_type"))
    contract = matrix._safe_dict(raw.get("turn_contract"))
    action = matrix._safe_dict(contract.get("action"))
    return matrix._safe_str(action.get("action_type"))


def _session_environment(session: Mapping[str, Any]) -> Dict[str, Any]:
    state = matrix._safe_dict(session.get("state"))
    world = matrix._safe_dict(state.get("world"))
    env = matrix._safe_dict(world.get("environment"))
    if env:
        return env
    return matrix._safe_dict(env_matrix._environment_from_world(world))


def _set_session_environment(session: Dict[str, Any], env: Mapping[str, Any]) -> Dict[str, Any]:
    state = matrix._safe_dict(session.get("state"))
    world = matrix._safe_dict(state.get("world"))
    world["environment"] = deepcopy(dict(env))
    state["world"] = world
    session["state"] = state
    return session


def _replace_environment_payloads(value: Any, env: Mapping[str, Any]) -> None:
    if isinstance(value, dict):
        for key, nested in list(value.items()):
            if key == "environment" and isinstance(nested, dict) and "absolute_minutes" in nested:
                value[key] = deepcopy(dict(env))
            else:
                _replace_environment_payloads(nested, env)
    elif isinstance(value, list):
        for nested in value:
            _replace_environment_payloads(nested, env)


def _advance_environment_after_travel_turn(
    *,
    session_id: str,
    turn_summary: Mapping[str, Any],
    turn_index: int,
    player_input: str,
) -> None:
    if _turn_action_type(turn_summary) != "travel" and "travel" not in player_input.lower():
        return
    raw = matrix._safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    session = _load_environment_session(session_id) or matrix._safe_dict(raw.get("session"))
    env = _session_environment(session)
    if not env:
        return
    advanced = advance_environment_time(env)
    session = _set_session_environment(dict(session), advanced)
    _save_environment_session(session)
    _replace_environment_payloads(raw, advanced)
    raw["environment_elapsed_handoff"] = {
        "source": "interactive_environment_feature_matrix_zip",
        "turn_index": turn_index,
        "absolute_minutes_before": env.get("absolute_minutes"),
        "absolute_minutes_after": advanced.get("absolute_minutes"),
    }
    if "raw_result" in turn_summary:
        turn_summary["raw_result"] = raw  # type: ignore[index]
    else:
        turn_summary["result"] = raw  # type: ignore[index]


def _environment_after_turn_hook_for_scenario(scenario: Any):
    scenario_id = matrix._safe_str(getattr(scenario, "scenario_id", ""))
    if scenario_id not in env_matrix.ENVIRONMENT_MATRIX_SCENARIO_IDS:
        return None
    return _advance_environment_after_travel_turn


def _compose_hooks(first: Any, second: Any):
    if first is None:
        return second
    if second is None:
        return first

    def _combined(**kwargs: Any) -> None:
        first(**kwargs)
        second(**kwargs)

    return _combined


def _run_intent_matrix_with_environment_hooks(**kwargs: Any) -> Dict[str, Any]:
    original_hook = matrix._after_turn_hook_for_scenario

    def _hook_for_scenario(scenario: Any):
        return _compose_hooks(original_hook(scenario), _environment_after_turn_hook_for_scenario(scenario))

    matrix._after_turn_hook_for_scenario = _hook_for_scenario  # type: ignore[assignment]
    try:
        return matrix.run_intent_matrix(**kwargs)
    finally:
        matrix._after_turn_hook_for_scenario = original_hook  # type: ignore[assignment]


def run_environment_feature_matrix(
    *,
    scenarios: Sequence[Any] | None = None,
    output_root: Path | None = None,
    live_provider: bool = True,
    seed_live_survival: bool = True,
) -> Dict[str, Any]:
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    selected = list(scenarios or env_matrix.environment_feature_matrix_scenarios())
    result = _run_intent_matrix_with_environment_hooks(
        scenarios=selected,
        output_root=output_root,
        live_provider=live_provider,
        seed_live_survival=seed_live_survival,
    )
    classification = _classify_environment_results(list(result.get("results") or []))
    result["results"] = classification["results"]
    summary = matrix._safe_dict(result.get("summary"))
    hard_failures = list(classification["hard_failures"])
    summary.update(
        {
            "format_version": ENVIRONMENT_FEATURE_MATRIX_VERSION,
            "matrix_kind": "environment_feature_matrix",
            "failed": hard_failures,
            "passed": int(summary.get("scenario_count") or len(result.get("results") or [])) - len(hard_failures),
            "environment_scenario_ids": [scenario.scenario_id for scenario in selected],
        }
    )
    result["summary"] = summary
    _write_environment_summary_artifacts(result, output_root)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live_provider:
        print("This environment matrix is intended for live-provider runs. Re-run with --live-provider.")
        return 2

    scenarios = _select_environment_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else DEFAULT_OUTPUT_ROOT
    result = run_environment_feature_matrix(
        scenarios=scenarios,
        output_root=output_root,
        live_provider=True,
        seed_live_survival=not bool(args.no_live_survival_seed),
    )
    if not bool(args.no_response_quality_cleanup):
        cleanup = apply_response_quality_to_matrix_result(result)
        result["summary"]["response_quality_cleanup"] = cleanup

    requested_zip_path = Path(args.zip_path) if args.zip_path else output_root.with_suffix(".zip")
    result["summary"]["zip_path"] = str(requested_zip_path)
    _write_environment_summary_artifacts(result, output_root)
    zip_path = matrix_zip.zip_matrix_output(output_root, requested_zip_path)
    result["summary"]["zip_path"] = str(zip_path)
    _write_environment_summary_artifacts(result, output_root)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(f"[INTERACTIVE-ENVIRONMENT-FEATURE-MATRIX-ZIP] {zip_path}")
    return 0 if not result["summary"].get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())