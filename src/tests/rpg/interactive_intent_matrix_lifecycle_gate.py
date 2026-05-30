from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_intent_matrix as matrix  # noqa: E402
from tests.rpg.combat_lifecycle_matrix_assertions import (  # noqa: E402
    validate_combat_lifecycle_matrix_turns,
)

GATED_MATRIX_VERSION = "interactive_intent_matrix_lifecycle_gate_v1"
DEFAULT_ZIP_NAME = "interactive-intent-matrix.zip"


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _combat_lifecycle_failures(result: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    for item in result.get("results") or []:
        item = _d(item)
        scenario = item.get("scenario")
        scenario_id = getattr(scenario, "scenario_id", "") or _d(scenario).get("scenario_id")
        if scenario_id != matrix.COMBAT_MATRIX_SCENARIO_ID:
            continue
        turns = [_d(turn) for turn in _d(item.get("result")).get("turns") or []]
        failures.extend(validate_combat_lifecycle_matrix_turns(turns))
    return failures


def zip_matrix_output_root(output_root: Path, *, zip_name: str = DEFAULT_ZIP_NAME) -> Path:
    """Zip an interactive matrix output directory next to that directory."""

    output_root = Path(output_root)
    if not output_root.exists() or not output_root.is_dir():
        raise ValueError(f"matrix_output_root_not_directory: {output_root}")
    zip_path = output_root.with_name(zip_name)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_root.rglob("*")):
            if path == zip_path or not path.is_file():
                continue
            archive.write(path, path.relative_to(output_root).as_posix())
    return zip_path


def apply_lifecycle_gate(result: Dict[str, Any]) -> Dict[str, Any]:
    """Apply PR.1 lifecycle assertions to an existing interactive matrix result."""

    result = _d(result)
    summary = _d(result.get("summary"))
    failures = _combat_lifecycle_failures(result)
    gate = {
        "format_version": GATED_MATRIX_VERSION,
        "ok": not failures,
        "failures": failures,
        "source": "pr1_3_lifecycle_gate",
    }
    summary["combat_lifecycle_gate"] = gate
    if failures:
        failed = list(summary.get("failed") or [])
        failed.append(
            {
                "ok": False,
                "scenario_id": matrix.COMBAT_MATRIX_SCENARIO_ID,
                "title": "Combat lifecycle matrix gate",
                "failures": failures,
                "source": GATED_MATRIX_VERSION,
            }
        )
        summary["failed"] = failed
        summary["passed"] = max(0, int(summary.get("passed") or 0) - 1)
    result["summary"] = summary
    return result


def run_intent_matrix_with_lifecycle_gate(
    *,
    scenarios: Sequence[Any] | None = None,
    output_root: Path | None = None,
    live_provider: bool = True,
    seed_live_survival: bool = True,
) -> Dict[str, Any]:
    result = matrix.run_intent_matrix(
        scenarios=scenarios,
        output_root=output_root,
        live_provider=live_provider,
        seed_live_survival=seed_live_survival,
    )
    result = apply_lifecycle_gate(result)
    summary = _d(result.get("summary"))
    output_root_value = summary.get("output_root")
    if output_root_value:
        root = Path(str(output_root_value))
        root.mkdir(parents=True, exist_ok=True)
        (root / "interactive-intent-matrix-lifecycle-gate.json").write_text(
            json.dumps(summary.get("combat_lifecycle_gate"), indent=2, ensure_ascii=False, sort_keys=True, default=str),
            encoding="utf-8",
        )
        (root / "interactive-intent-matrix-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str),
            encoding="utf-8",
        )
        zip_path = zip_matrix_output_root(root)
        summary["zip_path"] = str(zip_path)
        (root / "interactive-intent-matrix-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str),
            encoding="utf-8",
        )
    result["summary"] = summary
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run interactive intent matrix with PR.1 combat lifecycle gate.")
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider.")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario id to run. Can be repeated.")
    parser.add_argument("--output-root", default="", help="Optional output root.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival/inventory state.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live_provider:
        print("This matrix is intended for live provider regression runs. Re-run with --live-provider.")
        return 2
    scenarios = matrix._select_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else matrix.DEFAULT_OUTPUT_ROOT
    result = run_intent_matrix_with_lifecycle_gate(
        scenarios=scenarios,
        output_root=output_root,
        live_provider=True,
        seed_live_survival=not bool(args.no_live_survival_seed),
    )
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if not result["summary"].get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
