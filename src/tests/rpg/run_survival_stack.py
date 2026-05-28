"""Bundle BV — one-command survival stack regression runner.

Usage from repo root:

    python src/tests/rpg/run_survival_stack.py --print-command
    python src/tests/rpg/run_survival_stack.py --check-only
    python src/tests/rpg/run_survival_stack.py

The script bootstraps its own import path, reads the BU manifest, validates that
all referenced test files exist, and then runs the canonical BA→BT pytest slice.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]

for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from rpg.survival_stack_manifest import (  # noqa: E402
    missing_survival_stack_tests,
    survival_stack_powershell_command,
    survival_stack_pytest_args,
    survival_stack_summary,
)

RUNNER_VERSION = "survival_stack_runner_v1"


def _normalize_paths(paths: Iterable[str]) -> List[str]:
    return [str(Path(path)) for path in paths]


def build_runner_summary(repo_root: Path = REPO_ROOT) -> dict:
    summary = dict(survival_stack_summary())
    missing = missing_survival_stack_tests(repo_root)
    summary.update(
        {
            "runner_version": RUNNER_VERSION,
            "repo_root": str(repo_root),
            "tests_root": str(TESTS_ROOT),
            "src_root": str(SRC_ROOT),
            "missing_test_files": missing,
            "ready": not missing,
        }
    )
    return summary


def build_pytest_command(extra_pytest_args: Sequence[str] | None = None) -> List[str]:
    command = list(survival_stack_pytest_args())
    if extra_pytest_args:
        command.extend(extra_pytest_args)
    return command


def run_survival_stack(extra_pytest_args: Sequence[str] | None = None) -> int:
    missing = missing_survival_stack_tests(REPO_ROOT)
    if missing:
        print("Missing survival stack test files:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 2
    command = build_pytest_command(extra_pytest_args)
    print("Running survival stack pytest slice:")
    print(" ".join(command))
    proc = subprocess.run(command, cwd=str(REPO_ROOT))
    return int(proc.returncode)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or inspect the canonical BA→BT survival regression stack.")
    parser.add_argument("--print-command", action="store_true", help="Print the copy-ready PowerShell pytest command and exit.")
    parser.add_argument("--json", action="store_true", help="Print the runner summary as JSON and exit.")
    parser.add_argument("--check-only", action="store_true", help="Validate that manifest test files exist without running pytest.")
    parser.add_argument("--", dest="pytest_separator", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Extra pytest args appended to the canonical stack command.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    extra = list(args.pytest_args or [])
    if extra and extra[0] == "--":
        extra = extra[1:]

    if args.print_command:
        print(survival_stack_powershell_command())
        return 0

    if args.json:
        print(json.dumps(build_runner_summary(), indent=2, sort_keys=True))
        return 0

    if args.check_only:
        summary = build_runner_summary()
        if summary["ready"]:
            print(f"Survival stack manifest ready: {summary['test_file_count']} test files.")
            return 0
        print(json.dumps(summary, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    return run_survival_stack(extra)


if __name__ == "__main__":
    raise SystemExit(main())
