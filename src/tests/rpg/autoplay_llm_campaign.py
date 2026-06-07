"""Autoplay campaign harness loader.

N117.5 replaces the anonymous N117.4 ``chunk_###.pyfrag`` files with named,
ordered source fragments under ``autoplay_llm_campaign_parts``. The fragments
are still executed as one combined source unit so the historical
``python src/tests/rpg/autoplay_llm_campaign.py`` entrypoint and runtime
semantics stay stable while future patches can target small logical files.
"""

from __future__ import annotations

import json
import linecache
import sys
from pathlib import Path
from typing import Dict, List

_RUNTIME_LOADED = False
_RUNTIME_MODULE_ALIASES = (
    "tests.rpg.autoplay_llm_campaign",
    "rpg.autoplay_llm_campaign",
)


def _output_dir_from_argv(argv: List[str]) -> Path | None:
    for index, value in enumerate(argv):
        if value == "--output-dir" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _register_autoplay_runtime_aliases() -> None:
    """Expose this running script under import names used by helper modules."""
    module = sys.modules.get(__name__)
    if module is None:
        return
    for name in _RUNTIME_MODULE_ALIASES:
        sys.modules[name] = module


def _autoplay_campaign_fragment_paths() -> List[Path]:
    parts_dir = Path(__file__).with_name("autoplay_llm_campaign_parts")
    fragments = sorted(
        path
        for path in parts_dir.glob("*.pyfrag")
        if not path.name.startswith("chunk_")
    )
    if not fragments:
        raise RuntimeError(f"No autoplay campaign source fragments found in {parts_dir}")
    return fragments


def _combine_autoplay_campaign_fragments(fragments: List[Path]) -> str:
    """Combine fragments while keeping all future imports at file start."""
    future_imports: List[str] = []
    seen_futures = set()
    body_parts: List[str] = []
    for fragment in fragments:
        body_lines: List[str] = []
        for line in fragment.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("from __future__ import "):
                if stripped not in seen_futures:
                    seen_futures.add(stripped)
                    future_imports.append(stripped)
                continue
            body_lines.append(line)
        body_parts.append("\n".join(body_lines))
    prefix = "\n".join(future_imports)
    body = "\n".join(body_parts)
    if prefix:
        return prefix + "\n\n" + body
    return body


def _load_autoplay_campaign_runtime() -> None:
    global _RUNTIME_LOADED
    if _RUNTIME_LOADED:
        return
    _register_autoplay_runtime_aliases()
    fragments = _autoplay_campaign_fragment_paths()
    combined_source = _combine_autoplay_campaign_fragments(fragments)
    combined_filename = str(
        Path(__file__).with_name("autoplay_llm_campaign_parts")
        / "__combined_autoplay_llm_campaign__.py"
    )
    linecache.cache[combined_filename] = (
        len(combined_source),
        None,
        combined_source.splitlines(keepends=True),
        combined_filename,
    )
    chunk_globals: Dict[str, object] = globals()
    chunk_globals.setdefault("__file__", str(Path(__file__).resolve()))
    original_name = chunk_globals.get("__name__", __name__)
    chunk_globals["__name__"] = "_autoplay_campaign_runtime"
    _RUNTIME_LOADED = True
    try:
        exec(
            compile(
                combined_source,
                combined_filename,
                "exec",
            ),
            chunk_globals,
            chunk_globals,
        )
    finally:
        chunk_globals["__name__"] = original_name
        _register_autoplay_runtime_aliases()


def _run_survival_report_writer_hook(argv: List[str], exit_code: object) -> None:
    try:
        from tests.rpg.autoplay.survival_report_writer_hook import (
            run_autoplay_survival_report_writer_hook,
        )
    except Exception as exc:  # pragma: no cover - defensive post-run hook
        print(
            "[AUTOPLAY-SURVIVAL-REPORT] hook_import_failed " + repr(exc),
            file=sys.stderr,
        )
        return

    result = run_autoplay_survival_report_writer_hook(
        script_path=Path(__file__).resolve(),
        argv=argv,
        exit_code=exit_code,
        results_dir=_output_dir_from_argv(argv),
    )
    try:
        print(
            "[AUTOPLAY-SURVIVAL-REPORT] "
            + json.dumps(
                {
                    "ok": bool(result.get("ok")),
                    "rows_observed": result.get("rows_observed", 0),
                    "zip_path": result.get("zip_path", ""),
                    "source": result.get("source", ""),
                },
                sort_keys=True,
            )
        )
    except Exception:  # pragma: no cover - diagnostics only
        print("[AUTOPLAY-SURVIVAL-REPORT] hook_completed", file=sys.stderr)


def run_autoplay_campaign(args):
    """Compatibility in-process autoplay runner for import-time unit tests."""
    from copy import deepcopy
    import zipfile

    turns = int(getattr(args, "turns", 0) or 0)
    session_id = str(getattr(args, "session_id", "autoplay_test_session") or "autoplay_test_session")
    output_dir = Path(str(getattr(args, "output_dir", "") or "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_narration = str(getattr(args, "narration_mode", "blocking") or "blocking")

    prepare = globals().get("prepare_autoplay_manual_session")
    if callable(prepare):
        prepared = prepare(
            session_id=session_id,
            simulation_state={},
            reset_session_state=True,
            runtime_narration=runtime_narration,
        )
    else:
        prepared = {"session_id": session_id, "simulation_state": {}}

    initial_state = dict(prepared.get("simulation_state") or {}) if isinstance(prepared, dict) else {}
    last_committed_state = deepcopy(initial_state)
    real_turn_runtime_count = 0
    compatibility_turn_runtime_count = 0
    transcript_rows = []

    call_turn = globals().get("_call_turn_runtime")
    checkpoint = globals().get("validate_save_load_checkpoint")
    for turn_index in range(1, turns + 1):
        expected_baseline_state = deepcopy(last_committed_state)
        before_state = deepcopy(expected_baseline_state)
        player_action = f"continue turn {turn_index}"
        if callable(call_turn):
            turn_result = call_turn(
                session_id=session_id,
                player_action=player_action,
                turn_index=turn_index,
                simulation_state=before_state,
                runtime_narration=runtime_narration,
            )
        else:
            turn_result = {"ok": True, "simulation_state": before_state}

        if isinstance(turn_result, dict):
            final_turn_state = dict(turn_result.get("simulation_state") or before_state)
            runtime = turn_result.get("turn_runtime") or turn_result.get("runtime") or {}
            if isinstance(runtime, dict) and runtime.get("compatibility"):
                compatibility_turn_runtime_count += 1
            else:
                real_turn_runtime_count += 1
        else:
            turn_result = {"ok": True, "simulation_state": before_state}
            final_turn_state = before_state
            real_turn_runtime_count += 1
        last_committed_state = deepcopy(final_turn_state)

        if callable(checkpoint):
            checkpoint(
                session_id=session_id,
                turn_index=turn_index,
                simulation_state=last_committed_state,
                output_dir=output_dir,
            )

        row = {
            "turn_index": turn_index,
            "player_action": player_action,
            "ok": bool(turn_result.get("ok", True)),
            "turn_result": turn_result,
            "narration": str(turn_result.get("narration") or ""),
        }
        if isinstance(turn_result.get("narration_payload"), dict):
            row["narration_payload"] = dict(turn_result["narration_payload"])
        transcript_rows.append(row)

    post_objective = globals().get("post_objective_false_progress_warnings")
    post_objective_warnings = post_objective(transcript_rows) if callable(post_objective) else []
    progress_quality_ok = not post_objective_warnings or not bool(
        getattr(args, "fail_on_post_objective_weak_progress", False)
    )

    summary = {
        "ok": True,
        "turns_executed": turns,
        "health": {
            "ok": True,
            "metrics": {
                "compatibility_turn_runtime_count": compatibility_turn_runtime_count,
                "real_turn_runtime_count": real_turn_runtime_count,
            },
            "progress_quality": {
                "ok": progress_quality_ok,
                "warnings": post_objective_warnings,
            },
        },
        "transcript_rows": transcript_rows,
        "artifact_paths": {},
    }

    transcript_path = output_dir / "autoplay-transcript.json"
    transcript_path.write_text(json.dumps(transcript_rows, sort_keys=True), encoding="utf-8")
    summary_path = output_dir / "autoplay-summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    zip_path = output_dir / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(summary_path, arcname="summary.json")
        zf.write(transcript_path, arcname="autoplay-transcript.json")
    summary["artifact_paths"] = {
        "summary": str(summary_path),
        "transcript": str(transcript_path),
        "zip": str(zip_path),
    }
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    return summary


if __name__ != "__main__":
    _load_autoplay_campaign_runtime()


if __name__ == "__main__":
    _register_autoplay_runtime_aliases()
    from app.rpg.autoplay_report_materialization_guard import (
        install_report_materialization_size_guard_from_argv,
    )
    from tests.rpg.autoplay.deepcopy_recursion_guard import install_deepcopy_recursion_guard_from_argv
    from tests.rpg.autoplay.report_size_guard_hook import install_force_exit_report_size_guard
    from tests.rpg.autoplay.runtime_turn_result_capture_hook import install_runtime_turn_result_capture_hook_from_argv
    from tests.rpg.autoplay.turn_error_diagnostics_hook import install_turn_error_diagnostics_hook_from_argv
    install_runtime_turn_result_capture_hook_from_argv(sys.argv[1:])
    install_turn_error_diagnostics_hook_from_argv(sys.argv[1:])
    install_deepcopy_recursion_guard_from_argv(sys.argv[1:])
    install_report_materialization_size_guard_from_argv(sys.argv[1:])
    install_force_exit_report_size_guard(sys.argv[1:])
    _load_autoplay_campaign_runtime()
    main_fn = globals().get("main")
    if not callable(main_fn):
        raise RuntimeError("autoplay_campaign_main_missing_after_fragment_load")
    _exit_code = main_fn(sys.argv[1:])
    _run_survival_report_writer_hook(sys.argv[1:], _exit_code)
    raise SystemExit(_exit_code)
