"""Run the extended interactive feature matrix and zip the result directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from rpg.interactive_cli_response_quality import apply_response_quality_to_matrix_result  # noqa: E402
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
        result["summary"]["response_quality_cleanup"] = cleanup
        if int(cleanup.get("changed_turns") or 0) > 0:
            matrix_zip._rewrite_matrix_artifacts_after_cleanup(result, output_root)
            result["summary"].update(
                {
                    "format_version": feature_matrix.FEATURE_MATRIX_VERSION,
                    "matrix_kind": "extended_feature_matrix",
                    "response_quality_cleanup": cleanup,
                }
            )
            summary_path = output_root / "interactive-feature-matrix-summary.json"
            summary_path.write_text(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    zip_path = matrix_zip.zip_matrix_output(output_root, Path(args.zip_path) if args.zip_path else None)
    result["summary"]["zip_path"] = str(zip_path)
    summary_path = output_root / "interactive-feature-matrix-summary.json"
    summary_path.write_text(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(f"[INTERACTIVE-FEATURE-MATRIX-ZIP] {zip_path}")
    return 0 if not result["summary"].get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
