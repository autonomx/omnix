from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from rpg import run_survival_stack
from rpg.survival_stack_manifest import SURVIVAL_STACK_TEST_FILES

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "src" / "tests" / "rpg" / "run_survival_stack.py"


def test_bundle_bv_runner_builds_summary_and_pytest_command_without_running_stack() -> None:
    summary = run_survival_stack.build_runner_summary(ROOT)
    command = run_survival_stack.build_pytest_command(["-q"])

    assert summary["runner_version"] == "survival_stack_runner_v1"
    assert summary["ready"] is True
    assert summary["missing_test_files"] == []
    assert summary["test_file_count"] == len(SURVIVAL_STACK_TEST_FILES)
    assert command[:3] == ["python", "-m", "pytest"]
    assert command[-1] == "-q"
    assert command[3:-1] == SURVIVAL_STACK_TEST_FILES
    json.dumps(summary)


def test_bundle_bv_runner_print_command_works_from_repo_root_without_pythonpath() -> None:
    proc = subprocess.run(
        ["python", str(RUNNER), "--print-command"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout.startswith("python -m pytest `")
    assert "test_bundle_ba_runtime_survival_state_model.py" in proc.stdout
    assert "test_bundle_bt_survival_report_ui_polish.py" in proc.stdout


def test_bundle_bv_runner_check_only_and_json_work_from_repo_root() -> None:
    check = subprocess.run(
        ["python", str(RUNNER), "--check-only"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    assert check.returncode == 0, check.stderr or check.stdout
    assert "Survival stack manifest ready" in check.stdout

    json_proc = subprocess.run(
        ["python", str(RUNNER), "--json"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    assert json_proc.returncode == 0, json_proc.stderr or json_proc.stdout
    payload = json.loads(json_proc.stdout)
    assert payload["ready"] is True
    assert payload["runner_version"] == "survival_stack_runner_v1"


def test_bundle_bv_runner_file_exists_and_has_main_guard() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "if __name__ == \"__main__\"" in source
    assert "sys.path.insert" in source
    assert "run_survival_stack" in source
