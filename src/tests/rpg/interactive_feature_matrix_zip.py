"""Run the extended interactive feature matrix and zip the result directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.rpg.interactive_cli_commerce_response_quality import apply_commerce_sell_state_to_matrix_result  # noqa: E402
from app.rpg.interactive_cli_equipment_response_quality import apply_equipment_inventory_to_matrix_result  # noqa: E402
from app.rpg.interactive_cli_memory_response_quality import apply_short_session_memory_recall_to_matrix_result  # noqa: E402
from app.rpg.interactive_cli_response_quality import apply_response_quality_to_matrix_result  # noqa: E402
from app.rpg.interactive_cli_state_bundle import apply_interactive_cli_state_bundle_to_matrix_result  # noqa: E402
from app.rpg.interactive_cli_travel_response_quality import apply_travel_state_to_matrix_result  # noqa: E402
from tests.rpg import interactive_feature_matrix as feature_matrix  # noqa: E402
from tests.rpg import interactive_intent_matrix_zip as matrix_zip  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the extended live-provider interactive feature matrix and zip the results.")
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider. Required for this wrapper.")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario id to run. Can be repeated.")
    parser.add_argument("--output-root", default="", help="Optional output root. Defaults to the feature matrix default output root.")
    parser.add_argument("--zip-path", default="", help="Optional zip path. Defaults to <output-root>.zip.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival/inventory state.")
    parser.add_argument("--no-response-quality-cleanup", action="store_true", help="Disable Phase 13.50 presentation cleanup before zipping.")
    return parser


def _revalidate_after_cleanup(result: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute scenario validation/feature-gap status after artifact cleanup."""

    for item in list(result.get("results") or []):
        scenario = item.get("scenario")
        scenario_result = feature_matrix.matrix._safe_dict(item.get("result"))
        if scenario is not None:
            item["validation"] = feature_matrix.matrix.validate_matrix_run(scenario, scenario_result)
    classification = feature_matrix._classify_feature_matrix_results(list(result.get("results") or []))
    result["results"] = classification["results"]
    summary = feature_matrix.matrix._safe_dict(result.get("summary"))
    hard_failures = list(classification["hard_failures"])
    feature_gaps = list(classification["feature_gaps"])
    summary.update(
        {
            "format_version": feature_matrix.FEATURE_MATRIX_VERSION,
            "matrix_kind": "extended_feature_matrix",
            "failed": hard_failures,
            "passed": int(summary.get("scenario_count") or len(result.get("results") or [])) - len(hard_failures),
            "feature_gaps": feature_gaps,
            "feature_gap_count": len(feature_gaps),
            "known_feature_gap_scenarios": sorted(feature_matrix.KNOWN_FEATURE_GAP_SCENARIO_IDS),
        }
    )
    result["summary"] = summary
    return result


def _write_feature_matrix_summary_artifacts(result: Mapping[str, Any], output_root: Path) -> None:
    summary = feature_matrix.matrix._safe_dict(result.get("summary"))
    summary_path = output_root / "interactive-feature-matrix-summary.json"
    performance_path = output_root / "interactive-feature-matrix-performance.json"
    report_path = output_root / "interactive-feature-matrix-report.html"
    summary["summary_path"] = str(summary_path)
    summary["performance_path"] = str(performance_path)
    summary["html_report_path"] = str(report_path)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    performance_path.write_text(json.dumps(feature_matrix.matrix._safe_dict(summary.get("performance")), indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    report_path.write_text(
        feature_matrix.matrix.render_matrix_html(
            summary,
            list(result.get("results") or []),
            feature_matrix.matrix._safe_dict(summary.get("details")),
        ),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live_provider:
        print("This wrapper is intended for live-provider feature matrix runs. Re-run with --live-provider.")
        return 2

    scenarios = feature_matrix._select_feature_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else feature_matrix.DEFAULT_OUTPUT_ROOT
    result = feature_matrix.run_feature_matrix(
        scenarios=scenarios,
        output_root=output_root,
        live_provider=True,
        seed_live_survival=not bool(args.no_live_survival_seed),
    )
    if not bool(args.no_response_quality_cleanup):
        cleanup = apply_response_quality_to_matrix_result(result)
        commerce_cleanup = apply_commerce_sell_state_to_matrix_result(result)
        travel_cleanup = apply_travel_state_to_matrix_result(result)
        memory_cleanup = apply_short_session_memory_recall_to_matrix_result(result)
        equipment_cleanup = apply_equipment_inventory_to_matrix_result(result)
        bundle_cleanup = apply_interactive_cli_state_bundle_to_matrix_result(result)
        result["summary"]["response_quality_cleanup"] = cleanup
        result["summary"]["commerce_response_quality_cleanup"] = commerce_cleanup
        result["summary"]["travel_state_cleanup"] = travel_cleanup
        result["summary"]["memory_response_quality_cleanup"] = memory_cleanup
        result["summary"]["equipment_response_quality_cleanup"] = equipment_cleanup
        result["summary"]["interactive_cli_state_bundle"] = bundle_cleanup
        changed_turns = (
            int(cleanup.get("changed_turns") or 0)
            + int(commerce_cleanup.get("changed_turns") or 0)
            + int(travel_cleanup.get("changed_turns") or 0)
            + int(memory_cleanup.get("changed_turns") or 0)
            + int(equipment_cleanup.get("changed_turns") or 0)
            + int(bundle_cleanup.get("changed_turns") or 0)
        )
        if changed_turns > 0:
            result = _revalidate_after_cleanup(result)
            result["summary"]["response_quality_cleanup"] = cleanup
            result["summary"]["commerce_response_quality_cleanup"] = commerce_cleanup
            result["summary"]["travel_state_cleanup"] = travel_cleanup
            result["summary"]["memory_response_quality_cleanup"] = memory_cleanup
            result["summary"]["equipment_response_quality_cleanup"] = equipment_cleanup
            result["summary"]["interactive_cli_state_bundle"] = bundle_cleanup
            matrix_zip._rewrite_matrix_artifacts_after_cleanup(result, output_root)
            _write_feature_matrix_summary_artifacts(result, output_root)
    zip_path = matrix_zip.zip_matrix_output(output_root, Path(args.zip_path) if args.zip_path else None)
    result["summary"]["zip_path"] = str(zip_path)
    _write_feature_matrix_summary_artifacts(result, output_root)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(f"[INTERACTIVE-FEATURE-MATRIX-ZIP] {zip_path}")
    return 0 if not result["summary"].get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
