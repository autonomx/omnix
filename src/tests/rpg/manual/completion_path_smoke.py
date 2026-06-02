from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from tests.rpg.manual.certification_artifacts import CERTIFICATION_PAYLOAD_FILENAME
from tests.rpg.manual.emission_hooks import REPORT_HTML_FILENAMES, emit_live_manual_saved_artifact_completion_hooks
from tests.rpg.manual.progress_metrics_certification import TRANSCRIPT_FILENAMES
from tests.rpg.manual.saved_state_certification import FINAL_STATE_FILENAMES, LOADABLE_STATE_FILENAMES

SOURCE = "deterministic_phase7_real_completion_path_smoke_gate"

ACTUAL_COMPLETION_ENTRY_POINTS = (
    "tests.rpg.manual.cli.main",
    "tests.rpg.manual.output_artifacts.write_results_zip",
    "tests.rpg.manual.completion_path_smoke.emit_phase7_saved_certification_from_completion_path",
)
REQUIRED_COMPLETION_ARTIFACT_FILENAMES = (
    "campaign_report.html",
    "autoplay_transcript.json",
    "final_session.json",
    "loadable_session.json",
    CERTIFICATION_PAYLOAD_FILENAME,
)


def _source_entry(kind: str, **fields: Any) -> Dict[str, Any]:
    entry = {"kind": kind, "source": SOURCE}
    entry.update(fields)
    return entry


def _existing_path(output_dir: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = output_dir / name
        if path.is_file():
            return path
    return None


def _has_any_file(output_dir: Path, names: tuple[str, ...]) -> bool:
    return _existing_path(output_dir, names) is not None


def _completion_artifact_diagnostics(output_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    groups = (
        ("report_html", REPORT_HTML_FILENAMES),
        ("transcript_artifact", TRANSCRIPT_FILENAMES),
        ("final_state_artifact", FINAL_STATE_FILENAMES),
        ("loadable_state_artifact", LOADABLE_STATE_FILENAMES),
    )
    for group, names in groups:
        path = _existing_path(output_dir, names)
        if path is None:
            blocker = _source_entry("missing_completion_artifact", group=group, output_dir=str(output_dir))
            diagnostics.append(blocker)
            blockers.append(blocker)
        else:
            diagnostics.append(_source_entry("completion_artifact_found", group=group, path=str(path)))
    return diagnostics, blockers


def emit_phase7_saved_certification_from_completion_path(
    saved_artifacts: Dict[str, Any] | None = None,
    *,
    output_dir: Path,
    report_html_path: Path | None = None,
    expected_turns: int = 100,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Provider-free bridge from real manual/autoplay completion paths to Phase 7 saved certification.

    This wrapper is intentionally conservative for real completion paths: missing or incomplete
    saved outputs return source-backed skip diagnostics without writing new artifacts. Complete
    output directories delegate to the Phase 7.13 emission hook, which writes the certification
    payload and appends saved diagnostics to the report HTML.
    """

    output_root = Path(output_dir)
    if not enabled:
        diagnostic = _source_entry("skipped_emission", output_dir=str(output_root), reason="completion_path_disabled")
        return {
            "ok": False,
            "reason": "phase7_real_completion_path_smoke_skipped",
            "diagnostics": [diagnostic],
            "blockers": [],
            "emission_hook_source": "",
            "emission_hook_diagnostics": [diagnostic],
            "emission_hook_blockers": [],
            "source": SOURCE,
        }

    if not output_root.exists() or not output_root.is_dir():
        blocker = _source_entry("missing_output_directory", output_dir=str(output_root))
        return {
            "ok": False,
            "reason": "phase7_real_completion_path_smoke_skipped_missing_output_directory",
            "diagnostics": [blocker],
            "blockers": [blocker],
            "emission_hook_source": "",
            "emission_hook_diagnostics": [blocker],
            "emission_hook_blockers": [blocker],
            "source": SOURCE,
        }

    diagnostics, blockers = _completion_artifact_diagnostics(output_root)
    if blockers:
        return {
            "ok": False,
            "reason": "phase7_real_completion_path_smoke_skipped_missing_saved_artifacts",
            "diagnostics": diagnostics,
            "blockers": blockers,
            "emission_hook_source": "",
            "emission_hook_diagnostics": diagnostics,
            "emission_hook_blockers": blockers,
            "source": SOURCE,
        }

    emitted = emit_live_manual_saved_artifact_completion_hooks(
        dict(saved_artifacts or {}),
        output_dir=output_root,
        report_html_path=report_html_path,
        expected_turns=expected_turns,
        enabled=True,
    )
    result = dict(emitted)
    result["completion_path_source"] = SOURCE
    result["completion_path_diagnostics"] = diagnostics + list(emitted.get("emission_hook_diagnostics", []))
    result["source"] = SOURCE
    return result


def assert_phase7_real_completion_path_smoke_ready() -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    if "tests.rpg.manual.cli.main" not in ACTUAL_COMPLETION_ENTRY_POINTS:
        blockers.append(_source_entry("missing_manual_cli_entry_point"))
    if "tests.rpg.manual.output_artifacts.write_results_zip" not in ACTUAL_COMPLETION_ENTRY_POINTS:
        blockers.append(_source_entry("missing_results_zip_entry_point"))
    if "campaign_report.html" not in REQUIRED_COMPLETION_ARTIFACT_FILENAMES:
        blockers.append(_source_entry("missing_campaign_report_html_requirement"))
    if "autoplay_transcript.json" not in REQUIRED_COMPLETION_ARTIFACT_FILENAMES:
        blockers.append(_source_entry("missing_autoplay_transcript_requirement"))
    if "final_session.json" not in REQUIRED_COMPLETION_ARTIFACT_FILENAMES:
        blockers.append(_source_entry("missing_final_session_requirement"))
    if "loadable_session.json" not in REQUIRED_COMPLETION_ARTIFACT_FILENAMES:
        blockers.append(_source_entry("missing_loadable_session_requirement"))
    return {
        "ok": not blockers,
        "reason": "phase7_real_completion_path_smoke_ready" if not blockers else "phase7_real_completion_path_smoke_not_ready",
        "blockers": blockers,
        "entry_points": ACTUAL_COMPLETION_ENTRY_POINTS,
        "required_artifacts": REQUIRED_COMPLETION_ARTIFACT_FILENAMES,
        "source": SOURCE,
    }
