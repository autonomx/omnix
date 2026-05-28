from __future__ import annotations

import json
from pathlib import Path

from rpg.survival_stack_manifest import (
    SURVIVAL_STACK_MANIFEST_VERSION,
    SURVIVAL_STACK_PHASES,
    SURVIVAL_STACK_TEST_FILES,
    missing_survival_stack_tests,
    survival_stack_powershell_command,
    survival_stack_pytest_args,
    survival_stack_summary,
)

ROOT = Path(__file__).resolve().parents[3]


def test_bundle_bu_survival_stack_manifest_lists_current_ba_to_bt_stack() -> None:
    assert SURVIVAL_STACK_MANIFEST_VERSION == "survival_stack_manifest_v1"
    assert SURVIVAL_STACK_PHASES[0].startswith("BA")
    assert SURVIVAL_STACK_PHASES[-1].startswith("BT")
    assert "src/tests/rpg/test_bundle_ba_runtime_survival_state_model.py" in SURVIVAL_STACK_TEST_FILES
    assert "src/tests/rpg/test_bundle_bt_survival_report_ui_polish.py" in SURVIVAL_STACK_TEST_FILES
    assert len(SURVIVAL_STACK_PHASES) == len(SURVIVAL_STACK_TEST_FILES)


def test_bundle_bu_survival_stack_manifest_files_exist() -> None:
    missing = missing_survival_stack_tests(ROOT)
    assert missing == []


def test_bundle_bu_survival_stack_manifest_emits_copy_ready_commands() -> None:
    args = survival_stack_pytest_args()
    command = survival_stack_powershell_command()
    summary = survival_stack_summary()

    assert args[:3] == ["python", "-m", "pytest"]
    assert args[3:] == SURVIVAL_STACK_TEST_FILES
    assert command.startswith("python -m pytest `")
    assert "test_bundle_bs1_world_scene_survival_grounding_bridge.py" in command
    assert "test_bundle_bt_survival_report_ui_polish.py" in command
    assert summary["phase_count"] == len(SURVIVAL_STACK_PHASES)
    assert summary["test_file_count"] == len(SURVIVAL_STACK_TEST_FILES)
    assert summary["powershell_command"] == command
    json.dumps(summary)
