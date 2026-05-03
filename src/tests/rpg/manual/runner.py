from __future__ import annotations

import argparse
import concurrent.futures
import uuid
from typing import Any, Dict, List

from tests.rpg.manual import html_report, output_artifacts
from tests.rpg.manual.constants import (
    MANUAL_LOG_MAX_CHUNK_BYTES,
    SERVICE_OUTPUT_PATH,
    TEST_RESULTS_ROOT,
)
from tests.rpg.manual.output_state import (
    _REGRESSION_WARNING_LOCK,
    _REGRESSION_WARNING_ROWS,
)
from tests.rpg.manual.safe import _compact_json, _safe_str
from tests.rpg.manual.scenario_execution import (
    _record_scenario_error,
    _run_one_service_scenario,
)
from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.summary_sanitizer import sanitize_scenario_summary
from tests.rpg.manual.threading_helpers import (
    _effective_scenario_workers,
    _scenario_workers_source,
)
from tests.rpg.manual.token_usage import _reset_token_usage

SERVICE_SCENARIOS = build_service_scenarios()


def _new_manual_run_id() -> str:
    """Create a run id without depending on the old monolith wrapper.

    manual_llm_transcript.py is now a thin wrapper, so runner.py must not call
    legacy._new_manual_run_id().
    """
    return f"manual_{uuid.uuid4().hex[:12]}"


def _emit_summary_block(
    *,
    title: str,
    rows: List[Dict[str, Any]],
    channel: str = "service_summary",
    artifact_detail: str = "summary",
) -> None:
    output_artifacts._emit("", channel=channel)
    output_artifacts._emit(title, channel=channel)
    output_artifacts._emit("=" * 80, channel=channel)

    # Sanitize rows based on artifact detail level
    if artifact_detail in ("summary", "debug", "full"):
        sanitized_rows = [sanitize_scenario_summary(row, artifact_detail) for row in rows]
    else:
        sanitized_rows = rows

    output_artifacts._emit(_compact_json(sanitized_rows), channel=channel)


def run_service_scenarios(
    *,
    scenario_names_to_run: List[str],
    fail_on_regression_warnings: bool = False,
    parallel_scenarios: bool = True,
    scenario_workers: int | None = None,
    no_html_report: bool = False,
    split_files: bool = True,
    legacy_channel: str = "service_legacy",
    stable_session_ids: bool = False,
    reset_session_state: bool = True,
    console_llm: bool = True,
    console_llm_raw: bool = False,
    console_llm_max_chars: int = 10_000,
    artifact_detail: str = "debug",
) -> List[Dict[str, Any]]:
    scenario_summaries: List[Dict[str, Any]] = []
    scenario_names_to_run = list(scenario_names_to_run or [])

    valid_names = sorted(SERVICE_SCENARIOS.keys())
    unknown = [name for name in scenario_names_to_run if name not in SERVICE_SCENARIOS]
    if unknown:
        output_artifacts._emit(f"Unknown scenario(s): {', '.join(unknown)}", channel="service_summary")
        output_artifacts._emit("", channel="service_summary")
        output_artifacts._emit("Valid scenarios:", channel="service_summary")
        output_artifacts._emit(", ".join(valid_names), channel="service_summary")
        raise SystemExit(2)

    if not scenario_names_to_run:
        scenario_names_to_run = valid_names

    max_workers = _effective_scenario_workers(
        int(scenario_workers or 1),
        len(scenario_names_to_run),
        parallel=parallel_scenarios,
    )
    use_parallel = bool(max_workers > 1)

    output_artifacts._emit(f"requested_parallel_scenarios: {parallel_scenarios}", channel="service_summary")
    output_artifacts._emit(f"requested_scenario_workers: {scenario_workers}", channel="service_summary")
    output_artifacts._emit(f"scenario_workers_source: {_scenario_workers_source()}", channel="service_summary")
    output_artifacts._emit(f"scenario_count: {len(scenario_names_to_run)}", channel="service_summary")
    output_artifacts._emit(f"parallel_scenarios: {bool(max_workers > 1)}", channel="service_summary")
    output_artifacts._emit(f"scenario_workers: {max_workers}", channel="service_summary")

    if parallel_scenarios and max_workers <= 1:
        output_artifacts._emit(
            "parallel_note: parallel requested but effective workers is 1; "
            "this usually means only one scenario was selected or scenario-workers/env is 1.",
            channel="service_summary",
        )

    run_id = _new_manual_run_id()

    def run_one(name: str) -> Dict[str, Any]:
        scenario = SERVICE_SCENARIOS[name]
        return _run_one_service_scenario(
            scenario_name=name,
            scenario=scenario,
            run_id=run_id,
            split_files=split_files,
            legacy_channel=legacy_channel,
            stable_session_ids=stable_session_ids,
            reset_session_state=reset_session_state,
            console_llm=console_llm,
            console_llm_raw=console_llm_raw,
            console_llm_max_chars=console_llm_max_chars,
            fail_on_regression_warnings=fail_on_regression_warnings,
            artifact_detail=artifact_detail,
        )

    if use_parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_by_name = {executor.submit(run_one, name): name for name in scenario_names_to_run}
            for future in concurrent.futures.as_completed(future_by_name):
                name = future_by_name[future]
                try:
                    scenario_summaries.append(future.result())
                except Exception as exc:
                    _record_scenario_error(
                        scenario_name=name,
                        session_id=f"manual_service_{name}",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    scenario_summaries.append(
                        {
                            "scenario": name,
                            "error": f"{type(exc).__name__}: {exc}",
                            "turns": [],
                            "scenario_warnings": [f"scenario_runtime_error:{name}:{type(exc).__name__}: {exc}"],
                            "regression_warnings": [f"scenario_runtime_error:{name}:{type(exc).__name__}: {exc}"],
                        }
                    )
    else:
        for name in scenario_names_to_run:
            try:
                scenario_summaries.append(run_one(name))
            except Exception as exc:
                _record_scenario_error(
                    scenario_name=name,
                    session_id=f"manual_service_{name}",
                    error=f"{type(exc).__name__}: {exc}",
                )
                scenario_summaries.append(
                    {
                        "scenario": name,
                        "error": f"{type(exc).__name__}: {exc}",
                        "turns": [],
                        "scenario_warnings": [f"scenario_runtime_error:{name}:{type(exc).__name__}: {exc}"],
                        "regression_warnings": [f"scenario_runtime_error:{name}:{type(exc).__name__}: {exc}"],
                    }
                )

    scenario_summaries.sort(key=lambda row: _safe_str(row.get("scenario") or row.get("scenario_name")))

    # Always use "summary" for global summary to keep it compact,
    # regardless of --artifact-detail flag (which controls per-scenario files only)
    _emit_summary_block(
        title="Manual RPG Service Scenario Summary",
        rows=scenario_summaries,
        channel="service_summary",
        artifact_detail="summary",
    )

    if not no_html_report:
        html_report._write_html_index_v2(
            output_dir=TEST_RESULTS_ROOT,
            scenario_summaries=scenario_summaries,
            scenario_names_to_run=scenario_names_to_run,
        )

    output_artifacts._write_output(
        SERVICE_OUTPUT_PATH,
        channel="service_summary",
        max_chunk_bytes=MANUAL_LOG_MAX_CHUNK_BYTES,
    )

    with _REGRESSION_WARNING_LOCK:
        warning_rows = list(_REGRESSION_WARNING_ROWS)

    if fail_on_regression_warnings and warning_rows:
        raise SystemExit(2)

    return scenario_summaries


def run_requested_transcripts(args: argparse.Namespace) -> None:
    _reset_token_usage()
    output_artifacts._reset_output()

    scenario_names = list(getattr(args, "scenario", []) or [])

    if getattr(args, "service_scenarios", False):
        run_service_scenarios(
            scenario_names_to_run=scenario_names,
            fail_on_regression_warnings=bool(getattr(args, "fail_on_regression_warnings", False)),
            parallel_scenarios=not bool(getattr(args, "no_parallel_scenarios", False)),
            scenario_workers=getattr(args, "scenario_workers", None),
            no_html_report=bool(getattr(args, "no_html_report", False)),
            split_files=not bool(getattr(args, "single_file", False)),
            legacy_channel="service_legacy",
            stable_session_ids=bool(getattr(args, "stable_session_ids", False)),
            reset_session_state=not bool(getattr(args, "no_reset_session_state", False)),
            console_llm=not bool(getattr(args, "no_console_llm", False)),
            console_llm_raw=bool(getattr(args, "console_llm_raw", False)),
            console_llm_max_chars=int(getattr(args, "console_llm_max_chars", 10_000) or 10_000),
            artifact_detail=getattr(args, "artifact_detail", "debug"),
        )
        return

    # Flat transcript mode has been migrated to the CLI module.
    import sys

    from tests.rpg.manual.cli import main as cli_main
    sys.argv = ["manual_llm_transcript.py"] + (getattr(args, "transcript_args", []) or [])
    cli_main()
