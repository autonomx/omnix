"""Bundle BU/BX — canonical survival stack regression manifest.

Keep this file lightweight and dependency-free.  It gives humans and automation a
single source of truth for the BA→BX survival regression slice without relying on
copy/pasted command history from chat sessions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

SURVIVAL_STACK_MANIFEST_VERSION = "survival_stack_manifest_v2"

SURVIVAL_STACK_TEST_FILES: List[str] = [
    "src/tests/rpg/test_bundle_ba_runtime_survival_state_model.py",
    "src/tests/rpg/test_bundle_bb_runtime_survival_action_resolver.py",
    "src/tests/rpg/test_bundle_bc_survival_inventory_service_integration.py",
    "src/tests/rpg/test_bundle_bd_runtime_survival_action_context.py",
    "src/tests/rpg/test_bundle_be_survival_persistence_save_load.py",
    "src/tests/rpg/test_bundle_bf_survival_runtime_tick_integration.py",
    "src/tests/rpg/test_bundle_bg_survival_report_metrics.py",
    "src/tests/rpg/test_bundle_bh_survival_report_artifacts.py",
    "src/tests/rpg/test_bundle_bi_autoplay_survival_report_writer_hook.py",
    "src/tests/rpg/test_bundle_bj_survival_autoplay_smoke_scenario.py",
    "src/tests/rpg/test_bundle_bk_survival_ui_projection.py",
    "src/tests/rpg/test_bundle_bl_survival_ui_interaction_smoke.py",
    "src/tests/rpg/test_bundle_bm_survival_ui_live_payload_bridge.py",
    "src/tests/rpg/test_bundle_bn_survival_ui_command_bridge_hardening.py",
    "src/tests/rpg/test_bundle_bo_bp_bq_survival_playability_integration.py",
    "src/tests/rpg/test_bundle_br_survival_service_expansion.py",
    "src/tests/rpg/test_bundle_bs_survival_narration_grounding.py",
    "src/tests/rpg/test_bundle_bs1_world_scene_survival_grounding_bridge.py",
    "src/tests/rpg/test_bundle_bt_survival_report_ui_polish.py",
    "src/tests/rpg/test_bundle_bx_survival_readiness.py",
]

SURVIVAL_STACK_PHASES: List[str] = [
    "BA survival state model",
    "BB survival action resolver",
    "BC survival inventory/service integration",
    "BD survival action context",
    "BE survival persistence save/load",
    "BF runtime passive tick integration",
    "BG/BQ survival report metrics and gates",
    "BH/BW survival report artifacts and compact summary",
    "BI report writer hook",
    "BJ autoplay survival smoke",
    "BK survival UI projection",
    "BL survival UI interaction smoke",
    "BM live payload bridge",
    "BN command bridge hardening",
    "BO/BP/BQ playability, auto-care, advisory gates",
    "BR merchant/service expansion",
    "BS narration grounding contract",
    "BS.1 world scene narrator grounding bridge",
    "BT report/UI polish",
    "BX survival readiness projection",
]


def iter_survival_stack_tests() -> Iterable[str]:
    return tuple(SURVIVAL_STACK_TEST_FILES)


def missing_survival_stack_tests(repo_root: str | Path) -> List[str]:
    root = Path(repo_root)
    return [path for path in SURVIVAL_STACK_TEST_FILES if not (root / path).exists()]


def survival_stack_pytest_args() -> List[str]:
    return ["python", "-m", "pytest", *SURVIVAL_STACK_TEST_FILES]


def survival_stack_powershell_command() -> str:
    lines = ["python -m pytest `"]
    for index, path in enumerate(SURVIVAL_STACK_TEST_FILES):
        suffix = " `" if index < len(SURVIVAL_STACK_TEST_FILES) - 1 else ""
        lines.append(f"  {path}{suffix}")
    return "\n".join(lines)


def survival_stack_summary() -> dict:
    return {
        "format_version": SURVIVAL_STACK_MANIFEST_VERSION,
        "phase_count": len(SURVIVAL_STACK_PHASES),
        "test_file_count": len(SURVIVAL_STACK_TEST_FILES),
        "phases": list(SURVIVAL_STACK_PHASES),
        "test_files": list(SURVIVAL_STACK_TEST_FILES),
        "powershell_command": survival_stack_powershell_command(),
    }
