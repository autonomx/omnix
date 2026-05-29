"""CD/CE/CE.1 — interactive intent matrix regression suite.

This is the realistic test layer that was missing: short player-facing scripts
that exercise the same interactive CLI path a human/Cline/Codex agent uses.

Manual/live-provider usage from repo root:

    python src/tests/rpg/interactive_intent_matrix.py --live-provider
    python src/tests/rpg/interactive_intent_matrix.py --live-provider --scenario commerce_food_purchase

Pytest can import and run the same scenario definitions with fake provider/runtime
for stable offline regression coverage. CE tightens visible-output expectations
so quest repair cannot swallow dialogue, rumor/news, or survival/self-use turns.
CE.1 makes text expectations inspect visible output only, never the player input.
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

MATRIX_VERSION = "interactive_intent_matrix_v1"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "resources" / "data" / "test-results" / "interactive-intent-matrix"


@dataclass(frozen=True)
class TurnExpectation:
    turn_index: int
    contains_any: Sequence[str] = field(default_factory=tuple)
    contains_all: Sequence[str] = field(default_factory=tuple)
    forbids: Sequence[str] = field(default_factory=tuple)
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
            commands=(
                "I ask Bran if he has any food for sale.",
                "What food do you have for sale?",
                "How much for bread?",
                "I'll buy a hot stew.",
            ),
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
            description="Quest requests must not return blank text or hallucinated quests.",
            commands=(
                "I'm looking for a quest.",
                "What do you say, Bran? Have any quests for me?",
            ),
            expectations=(
                TurnExpectation(1, contains_any=("no backed quest", "do not have a confirmed job or quest"), final_action_type="quest_inquiry", narration_source_any=("quest_repaired",)),
                TurnExpectation(2, contains_any=("no backed quest", "do not have a confirmed job or quest"), final_action_type="quest_inquiry", narration_source_any=("quest_repaired",)),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="rumor_news_no_backed_state",
            title="Rumor/news: ask Bran for rumors or news",
            description="Rumor/news intent must be recognized and grounded instead of blank fallback or quest repair copy.",
            commands=(
                "Any rumors around here?",
                "Any news lately, Bran?",
            ),
            expectations=(
                TurnExpectation(1, contains_any=("confirmed rumors", "confirmed rumor", "confirmed news", "no backed rumor"), forbids=("confirmed job or quest", "speaker\": \"self"), final_action_type="rumor_inquiry", narration_source_any=("rumor_repaired",)),
                TurnExpectation(2, contains_any=("confirmed rumors", "confirmed rumor", "confirmed news", "no backed rumor"), forbids=("confirmed job or quest", "speaker\": \"self"), final_action_type="rumor_inquiry", narration_source_any=("rumor_repaired",)),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="survival_food_and_water",
            title="Survival: ask about hunger/thirst and use provisions",
            description="Survival commands should keep visible output grounded and never become service or quest repairs.",
            commands=(
                "I check how hungry and thirsty I am.",
                "I drink water from my waterskin.",
                "I eat a ration.",
            ),
            expectations=(
                TurnExpectation(1, contains_any=("hunger", "thirst", "survival", "state"), forbids=("confirmed job or quest",), final_service_kind="unknown", provider_called=True),
                TurnExpectation(2, contains_any=("drink", "water", "waterskin", "thirst"), forbids=("confirmed job or quest", "Hot stew"), final_action_type="observe", final_service_kind="unknown"),
                TurnExpectation(3, contains_any=("eat", "ration", "hunger"), forbids=("confirmed job or quest", "Hot stew"), final_action_type="observe", final_service_kind="unknown"),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="npc_dialogue_persona",
            title="NPC dialogue: ask Bran who he is and what he knows",
            description="General dialogue should call provider intent router and avoid quest/rumor repair swallowing persona answers.",
            commands=(
                "Bran, who are you?",
                "What do you know about this place?",
            ),
            expectations=(
                TurnExpectation(1, contains_any=("Bran", "tavern", "inn", "keeper"), forbids=("confirmed job or quest", "confirmed rumors", "speaker\": \"self"), provider_called=True),
                TurnExpectation(2, contains_any=("place", "tavern", "road", "town"), forbids=("confirmed job or quest", "confirmed rumors", "confirmed news", "speaker\": \"self"), provider_called=True),
            ),
        ),
    ]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


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


def _turn_blob(turn: Mapping[str, Any]) -> str:
    # CE.1: visible-output expectations intentionally exclude player_input and
    # full raw JSON diagnostics so tests cannot pass because the user typed the
    # expected word or because a hidden diagnostic echoed it.
    return _visible_turn_blob(turn)


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
        blob = _turn_blob(turn).lower()
        if expectation.contains_all:
            for text in expectation.contains_all:
                if text.lower() not in blob:
                    failures.append(f"turn {expectation.turn_index}: expected visible text not found: {text!r}")
        if expectation.contains_any and not any(text.lower() in blob for text in expectation.contains_any):
            failures.append(f"turn {expectation.turn_index}: none of expected visible texts found: {list(expectation.contains_any)!r}")
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


def run_matrix_scenario(
    scenario: IntentMatrixScenario,
    *,
    output_root: Path | None = None,
    provider_factory: Callable[[], Any] | None = None,
    turn_executor_patch: Callable[..., Dict[str, Any]] | None = None,
    ensure_session_patch: Callable[[str], Any] | None = None,
    reset_session_patch: Callable[[str], Any] | None = None,
    live_provider: bool = True,
    seed_live_survival: bool = True,
) -> Dict[str, Any]:
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
        result = cli.run_interactive_campaign(
            turns=len(scenario.commands),
            session_id=f"intent_matrix_{scenario.scenario_id}",
            output_dir=output_dir,
            scripted_commands=list(scenario.commands),
            console_llm=False,
            provider_factory=provider_factory,
            enable_llm_intent_fallback=live_provider,
            seed_live_survival=seed_live_survival,
        )
    finally:
        cli._run_one_manual_turn = original_turn_executor  # type: ignore[method-assign]
        cli._ensure_manual_session = original_ensure  # type: ignore[method-assign]
        cli._reset_manual_session_artifacts = original_reset  # type: ignore[method-assign]
    validation = validate_matrix_run(scenario, result)
    return {"scenario": scenario, "result": result, "validation": validation}


def run_intent_matrix(
    *,
    scenarios: Sequence[IntentMatrixScenario] | None = None,
    output_root: Path | None = None,
    provider_factory: Callable[[], Any] | None = None,
    turn_executor_patch: Callable[..., Dict[str, Any]] | None = None,
    ensure_session_patch: Callable[[str], Any] | None = None,
    reset_session_patch: Callable[[str], Any] | None = None,
    live_provider: bool = True,
    seed_live_survival: bool = True,
) -> Dict[str, Any]:
    scenarios = list(scenarios or default_intent_matrix_scenarios())
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    output_root.mkdir(parents=True, exist_ok=True)
    results = [
        run_matrix_scenario(
            scenario,
            output_root=output_root,
            provider_factory=provider_factory,
            turn_executor_patch=turn_executor_patch,
            ensure_session_patch=ensure_session_patch,
            reset_session_patch=reset_session_patch,
            live_provider=live_provider,
            seed_live_survival=seed_live_survival,
        )
        for scenario in scenarios
    ]
    summary = {"format_version": MATRIX_VERSION, "scenario_count": len(results), "passed": sum(1 for item in results if item["validation"]["ok"]), "failed": [item["validation"] for item in results if not item["validation"]["ok"]], "output_root": str(output_root)}
    (output_root / "interactive-intent-matrix-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
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
