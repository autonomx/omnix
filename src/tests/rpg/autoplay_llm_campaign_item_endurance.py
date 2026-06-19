"""Autoplay campaign entrypoint with deterministic item-endurance milestones enabled."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import tests.rpg.autoplay_llm_campaign as base
from app.rpg.autoplay_report_materialization_guard import install_report_materialization_size_guard_from_argv
from tests.rpg.autoplay.deepcopy_recursion_guard import install_deepcopy_recursion_guard_from_argv
from tests.rpg.autoplay.item_endurance_action_hook import install_item_endurance_action_hook_from_argv
from tests.rpg.autoplay.live_manual_turn_timing import configure_live_manual_turn_timing_from_argv
from tests.rpg.autoplay.probe_source_map import configure_probe_source_map_from_argv
from tests.rpg.autoplay.report_size_guard_hook import install_force_exit_report_size_guard
from tests.rpg.autoplay.runtime_apply_chain_probe import install_runtime_apply_chain_probe_from_argv
from tests.rpg.autoplay.runtime_probe_payload_capture import configure_runtime_probe_payload_capture_from_argv
from tests.rpg.autoplay.runtime_turn_result_capture_hook import install_runtime_turn_result_capture_hook_from_argv
from tests.rpg.autoplay.turn_error_diagnostics_hook import install_turn_error_diagnostics_hook_from_argv


def _runtime_apply_chain_probe_enabled(argv: list[str]) -> bool:
    raw = str(os.environ.get("RPG_AUTOPLAY_RUNTIME_APPLY_CHAIN_PROBE", "") or "").strip().lower()
    return "--debug-runtime-apply-chain-probe" in argv or raw in {"1", "true", "yes", "on", "enabled"}


def main(argv: list[str] | None = None) -> object:
    args = list(sys.argv[1:] if argv is None else argv)
    base._register_autoplay_runtime_aliases()
    base._configure_runtime_exception_traceback_capture(args)
    configure_runtime_probe_payload_capture_from_argv(args)
    configure_live_manual_turn_timing_from_argv(args)
    configure_probe_source_map_from_argv(args)
    install_runtime_turn_result_capture_hook_from_argv(args)
    install_turn_error_diagnostics_hook_from_argv(args)
    install_deepcopy_recursion_guard_from_argv(args)
    if _runtime_apply_chain_probe_enabled(args):
        install_runtime_apply_chain_probe_from_argv(args)
    install_report_materialization_size_guard_from_argv(args)
    base._install_essential_mirror_member_filter()
    install_force_exit_report_size_guard(args)
    base._load_autoplay_campaign_runtime()
    hook_result = install_item_endurance_action_hook_from_argv(base.__dict__, args)
    try:
        print(f"[AUTOPLAY-ITEM-ENDURANCE] hook={hook_result}")
    except Exception:
        pass
    main_fn = base.__dict__.get("main")
    if not callable(main_fn):
        raise RuntimeError("autoplay_campaign_main_missing_after_fragment_load")
    exit_code = main_fn(args)
    base._run_survival_report_writer_hook(args, exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
