"""Phase 13.51 — extended live-provider interactive RPG feature matrix.

This suite is intentionally separate from ``interactive_intent_matrix``.  The
intent matrix remains the fast smoke/regression gate; this file adds broader
feature-facing scripts for live-provider review without making the default matrix
larger or slower.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_intent_matrix as matrix  # noqa: E402

FEATURE_MATRIX_VERSION = "interactive_feature_matrix_v4"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "resources" / "data" / "test-results" / "interactive-feature-matrix"
KNOWN_FEATURE_GAP_SCENARIO_IDS = frozenset()
SKILLS_MATRIX_SCENARIO_ID = "skills_progression_probe"
ITEMS_MATRIX_SCENARIO_ID = "item_system_actions_probe"

IntentFeatureScenario = matrix.IntentMatrixScenario
FeatureTurnExpectation = matrix.TurnExpectation


def default_feature_matrix_scenarios() -> List[IntentFeatureScenario]:
    """Return broader feature scenarios for live-provider RPG review."""

    E = FeatureTurnExpectation
    S = IntentFeatureScenario
    return [
        S(
            scenario_id="inn_room_purchase_flow",
            title="Inn: ask for room, price, purchase, and follow-up location",
            description="Covers lodging/room service intent and Bran room follow-up presentation.",
            commands=(
                "Bran, do you have any rooms available tonight?",
                "How much is a room for the night?",
                "I'll pay for a room now.",
                "Where is my room, Bran?",
            ),
            expectations=(
                E(1, contains_any=("room", "night", "available", "sleep", "lodging"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
                E(2, contains_any=("room", "night", "silver", "price", "cost"), forbids=("Hot stew", "confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
                E(3, contains_any=("room", "night", "pay", "paid", "silver", "key", "upstairs", "lodging"), forbids=("Hot stew", "confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
                E(4, contains_any=("room", "upstairs", "stairs", "hall", "door", "key", "night"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
            ),
        ),
        S(
            scenario_id="shop_sell_attempt",
            title="Shop: ask to sell provisions and check inventory/currency feedback",
            description="Covers sell/service routing and safe refusal/valuation when no backed sell inventory exists.",
            commands=(
                "Bran, can I sell you one ration?",
                "How much copper would you give me for a ration?",
                "I sell one ration to Bran.",
            ),
            expectations=(
                E(1, contains_any=("sell", "ration", "trade", "buy", "can't", "cannot", "not set up"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
                E(2, contains_any=("ration", "copper", "price", "value", "sell", "trade", "can't", "cannot"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
                E(3, contains_any=("ration", "sell", "sold", "trade", "inventory", "can't", "cannot"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
            ),
        ),
        S(
            scenario_id="travel_round_trip_route",
            title="Travel: tavern to road to old mill and back toward tavern",
            description="Covers multi-step travel intent and destination preservation beyond a two-turn route.",
            commands=(
                "I leave the tavern and take the road north.",
                "I continue toward the old mill.",
                "I look around near the old mill.",
                "I head back south toward the tavern.",
            ),
            expectations=(
                E(1, contains_any=("road", "north", "tavern", "travel", "leave"), final_action_type="travel", final_requested_terms_contains_any=("road", "north", "tavern"), provider_called=True),
                E(2, contains_any=("old mill", "road", "continue", "travel", "north"), final_action_type="travel", final_requested_terms_contains_any=("old mill", "road"), provider_called=True),
                E(3, contains_any=("old mill", "look", "around", "road", "area"), forbids=("Hot stew", "confirmed job or quest"), provider_called=True),
                E(4, contains_any=("south", "tavern", "road", "back", "travel"), final_action_type="travel", final_requested_terms_contains_any=("south", "tavern", "road"), provider_called=True),
            ),
        ),
        S(
            scenario_id="map_expansion_probe",
            title="Map expansion: travel beyond the seeded local route",
            description="Covers progressive map growth when the player follows a route beyond the initial local-region seed.",
            commands=(
                "I leave the tavern and take the road north.",
                "I continue toward the old mill.",
                "I keep following the old road east toward the river town.",
            ),
            expectations=(
                E(1, contains_any=("road", "north", "tavern", "travel", "leave"), final_action_type="travel", final_requested_terms_contains_any=("road", "north", "tavern"), provider_called=True),
                E(2, contains_any=("old mill", "road", "continue", "travel", "north"), final_action_type="travel", final_requested_terms_contains_any=("old mill", "road"), provider_called=True),
                E(3, contains_any=("east", "road", "travel", "river", "route"), final_action_type="travel", final_requested_terms_contains_any=("east", "river", "river town"), provider_called=True),
            ),
        ),
        S(
            scenario_id="npc_memory_recall_probe",
            title="NPC memory: tell Bran a name and ask if he recalls it",
            description="Covers short-session memory/recall presentation without requiring durable cross-session persistence.",
            commands=(
                "Bran, remember this: my trail name is Ash Lantern.",
                "What trail name did I ask you to remember?",
            ),
            expectations=(
                E(1, contains_any=("Ash Lantern", "remember", "trail name", "Bran"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
                E(2, contains_any=("Ash Lantern", "trail name", "remember", "recall"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
            ),
        ),
        S(
            scenario_id="equipment_inventory_probe",
            title="Inventory/equipment: check gear, ready weapon, and ask status",
            description="Covers inventory/equipment-style commands without entering a full combat scenario.",
            commands=(
                "I check my inventory and gear.",
                "I ready my sword and shield.",
                "What am I carrying right now?",
            ),
            expectations=(
                E(1, contains_any=("inventory", "gear", "carrying", "ration", "waterskin", "sword", "shield"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
                E(2, contains_any=("sword", "shield", "ready", "gear", "weapon"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
                E(3, contains_any=("carrying", "inventory", "gear", "ration", "waterskin", "sword", "shield"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
            ),
        ),
        S(
            scenario_id=SKILLS_MATRIX_SCENARIO_ID,
            title="Skills: check training, practice, and re-check progression",
            description="Covers visible skills/training progression surfaces without requiring combat victory or a level-up.",
            commands=(
                "I check my skills and training progress.",
                "I practice swordsmanship with careful controlled cuts.",
                "I check my skill progress after that practice.",
            ),
            expectations=(
                E(1, contains_any=("skill", "skills", "training", "progress", "level", "xp", "experience"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
                E(2, contains_any=("practice", "sword", "swordsmanship", "training", "skill", "cuts"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
                E(3, contains_any=("skill", "progress", "training", "sword", "improved", "xp", "experience"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
            ),
        ),
        S(
            scenario_id=ITEMS_MATRIX_SCENARIO_ID,
            title="Items: inspect inventory, use ration, query merchant, and ask crafting options",
            description="Covers player-facing item surfaces for inventory, consumables, merchant supply, and crafting/repair affordances.",
            commands=(
                "I check my items, inventory, equipment, and crafting options.",
                "I use one trail ration from my pack.",
                "Bran, what useful items or supplies can I buy or sell here?",
                "Do my items include materials for crafting or repairing a torch?",
            ),
            expectations=(
                E(1, contains_any=("item", "items", "inventory", "equipment", "crafting", "ration", "waterskin", "cloak", "dagger"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
                E(2, contains_any=("ration", "use", "eat", "hunger", "provision", "inventory"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
                E(3, contains_any=("item", "items", "supplies", "sell", "buy", "trade", "copper", "merchant", "Bran"), forbids=("confirmed job or quest", "confirmed rumor"), final_target_contains_any=("bran",), provider_called=True),
                E(4, contains_any=("craft", "crafting", "repair", "torch", "material", "items", "supplies", "recipe"), forbids=("confirmed job or quest", "confirmed rumor"), provider_called=True),
            ),
        ),
        S(
            scenario_id="backed_quest_acceptance_probe",
            title="Quest: ask for real work, accept only if backed, then clarify next step",
            description="Covers safe quest acceptance behavior: backed quest if present, otherwise grounded no-backed fallback.",
            commands=(
                "Bran, do you have real work for me?",
                "If that is a real job, I accept it.",
                "What is the next step for that job?",
            ),
            expectations=(
                E(1, contains_any=("job", "quest", "work", "confirmed", "do not have", "no backed"), forbids=("confirmed rumor",), final_target_contains_any=("bran",), provider_called=True),
                E(2, contains_any=("accept", "job", "quest", "confirmed", "do not have", "no backed"), forbids=("confirmed rumor",), provider_called=True),
                E(3, contains_any=("next", "step", "job", "quest", "confirmed", "do not have", "no backed"), forbids=("confirmed rumor",), provider_called=True),
            ),
        ),
    ]


def _select_feature_scenarios(names: Sequence[str]) -> List[IntentFeatureScenario]:
    all_scenarios = default_feature_matrix_scenarios()
    if not names:
        return all_scenarios
    wanted = set(names)
    return [scenario for scenario in all_scenarios if scenario.scenario_id in wanted]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _feature_gap_allowed(item: Mapping[str, Any], validation: Mapping[str, Any]) -> bool:
    scenario = item.get("scenario")
    scenario_id = getattr(scenario, "scenario_id", "") or str(validation.get("scenario_id") or "")
    if scenario_id not in KNOWN_FEATURE_GAP_SCENARIO_IDS:
        return False
    result = matrix._safe_dict(item.get("result"))
    summary = matrix._safe_dict(result.get("summary"))
    if _safe_int(summary.get("error_count"), 0) > 0:
        return False
    completed_turns = _safe_int(summary.get("completed_turns"), 0)
    expected_turns = len(getattr(scenario, "commands", ()) or ())
    return bool(expected_turns and completed_turns == expected_turns)


def _classify_feature_matrix_results(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    adjusted_results: List[Dict[str, Any]] = []
    feature_gaps: List[Dict[str, Any]] = []
    hard_failures: List[Dict[str, Any]] = []
    for item in results:
        adjusted_item = dict(item)
        validation = dict(matrix._safe_dict(adjusted_item.get("validation")))
        if validation and not bool(validation.get("ok")) and _feature_gap_allowed(adjusted_item, validation):
            failures = list(validation.get("failures") or [])
            validation.update(
                {
                    "ok": True,
                    "feature_gap": True,
                    "feature_gap_status": "tracked_known_gap",
                    "feature_gap_failures": failures,
                    "failures": [],
                }
            )
            scenario = adjusted_item.get("scenario")
            feature_gaps.append(
                {
                    "scenario_id": getattr(scenario, "scenario_id", "") or validation.get("scenario_id"),
                    "title": getattr(scenario, "title", ""),
                    "failure_count": len(failures),
                    "failures": failures,
                    "status": "tracked_known_gap",
                }
            )
        if validation and not bool(validation.get("ok")):
            hard_failures.append(validation)
        adjusted_item["validation"] = validation
        adjusted_results.append(adjusted_item)
    return {"results": adjusted_results, "feature_gaps": feature_gaps, "hard_failures": hard_failures}


def run_feature_matrix(
    *,
    scenarios: Sequence[IntentFeatureScenario] | None = None,
    output_root: Path | None = None,
    live_provider: bool = True,
    seed_live_survival: bool = True,
) -> Dict[str, Any]:
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    result = matrix.run_intent_matrix(
        scenarios=list(scenarios or default_feature_matrix_scenarios()),
        output_root=output_root,
        live_provider=live_provider,
        seed_live_survival=seed_live_survival,
    )
    classification = _classify_feature_matrix_results(list(result.get("results") or []))
    result["results"] = classification["results"]
    summary = matrix._safe_dict(result.get("summary"))
    hard_failures = list(classification["hard_failures"])
    feature_gaps = list(classification["feature_gaps"])
    summary["format_version"] = FEATURE_MATRIX_VERSION
    summary["matrix_kind"] = "extended_feature_matrix"
    summary["suite_note"] = "Broader live-provider feature smoke suite; known unfinished features are reported as feature_gaps while runtime errors remain hard failures. The default intent matrix remains the fast PR smoke gate."
    summary["failed"] = hard_failures
    summary["passed"] = int(summary.get("scenario_count") or len(result.get("results") or [])) - len(hard_failures)
    summary["feature_gaps"] = feature_gaps
    summary["feature_gap_count"] = len(feature_gaps)
    summary["known_feature_gap_scenarios"] = sorted(KNOWN_FEATURE_GAP_SCENARIO_IDS)
    summary_path = output_root / "interactive-feature-matrix-summary.json"
    performance_path = output_root / "interactive-feature-matrix-performance.json"
    report_path = output_root / "interactive-feature-matrix-report.html"
    summary["html_report_path"] = str(report_path)
    summary["summary_path"] = str(summary_path)
    summary["performance_path"] = str(performance_path)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    performance_path.write_text(json.dumps(matrix._safe_dict(summary.get("performance")), indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    report_path.write_text(matrix.render_matrix_html(summary, list(result.get("results") or []), matrix._safe_dict(summary.get("details"))), encoding="utf-8")
    result["summary"] = summary
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the extended live-provider interactive feature matrix.")
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider.")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario id to run. Can be repeated.")
    parser.add_argument("--output-root", default="", help="Optional output root. Defaults to the feature matrix default output root.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival/inventory state.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    scenarios = _select_feature_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else DEFAULT_OUTPUT_ROOT
    result = run_feature_matrix(
        scenarios=scenarios,
        output_root=output_root,
        live_provider=bool(args.live_provider),
        seed_live_survival=not bool(args.no_live_survival_seed),
    )
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if not result["summary"].get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
