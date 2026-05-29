"""CD/CE/CF — interactive intent matrix regression suite.

Realistic player-facing scripts for the interactive CLI path. CF adds matrix-level
performance rollups so slow live-provider runs are visible in the top-level
summary without opening every per-scenario artifact.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_cli_campaign as cli  # noqa: E402

MATRIX_VERSION = "interactive_intent_matrix_v2"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "resources" / "data" / "test-results" / "interactive-intent-matrix"


@dataclass(frozen=True)
class TurnExpectation:
    turn_index: int
    contains_any: Sequence[str] = field(default_factory=tuple)
    contains_all: Sequence[str] = field(default_factory=tuple)
    forbids: Sequence[str] = field(default_factory=tuple)
    npc_line_contains_any: Sequence[str] = field(default_factory=tuple)
    require_npc_line: bool = False
    final_action_type: str = ""
    final_service_kind: str = ""
    narration_source_any: Sequence[str] = field(default_factory=tuple)
    provider_called: bool | None = True


@dataclass(frozen=True)
class IntentMatrixScenario:
    scenario_id: str
    title: str
    commands: Sequence[str]
    expectations: Sequence[TurnExpectation]
    description: str = ""


def default_intent_matrix_scenarios() -> List[IntentMatrixScenario]:
    return [
        IntentMatrixScenario(
            scenario_id="commerce_food_purchase",
            title="Commerce: ask Bran for food, price, and purchase",
            description="Covers the previously broken food/bread/stew flow.",
            commands=("I ask Bran if he has any food for sale.", "What food do you have for sale?", "How much for bread?", "I'll buy a hot stew."),
            expectations=(
                TurnExpectation(1, contains_all=("Hot stew", "1 silver", "5 copper"), final_service_kind="meal"),
                TurnExpectation(2, contains_all=("Hot stew", "1 silver", "5 copper"), final_service_kind="meal"),
                TurnExpectation(3, contains_all=("Hot stew", "1 silver", "5 copper"), final_service_kind="meal"),
                TurnExpectation(4, contains_all=("Hot stew", "1 silver", "5 copper"), final_action_type="service_purchase", final_service_kind="meal"),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="quest_no_backed_state",
            title="Quest: ask Bran for work when no backed quest exists",
            commands=("I'm looking for a quest.", "What do you say, Bran? Have any quests for me?"),
            expectations=(
                TurnExpectation(1, contains_any=("no backed quest", "do not have a confirmed job or quest"), final_action_type="quest_inquiry", narration_source_any=("quest_repaired",)),
                TurnExpectation(2, contains_any=("no backed quest", "do not have a confirmed job or quest"), final_action_type="quest_inquiry", narration_source_any=("quest_repaired",)),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="rumor_news_no_backed_state",
            title="Rumor/news: ask Bran for rumors or news",
            commands=("Any rumors around here?", "Any news lately, Bran?"),
            expectations=(
                TurnExpectation(1, contains_any=("confirmed rumors", "confirmed rumor", "confirmed news", "no backed rumor"), forbids=("confirmed job or quest", "speaker\": \"self"), final_action_type="rumor_inquiry", narration_source_any=("rumor_repaired",)),
                TurnExpectation(2, contains_any=("confirmed rumors", "confirmed rumor", "confirmed news", "no backed rumor"), forbids=("confirmed job or quest", "speaker\": \"self"), final_action_type="rumor_inquiry", narration_source_any=("rumor_repaired",)),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="survival_food_and_water",
            title="Survival: ask about hunger/thirst and use provisions",
            commands=("I check how hungry and thirsty I am.", "I drink water from my waterskin.", "I eat a ration."),
            expectations=(
                TurnExpectation(1, contains_any=("hunger", "thirst", "survival", "state"), forbids=("confirmed job or quest",), final_service_kind="unknown", provider_called=True),
                TurnExpectation(2, contains_any=("drink", "water", "waterskin", "thirst"), forbids=("confirmed job or quest", "Hot stew"), final_action_type="observe", final_service_kind="unknown"),
                TurnExpectation(3, contains_any=("eat", "ration", "hunger"), forbids=("confirmed job or quest", "Hot stew"), final_action_type="observe", final_service_kind="unknown"),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="npc_dialogue_persona",
            title="NPC dialogue: ask Bran who he is and what he knows",
            commands=("Bran, who are you?", "What do you know about this place?"),
            expectations=(
                TurnExpectation(1, contains_any=("Bran", "tavern", "inn", "keeper"), npc_line_contains_any=("Bran", "tavern", "inn", "keeper"), require_npc_line=True, forbids=("confirmed job or quest", "confirmed rumors", "speaker\": \"self"), provider_called=True),
                TurnExpectation(2, contains_any=("place", "tavern", "road", "town"), npc_line_contains_any=("place", "tavern", "road", "town"), require_npc_line=True, forbids=("confirmed job or quest", "confirmed rumors", "confirmed news", "speaker\": \"self"), narration_source_any=("dialogue_repaired",), provider_called=True),
            ),
        ),
    ]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _percentile(values: Sequence[float], percentile: float) -> float:
    values = sorted(float(v) for v in values)
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 4)
    position = (len(values) - 1) * (percentile / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return round(values[lower] * (1.0 - weight) + values[upper] * weight, 4)


def _visible_npc_line(turn: Mapping[str, Any]) -> str:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    raw_npc = _safe_dict(turn.get("raw_npc"))
    result_npc = _safe_dict(raw.get("npc"))
    return _safe_str(raw_npc.get("line") or result_npc.get("line"))


def _visible_turn_blob(turn: Mapping[str, Any]) -> str:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    raw_npc = _safe_dict(turn.get("raw_npc"))
    result_npc = _safe_dict(raw.get("npc"))
    visible_payload = {
        "raw_narration": _safe_str(turn.get("raw_narration")),
        "raw_npc": {"speaker": _safe_str(raw_npc.get("speaker")), "line": _safe_str(raw_npc.get("line"))},
        "result_narration": _safe_str(raw.get("narration")),
        "result_npc": {"speaker": _safe_str(result_npc.get("speaker")), "line": _safe_str(result_npc.get("line"))},
        "narration_preview": _safe_str(turn.get("narration_preview")),
    }
    return json.dumps(visible_payload, ensure_ascii=False, default=str)


def _final_classification(turn: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
    return _safe_dict(diagnostics.get("final_classification"))


def validate_matrix_run(scenario: IntentMatrixScenario, result: Mapping[str, Any]) -> Dict[str, Any]:
    turns = list(result.get("turns") or [])
    failures: List[str] = []
    for expectation in scenario.expectations:
        index = expectation.turn_index - 1
        if index < 0 or index >= len(turns):
            failures.append(f"turn {expectation.turn_index}: missing turn result")
            continue
        turn = _safe_dict(turns[index])
        blob = _visible_turn_blob(turn).lower()
        npc_line = _visible_npc_line(turn).lower()
        if expectation.contains_all:
            for text in expectation.contains_all:
                if text.lower() not in blob:
                    failures.append(f"turn {expectation.turn_index}: expected visible text not found: {text!r}")
        if expectation.contains_any and not any(text.lower() in blob for text in expectation.contains_any):
            failures.append(f"turn {expectation.turn_index}: none of expected visible texts found: {list(expectation.contains_any)!r}")
        if expectation.require_npc_line and not npc_line.strip():
            failures.append(f"turn {expectation.turn_index}: expected non-empty visible NPC line")
        if expectation.npc_line_contains_any and not any(text.lower() in npc_line for text in expectation.npc_line_contains_any):
            failures.append(f"turn {expectation.turn_index}: none of expected NPC-line texts found: {list(expectation.npc_line_contains_any)!r}")
        for text in expectation.forbids:
            if text.lower() in blob:
                failures.append(f"turn {expectation.turn_index}: forbidden visible text found: {text!r}")
        final = _final_classification(turn)
        if expectation.final_action_type and _safe_str(final.get("action_type")) != expectation.final_action_type:
            failures.append(f"turn {expectation.turn_index}: final action_type {_safe_str(final.get('action_type'))!r} != {expectation.final_action_type!r}")
        if expectation.final_service_kind and _safe_str(final.get("service_kind")) != expectation.final_service_kind:
            failures.append(f"turn {expectation.turn_index}: final service_kind {_safe_str(final.get('service_kind'))!r} != {expectation.final_service_kind!r}")
        diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
        if expectation.provider_called is not None and bool(diagnostics.get("provider_called")) is not bool(expectation.provider_called):
            failures.append(f"turn {expectation.turn_index}: provider_called expected {expectation.provider_called}")
        narration_source = _safe_str(turn.get("narration_source"))
        if expectation.narration_source_any and narration_source not in expectation.narration_source_any:
            failures.append(f"turn {expectation.turn_index}: narration_source {narration_source!r} not in {list(expectation.narration_source_any)!r}")
    summary = _safe_dict(result.get("summary"))
    if int(summary.get("completed_turns") or 0) != len(scenario.commands):
        failures.append(f"completed_turns {summary.get('completed_turns')} != commands {len(scenario.commands)}")
    return {"ok": not failures, "scenario_id": scenario.scenario_id, "title": scenario.title, "failures": failures, "summary": summary, "artifact_paths": _safe_dict(result.get("artifacts")), "source": MATRIX_VERSION}


def _scenario_performance(result: Mapping[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(result.get("summary"))
    perf = _safe_dict(summary.get("performance"))
    return {
        "elapsed_seconds": round(_safe_float(summary.get("elapsed_seconds")), 4),
        "completed_turns": int(summary.get("completed_turns") or 0),
        "avg_turn_seconds": round(_safe_float(summary.get("avg_turn_seconds") or perf.get("avg_turn_seconds")), 4),
        "p95_turn_seconds": round(_safe_float(summary.get("p95_turn_seconds") or perf.get("p95_turn_seconds")), 4),
        "max_turn_seconds": round(_safe_float(summary.get("max_turn_seconds") or perf.get("max_turn_seconds")), 4),
        "slow_turn_count": int(summary.get("slow_turn_count") or perf.get("slow_turn_count") or 0),
        "phase_totals_seconds": _safe_dict(perf.get("phase_totals_seconds")),
        "phase_avg_seconds": _safe_dict(perf.get("phase_avg_seconds")),
        "slow_turns": list(perf.get("slow_turns") or [])[:10],
    }


def _matrix_performance(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    scenarios = []
    all_turn_totals: List[float] = []
    total_elapsed = 0.0
    phase_totals: Dict[str, float] = {}
    for item in results:
        scenario = item["scenario"]
        result = _safe_dict(item.get("result"))
        perf = _scenario_performance(result)
        perf["scenario_id"] = scenario.scenario_id
        scenarios.append(perf)
        total_elapsed += _safe_float(perf.get("elapsed_seconds"))
        for turn in result.get("turns") or []:
            turn_perf = _safe_dict(_safe_dict(turn).get("interactive_cli_performance"))
            total = _safe_float(turn_perf.get("turn_total_seconds"))
            if total > 0:
                all_turn_totals.append(total)
            for key, value in _safe_dict(perf.get("phase_totals_seconds")).items():
                phase_totals[key] = phase_totals.get(key, 0.0) + _safe_float(value)
    slowest = sorted(scenarios, key=lambda item: _safe_float(item.get("avg_turn_seconds")), reverse=True)
    return {
        "format_version": "interactive_intent_matrix_performance_v1",
        "scenario_count": len(scenarios),
        "total_elapsed_seconds": round(total_elapsed, 4),
        "avg_turn_seconds": round(sum(all_turn_totals) / len(all_turn_totals), 4) if all_turn_totals else 0.0,
        "p95_turn_seconds": _percentile(all_turn_totals, 95),
        "max_turn_seconds": round(max(all_turn_totals), 4) if all_turn_totals else 0.0,
        "phase_totals_seconds": {key: round(value, 4) for key, value in sorted(phase_totals.items())},
        "slowest_scenarios": slowest[:10],
        "scenarios": sorted(scenarios, key=lambda item: _safe_str(item.get("scenario_id"))),
    }


def run_matrix_scenario(scenario: IntentMatrixScenario, *, output_root: Path | None = None, provider_factory: Callable[[], Any] | None = None, turn_executor_patch: Callable[..., Dict[str, Any]] | None = None, ensure_session_patch: Callable[[str], Any] | None = None, reset_session_patch: Callable[[str], Any] | None = None, live_provider: bool = True, seed_live_survival: bool = True) -> Dict[str, Any]:
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    output_dir = output_root / scenario.scenario_id
    original_turn_executor = cli._run_one_manual_turn
    original_ensure = cli._ensure_manual_session
    original_reset = cli._reset_manual_session_artifacts
    try:
        if turn_executor_patch is not None:
            cli._run_one_manual_turn = turn_executor_patch  # type: ignore[method-assign]
        if ensure_session_patch is not None:
            cli._ensure_manual_session = ensure_session_patch  # type: ignore[method-assign]
        if reset_session_patch is not None:
            cli._reset_manual_session_artifacts = reset_session_patch  # type: ignore[method-assign]
        result = cli.run_interactive_campaign(turns=len(scenario.commands), session_id=f"intent_matrix_{scenario.scenario_id}", output_dir=output_dir, scripted_commands=list(scenario.commands), console_llm=False, provider_factory=provider_factory, enable_llm_intent_fallback=live_provider, seed_live_survival=seed_live_survival)
    finally:
        cli._run_one_manual_turn = original_turn_executor  # type: ignore[method-assign]
        cli._ensure_manual_session = original_ensure  # type: ignore[method-assign]
        cli._reset_manual_session_artifacts = original_reset  # type: ignore[method-assign]
    validation = validate_matrix_run(scenario, result)
    return {"scenario": scenario, "result": result, "validation": validation}


def run_intent_matrix(*, scenarios: Sequence[IntentMatrixScenario] | None = None, output_root: Path | None = None, provider_factory: Callable[[], Any] | None = None, turn_executor_patch: Callable[..., Dict[str, Any]] | None = None, ensure_session_patch: Callable[[str], Any] | None = None, reset_session_patch: Callable[[str], Any] | None = None, live_provider: bool = True, seed_live_survival: bool = True) -> Dict[str, Any]:
    scenarios = list(scenarios or default_intent_matrix_scenarios())
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    output_root.mkdir(parents=True, exist_ok=True)
    results = [run_matrix_scenario(scenario, output_root=output_root, provider_factory=provider_factory, turn_executor_patch=turn_executor_patch, ensure_session_patch=ensure_session_patch, reset_session_patch=reset_session_patch, live_provider=live_provider, seed_live_survival=seed_live_survival) for scenario in scenarios]
    performance = _matrix_performance(results)
    summary = {
        "format_version": MATRIX_VERSION,
        "scenario_count": len(results),
        "passed": sum(1 for item in results if item["validation"]["ok"]),
        "failed": [item["validation"] for item in results if not item["validation"]["ok"]],
        "output_root": str(output_root),
        "performance": performance,
    }
    (output_root / "interactive-intent-matrix-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    (output_root / "interactive-intent-matrix-performance.json").write_text(json.dumps(performance, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return {"summary": summary, "results": results}


def _select_scenarios(names: Sequence[str]) -> List[IntentMatrixScenario]:
    all_scenarios = default_intent_matrix_scenarios()
    if not names:
        return all_scenarios
    wanted = set(names)
    return [scenario for scenario in all_scenarios if scenario.scenario_id in wanted]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run realistic interactive CLI intent matrix scenarios.")
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider. Without this, exits with instructions.")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario id to run. Can be repeated.")
    parser.add_argument("--output-root", default="", help="Optional output root. Defaults to resources/data/test-results/interactive-intent-matrix.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival/inventory state.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live_provider:
        print("This matrix is intended for live provider regression runs. Re-run with --live-provider.")
        print("For stable pytest coverage, run: python -m pytest src/tests/rpg/test_bundle_cd_interactive_intent_matrix.py")
        return 2
    scenarios = _select_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else DEFAULT_OUTPUT_ROOT
    result = run_intent_matrix(scenarios=scenarios, output_root=output_root, live_provider=True, seed_live_survival=not bool(args.no_live_survival_seed))
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if not result["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
