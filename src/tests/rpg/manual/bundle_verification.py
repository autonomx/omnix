from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

from tests.rpg.manual.artifact_discovery import discover_artifact_group, expanded_artifact_candidates, normalize_artifact_name
from tests.rpg.manual.certification_artifacts import CERTIFICATION_PAYLOAD_FILENAME
from tests.rpg.manual.emission_hooks import REPORT_HTML_FILENAMES
from tests.rpg.manual.output_artifacts import write_results_zip
from tests.rpg.manual.progress_metrics_certification import TRANSCRIPT_FILENAMES
from tests.rpg.manual.saved_state_certification import FINAL_STATE_FILENAMES, LOADABLE_STATE_FILENAMES

SOURCE = "deterministic_phase7_saved_artifact_bundle_zip_verification_gate"
REQUIRED_BUNDLE_GROUPS = {
    "certification_payload": (CERTIFICATION_PAYLOAD_FILENAME,),
    "report_html": REPORT_HTML_FILENAMES,
    "transcript_artifact": TRANSCRIPT_FILENAMES,
    "final_state_artifact": FINAL_STATE_FILENAMES,
    "loadable_state_artifact": LOADABLE_STATE_FILENAMES,
}
REQUIRED_ZIP_GROUPS = {
    "certification_payload": (CERTIFICATION_PAYLOAD_FILENAME,),
    "transcript_artifact": TRANSCRIPT_FILENAMES,
    "final_state_artifact": FINAL_STATE_FILENAMES,
    "loadable_state_artifact": LOADABLE_STATE_FILENAMES,
}


def _source_entry(kind: str, **fields: Any) -> Dict[str, Any]:
    entry = {"kind": kind, "source": SOURCE}
    entry.update(fields)
    return entry


def _zip_names(zip_path: Path) -> set[str]:
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            return {normalize_artifact_name(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile):
        return set()


def _matching_zip_name(names: set[str], candidates: Iterable[str]) -> str:
    normalized_candidates = set(expanded_artifact_candidates(candidates))
    for name in sorted(names):
        if name in normalized_candidates:
            return name
    return ""


def build_saved_artifact_bundle_verification(
    *,
    output_dir: Path,
    zip_path: Path | None = None,
    expected_zip_groups: Dict[str, tuple[str, ...]] | None = None,
) -> Dict[str, Any]:
    """Verify saved certification artifacts exist on disk and in the results ZIP."""

    output_root = Path(output_dir)
    zip_file = Path(zip_path) if zip_path is not None else output_root / "manual-rpg-test-results.zip"
    diagnostics: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    if not output_root.exists() or not output_root.is_dir():
        blockers.append(_source_entry("missing_bundle_output_directory", output_dir=str(output_root)))
    else:
        diagnostics.append(_source_entry("bundle_output_directory_found", output_dir=str(output_root)))
        for group, names in REQUIRED_BUNDLE_GROUPS.items():
            discovery = discover_artifact_group(output_dir=output_root, group=group, names=names, source=SOURCE)
            diagnostics.extend(discovery["diagnostics"])
            if discovery.get("selected_path"):
                diagnostics.append(_source_entry("bundle_artifact_found", group=group, path=discovery["selected_path"]))
            else:
                blockers.append(_source_entry("missing_bundle_artifact", group=group, candidates=list(names)))
            blockers.extend(discovery["blockers"])

    if not zip_file.is_file():
        blockers.append(_source_entry("missing_results_zip", path=str(zip_file)))
        zip_entries: set[str] = set()
    else:
        zip_entries = _zip_names(zip_file)
        if not zip_entries:
            blockers.append(_source_entry("unreadable_or_empty_results_zip", path=str(zip_file)))
        else:
            diagnostics.append(_source_entry("results_zip_found", path=str(zip_file), entries=len(zip_entries)))

    zip_groups = expected_zip_groups or REQUIRED_ZIP_GROUPS
    if zip_entries:
        for group, names in zip_groups.items():
            match = _matching_zip_name(zip_entries, names)
            if match:
                diagnostics.append(_source_entry("zip_artifact_found", group=group, path=match))
            else:
                blockers.append(_source_entry("missing_zip_artifact", group=group, candidates=list(names)))

    return {
        "ok": not blockers,
        "reason": "phase7_saved_artifact_bundle_zip_verified"
        if not blockers
        else "phase7_saved_artifact_bundle_zip_blocked",
        "output_dir": str(output_root),
        "zip_path": str(zip_file),
        "diagnostics": diagnostics,
        "blockers": blockers,
        "source": SOURCE,
    }


def write_and_verify_saved_artifact_bundle_zip(
    *,
    output_dir: Path,
    zip_path: Path | None = None,
) -> Dict[str, Any]:
    """Write a manual-style results ZIP, then verify saved artifact inclusion."""

    output_root = Path(output_dir)
    zip_file = Path(zip_path) if zip_path is not None else output_root / "manual-rpg-test-results.zip"
    write_results_zip(zip_file)
    return build_saved_artifact_bundle_verification(output_dir=output_root, zip_path=zip_file)


def assert_phase7_saved_artifact_bundle_zip_verification_ready() -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    if CERTIFICATION_PAYLOAD_FILENAME not in REQUIRED_BUNDLE_GROUPS["certification_payload"]:
        blockers.append(_source_entry("missing_certification_payload_requirement"))
    if CERTIFICATION_PAYLOAD_FILENAME not in REQUIRED_ZIP_GROUPS["certification_payload"]:
        blockers.append(_source_entry("missing_certification_payload_zip_requirement"))
    if "autoplay_transcript.json" not in REQUIRED_ZIP_GROUPS["transcript_artifact"]:
        blockers.append(_source_entry("missing_transcript_zip_requirement"))
    if "final_session.json" not in REQUIRED_ZIP_GROUPS["final_state_artifact"]:
        blockers.append(_source_entry("missing_final_state_zip_requirement"))
    if "loadable_session.json" not in REQUIRED_ZIP_GROUPS["loadable_state_artifact"]:
        blockers.append(_source_entry("missing_loadable_state_zip_requirement"))
    return {
        "ok": not blockers,
        "reason": "phase7_saved_artifact_bundle_zip_verification_ready"
        if not blockers
        else "phase7_saved_artifact_bundle_zip_verification_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }
