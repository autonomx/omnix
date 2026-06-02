from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from tests.rpg.manual.certification_artifacts import emit_saved_100_turn_certification_artifacts
from tests.rpg.manual.progress_metrics_certification import (
    REPORT_FILENAMES,
    TRANSCRIPT_FILENAMES,
    build_real_autoplay_progress_metrics_artifact,
)
from tests.rpg.manual.saved_state_certification import (
    FINAL_STATE_FILENAMES,
    LOADABLE_STATE_FILENAMES,
    build_real_saved_state_certification_artifact,
)

SOURCE = "deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate"
REPORT_HTML_FILENAMES = (
    "campaign_report.html",
    "autoplay_report.html",
    "manual_report.html",
    "html/campaign_report.html",
    "html/autoplay_report.html",
    "html/manual_report.html",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def discover_live_manual_saved_artifact_completion_inputs(
    *,
    output_dir: Path,
    report_html_path: Path | None = None,
) -> Dict[str, Any]:
    """Discover deterministic manual/autoplay completion artifacts without mutating them."""

    output_root = Path(output_dir)
    diagnostics: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    if not output_root.exists() or not output_root.is_dir():
        blocker = _source_entry("missing_output_directory", output_dir=str(output_root))
        return {
            "ok": False,
            "reason": "phase7_live_manual_saved_artifact_completion_inputs_blocked",
            "output_dir": str(output_root),
            "report_html_path": "",
            "diagnostics": [blocker],
            "blockers": [blocker],
            "source": SOURCE,
        }

    diagnostics.append(_source_entry("completion_output_directory_found", output_dir=str(output_root)))

    resolved_report = Path(report_html_path) if report_html_path is not None else _existing_path(output_root, REPORT_HTML_FILENAMES)
    if resolved_report is not None and resolved_report.is_file():
        diagnostics.append(_source_entry("completion_report_html_found", path=str(resolved_report)))
    else:
        diagnostics.append(_source_entry("missing_report_html", output_dir=str(output_root)))
        resolved_report = None

    if _has_any_file(output_root, TRANSCRIPT_FILENAMES):
        diagnostics.append(_source_entry("completion_transcript_artifact_found", output_dir=str(output_root)))
    else:
        diagnostics.append(_source_entry("missing_transcript_artifacts", output_dir=str(output_root)))

    if _has_any_file(output_root, FINAL_STATE_FILENAMES) and _has_any_file(output_root, LOADABLE_STATE_FILENAMES):
        diagnostics.append(_source_entry("completion_state_checkpoint_artifacts_found", output_dir=str(output_root)))
    else:
        diagnostics.append(_source_entry("missing_state_checkpoint_artifacts", output_dir=str(output_root)))

    return {
        "ok": True,
        "reason": "phase7_live_manual_saved_artifact_completion_inputs_discovered",
        "output_dir": str(output_root),
        "report_html_path": str(resolved_report) if resolved_report is not None else "",
        "diagnostics": diagnostics,
        "blockers": blockers,
        "source": SOURCE,
    }


def build_live_manual_saved_artifact_emission_hook_payload(
    saved_artifacts: Dict[str, Any] | None = None,
    *,
    output_dir: Path,
    report_html_path: Path | None = None,
    expected_turns: int = 100,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Build the provider-free completion hook payload and diagnostics."""

    output_root = Path(output_dir)
    if not enabled:
        diagnostic = _source_entry("skipped_emission", output_dir=str(output_root), reason="emission_hook_disabled")
        return {
            "ok": False,
            "reason": "phase7_live_manual_saved_artifact_emission_skipped",
            "saved_artifacts": dict(_safe_dict(saved_artifacts)),
            "report_html_path": "",
            "diagnostics": [diagnostic],
            "blockers": [],
            "source": SOURCE,
        }

    discovery = discover_live_manual_saved_artifact_completion_inputs(
        output_dir=output_root,
        report_html_path=report_html_path,
    )
    saved = dict(_safe_dict(saved_artifacts))
    diagnostics = list(discovery["diagnostics"])
    blockers = list(discovery["blockers"])

    if discovery.get("ok") is not True:
        saved["emission_hook_source"] = SOURCE
        saved["emission_hook_diagnostics"] = diagnostics
        return {
            "ok": False,
            "reason": "phase7_live_manual_saved_artifact_emission_blocked",
            "saved_artifacts": saved,
            "report_html_path": "",
            "diagnostics": diagnostics,
            "blockers": blockers,
            "source": SOURCE,
        }

    progress = build_real_autoplay_progress_metrics_artifact(saved, output_dir=output_root, expected_turns=expected_turns)
    saved = dict(_safe_dict(progress.get("saved_artifacts")))
    progress_blockers = list(progress.get("blockers", []))
    for blocker in progress_blockers:
        diagnostics.append(_source_entry("certification_payload_emission_blocker", blocker=blocker))
    blockers.extend(progress_blockers)

    state = build_real_saved_state_certification_artifact(saved, output_dir=output_root)
    saved = dict(_safe_dict(state.get("saved_artifacts")))
    state_blockers = list(state.get("blockers", []))
    for blocker in state_blockers:
        diagnostics.append(_source_entry("certification_payload_emission_blocker", blocker=blocker))
    blockers.extend(state_blockers)

    saved["emission_hook_source"] = SOURCE
    saved["emission_hook_diagnostics"] = diagnostics
    saved["emission_hook_blockers"] = blockers
    saved["artifact_source"] = str(saved.get("artifact_source") or SOURCE)

    return {
        "ok": not blockers,
        "reason": "phase7_live_manual_saved_artifact_emission_payload_ready"
        if not blockers
        else "phase7_live_manual_saved_artifact_emission_payload_has_blockers",
        "saved_artifacts": saved,
        "report_html_path": discovery.get("report_html_path", ""),
        "diagnostics": diagnostics,
        "blockers": blockers,
        "source": SOURCE,
    }


def emit_live_manual_saved_artifact_completion_hooks(
    saved_artifacts: Dict[str, Any] | None = None,
    *,
    output_dir: Path,
    report_html_path: Path | None = None,
    expected_turns: int = 100,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Emit saved certification JSON/HTML from real manual/autoplay completion outputs."""

    hook_payload = build_live_manual_saved_artifact_emission_hook_payload(
        saved_artifacts,
        output_dir=output_dir,
        report_html_path=report_html_path,
        expected_turns=expected_turns,
        enabled=enabled,
    )
    if hook_payload.get("reason") in {
        "phase7_live_manual_saved_artifact_emission_skipped",
        "phase7_live_manual_saved_artifact_emission_blocked",
    }:
        result = dict(hook_payload)
        result["emission_hook_source"] = SOURCE
        result["emission_hook_diagnostics"] = hook_payload.get("diagnostics", [])
        result["emission_hook_blockers"] = hook_payload.get("blockers", [])
        return result
    if hook_payload.get("report_html_path"):
        resolved_report_html_path: Path | None = Path(str(hook_payload["report_html_path"]))
    else:
        resolved_report_html_path = None

    emitted = emit_saved_100_turn_certification_artifacts(
        hook_payload["saved_artifacts"],
        output_dir=Path(output_dir),
        report_html_path=resolved_report_html_path,
        expected_turns=expected_turns,
    )
    emitted = dict(emitted)
    emitted["emission_hook_source"] = SOURCE
    emitted["emission_hook_diagnostics"] = hook_payload["diagnostics"]
    emitted["emission_hook_blockers"] = hook_payload["blockers"]
    emitted["ok"] = emitted.get("ok") is True and hook_payload.get("ok") is True
    if hook_payload.get("ok") is not True:
        emitted["reason"] = "phase7_live_manual_saved_artifact_emission_emitted_with_blockers"
    return emitted


def assert_phase7_live_manual_saved_artifact_emission_hooks_ready() -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    if "campaign_report.html" not in REPORT_HTML_FILENAMES:
        blockers.append(_source_entry("missing_campaign_report_html_candidate"))
    if "autoplay_transcript.json" not in TRANSCRIPT_FILENAMES:
        blockers.append(_source_entry("missing_autoplay_transcript_candidate"))
    if "final_session.json" not in FINAL_STATE_FILENAMES:
        blockers.append(_source_entry("missing_final_state_candidate"))
    if "loadable_session.json" not in LOADABLE_STATE_FILENAMES:
        blockers.append(_source_entry("missing_loadable_state_candidate"))
    return {
        "ok": not blockers,
        "reason": "phase7_live_manual_saved_artifact_emission_hooks_ready"
        if not blockers
        else "phase7_live_manual_saved_artifact_emission_hooks_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }
