"""Run the interactive intent matrix and zip the result directory.

This wrapper exists for live-provider debugging loops where the caller needs a
single upload-ready artifact after each run.  It delegates scenario execution to
``interactive_intent_matrix`` and then writes ``<output-root>.zip`` beside the
output directory by default.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_cli_campaign as cli  # noqa: E402
from tests.rpg import interactive_intent_matrix as matrix  # noqa: E402
from rpg.interactive_cli_response_quality import apply_response_quality_to_matrix_result  # noqa: E402


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _default_zip_path(output_root: Path) -> Path:
    return output_root.with_suffix(".zip")


def zip_matrix_output(output_root: Path, zip_path: Path | None = None) -> Path:
    """Zip ``output_root`` recursively and return the created archive path."""

    output_root = output_root.resolve()
    zip_path = (zip_path or _default_zip_path(output_root)).resolve()
    if not output_root.exists() or not output_root.is_dir():
        raise FileNotFoundError(f"matrix_output_root_missing: {output_root}")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_root.rglob("*")):
            if path.resolve() == zip_path:
                continue
            if path.is_file():
                archive.write(path, arcname=path.relative_to(output_root).as_posix())
    return zip_path


def _rewrite_scenario_artifacts_after_cleanup(item: Mapping[str, Any]) -> None:
    scenario_result = _safe_dict(_safe_dict(item).get("result"))
    artifacts = _safe_dict(scenario_result.get("artifacts"))
    output_dir = artifacts.get("output_dir")
    if not output_dir:
        return
    rewritten = cli.write_interactive_campaign_artifacts(
        output_dir=Path(str(output_dir)),
        summary=_safe_dict(scenario_result.get("summary")),
        turns=list(scenario_result.get("turns") or []),
    )
    scenario_result["artifacts"] = rewritten
    item["result"] = scenario_result  # type: ignore[index]


def _rewrite_matrix_artifacts_after_cleanup(result: dict[str, Any], output_root: Path) -> None:
    results = list(result.get("results") or [])
    for item in results:
        _rewrite_scenario_artifacts_after_cleanup(item)
        scenario = item.get("scenario")
        item["validation"] = matrix.validate_matrix_run(scenario, _safe_dict(item.get("result")))
    performance = matrix._matrix_performance(results)
    details = matrix._matrix_result_details(results)
    summary = _safe_dict(result.get("summary"))
    summary.update(
        {
            "passed": sum(1 for item in results if item["validation"]["ok"]),
            "failed": [item["validation"] for item in results if not item["validation"]["ok"]],
            "performance": performance,
            "details": details,
        }
    )
    report_path = output_root / "interactive-intent-matrix-report.html"
    summary["html_report_path"] = str(report_path)
    (output_root / "interactive-intent-matrix-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_root / "interactive-intent-matrix-performance.json").write_text(
        json.dumps(performance, indent=2, ensure_ascii=False, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report_path.write_text(matrix.render_matrix_html(summary, results, details), encoding="utf-8")
    result["summary"] = summary
    result["results"] = results


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the live-provider interactive intent matrix and zip the results.")
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider. Required for this wrapper.")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario id to run. Can be repeated.")
    parser.add_argument("--output-root", default="", help="Optional output root. Defaults to the matrix default output root.")
    parser.add_argument("--zip-path", default="", help="Optional zip path. Defaults to <output-root>.zip.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival/inventory state.")
    parser.add_argument("--no-response-quality-cleanup", action="store_true", help="Disable Phase 13.50 presentation cleanup before zipping.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live_provider:
        print("This wrapper is intended for live provider regression runs. Re-run with --live-provider.")
        return 2

    scenarios = matrix._select_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else matrix.DEFAULT_OUTPUT_ROOT
    result = matrix.run_intent_matrix(
        scenarios=scenarios,
        output_root=output_root,
        live_provider=True,
        seed_live_survival=not bool(args.no_live_survival_seed),
    )
    if not bool(args.no_response_quality_cleanup):
        cleanup = apply_response_quality_to_matrix_result(result)
        result["summary"]["response_quality_cleanup"] = cleanup
        if int(cleanup.get("changed_turns") or 0) > 0:
            _rewrite_matrix_artifacts_after_cleanup(result, output_root)
            result["summary"]["response_quality_cleanup"] = cleanup
            (output_root / "interactive-intent-matrix-summary.json").write_text(
                json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str),
                encoding="utf-8",
            )
    zip_path = zip_matrix_output(output_root, Path(args.zip_path) if args.zip_path else None)
    result["summary"]["zip_path"] = str(zip_path)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(f"[INTERACTIVE-INTENT-MATRIX-ZIP] {zip_path}")
    return 0 if not result["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
