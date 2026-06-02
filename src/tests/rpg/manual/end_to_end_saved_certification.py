from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from tests.rpg.manual import output_artifacts
from tests.rpg.manual.bundle_verification import write_and_verify_saved_artifact_bundle_zip
from tests.rpg.manual.certification_artifacts import CERTIFICATION_PAYLOAD_FILENAME
from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

SOURCE = "deterministic_phase7_end_to_end_saved_100_turn_fixture_certification_gate"
RESULTS_ZIP_FILENAME = "manual-rpg-test-results.zip"


def _source_entry(kind: str, **fields: Any) -> Dict[str, Any]:
    entry = {"kind": kind, "source": SOURCE}
    entry.update(fields)
    return entry


def _turn_rows(count: int = 100) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"end to end certification step {index % 9}",
                "location_id": f"location:{index % 5}",
                "destination_id": f"location:{(index + 1) % 5}" if index % 3 == 0 else "",
                "quest_events": [{"quest_id": "quest:old_mill", "event": "advanced"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new saved certification clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road", "outcome": "won"} if index == 40 else None,
            }
        )
    return rows


def _session() -> Dict[str, Any]:
    return {
        "manifest": {"id": "phase7.16:test", "session_id": "phase7.16:test"},
        "installed_packs": ["base"],
        "simulation_state": {
            "travel_state": {"current_location_id": "location:old_mill"},
            "player_state": {
                "inventory_state": {"items": [{"item_id": "ration", "qty": 1}]},
                "currency": {"gold": 1, "silver": 12, "copper": 0},
            },
            "quest_state": {"active": ["quest:old_mill"], "completed": ["quest:road_probe"]},
        },
        "runtime_state": {"tick": 100, "elapsed_ms": 999},
    }


def write_end_to_end_saved_100_turn_fixture(output_dir: Path) -> Dict[str, Any]:
    """Write a canonical tiny saved output directory that mirrors manual/autoplay artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    rows = _turn_rows()
    session_payload = {"session": _session()}
    transcript_path = output_root / "autoplay_transcript.json"
    report_json_path = output_root / "campaign_report.json"
    report_html_path = output_root / "campaign_report.html"
    final_state_path = output_root / "final_session.json"
    loadable_state_path = output_root / "loadable_session.json"

    transcript_path.write_text(json.dumps({"rows": rows}, sort_keys=True), encoding="utf-8")
    report_json_path.write_text(json.dumps({"turn_rows": rows, "report_bytes": 1024}, sort_keys=True), encoding="utf-8")
    report_html_path.write_text("<html><body>phase 7.16 saved fixture report</body></html>", encoding="utf-8")
    final_state_path.write_text(json.dumps(session_payload, sort_keys=True), encoding="utf-8")
    loadable_state_path.write_text(json.dumps(session_payload, sort_keys=True), encoding="utf-8")

    return {
        "ok": True,
        "reason": "phase7_end_to_end_saved_100_turn_fixture_written",
        "output_dir": str(output_root),
        "turn_count": len(rows),
        "artifacts": {
            "transcript": str(transcript_path),
            "report_json": str(report_json_path),
            "report_html": str(report_html_path),
            "final_state": str(final_state_path),
            "loadable_state": str(loadable_state_path),
        },
        "source": SOURCE,
    }


def _read_payload(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def certify_end_to_end_saved_100_turn_fixture(output_dir: Path) -> Dict[str, Any]:
    """Compose emission, report append, saved payload, and bundle/ZIP verification."""

    output_root = Path(output_dir)
    fixture = write_end_to_end_saved_100_turn_fixture(output_root)
    emitted = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=output_root)

    previous_root = output_artifacts.TEST_RESULTS_ROOT
    try:
        output_artifacts.TEST_RESULTS_ROOT = output_root
        bundle = write_and_verify_saved_artifact_bundle_zip(
            output_dir=output_root,
            zip_path=output_root / RESULTS_ZIP_FILENAME,
        )
    finally:
        output_artifacts.TEST_RESULTS_ROOT = previous_root

    payload_path = output_root / CERTIFICATION_PAYLOAD_FILENAME
    payload = _read_payload(payload_path)
    report_html = (output_root / "campaign_report.html").read_text(encoding="utf-8")
    certification = payload.get("certification_result") if isinstance(payload.get("certification_result"), dict) else {}
    certification_status = certification.get("certification_status", "")
    diagnostics = list(emitted.get("emission_hook_diagnostics", [])) + list(bundle.get("diagnostics", []))
    blockers: List[Dict[str, Any]] = []

    if fixture.get("ok") is not True:
        blockers.append(_source_entry("fixture_write_failed"))
    if emitted.get("ok") is not True:
        blockers.append(_source_entry("emission_hook_failed", reason=emitted.get("reason", "")))
    if bundle.get("ok") is not True:
        blockers.append(_source_entry("bundle_zip_verification_failed", reason=bundle.get("reason", "")))
    if certification_status != "final_100_turn_certification_passed":
        blockers.append(_source_entry("certification_status_not_passed", status=certification_status))
    if "Phase 7.7 Real Autoplay Certification" not in report_html:
        blockers.append(_source_entry("saved_report_html_missing_certification_section"))
    if payload.get("artifact_writer_source") != "deterministic_phase7_saved_certification_artifact_writer_gate":
        blockers.append(_source_entry("payload_missing_artifact_writer_source"))
    if payload.get("emission_hook_source") != "deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate":
        blockers.append(_source_entry("payload_missing_emission_hook_source"))

    return {
        "ok": not blockers,
        "reason": "phase7_end_to_end_saved_100_turn_fixture_certified"
        if not blockers
        else "phase7_end_to_end_saved_100_turn_fixture_blocked",
        "output_dir": str(output_root),
        "payload_path": str(payload_path),
        "zip_path": str(output_root / RESULTS_ZIP_FILENAME),
        "fixture": fixture,
        "emitted": emitted,
        "bundle_verification": bundle,
        "payload": payload,
        "diagnostics": diagnostics,
        "blockers": blockers,
        "source": SOURCE,
    }


def assert_phase7_end_to_end_saved_100_turn_fixture_certification_ready() -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    if not CERTIFICATION_PAYLOAD_FILENAME.endswith(".json"):
        blockers.append(_source_entry("certification_payload_filename_not_json"))
    if RESULTS_ZIP_FILENAME != "manual-rpg-test-results.zip":
        blockers.append(_source_entry("unexpected_results_zip_filename"))
    return {
        "ok": not blockers,
        "reason": "phase7_end_to_end_saved_100_turn_fixture_certification_ready"
        if not blockers
        else "phase7_end_to_end_saved_100_turn_fixture_certification_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }
