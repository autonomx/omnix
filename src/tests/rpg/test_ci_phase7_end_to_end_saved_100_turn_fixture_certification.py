import json
import zipfile


def test_ci_phase7_end_to_end_saved_100_turn_fixture_certifies_payload_report_and_zip(tmp_path):
    from tests.rpg.manual.end_to_end_saved_certification import CERTIFICATION_PAYLOAD_FILENAME
    from tests.rpg.manual.end_to_end_saved_certification import certify_end_to_end_saved_100_turn_fixture

    result = certify_end_to_end_saved_100_turn_fixture(tmp_path)
    payload_path = tmp_path / CERTIFICATION_PAYLOAD_FILENAME
    zip_path = tmp_path / "manual-rpg-test-results.zip"
    report_html = (tmp_path / "campaign_report.html").read_text(encoding="utf-8")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    diagnostic_pairs = {(row.get("kind"), row.get("group")) for row in result["diagnostics"]}

    assert result["ok"] is True
    assert result["reason"] == "phase7_end_to_end_saved_100_turn_fixture_certified"
    assert result["source"] == "deterministic_phase7_end_to_end_saved_100_turn_fixture_certification_gate"
    assert payload["certification_result"]["certification_status"] == "final_100_turn_certification_passed"
    assert payload["artifact_writer_source"] == "deterministic_phase7_saved_certification_artifact_writer_gate"
    assert payload["emission_hook_source"] == "deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate"
    assert payload["certification_result"]["actual_turns"] == 100
    assert payload["report_diagnostics"]["source"] == "deterministic_phase7_saved_certification_report_diagnostics_gate"
    assert "Phase 7.7 Real Autoplay Certification" in report_html
    assert "Phase 7 Saved Certification Diagnostics" in report_html
    assert ("bundle_artifact_found", "certification_payload") in diagnostic_pairs
    assert ("bundle_artifact_found", "report_html") in diagnostic_pairs
    assert ("zip_artifact_found", "certification_payload") in diagnostic_pairs
    assert ("zip_artifact_found", "transcript_artifact") in diagnostic_pairs
    assert zip_path.is_file()

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    assert "phase7_100_turn_certification.json" in names
    assert "autoplay_transcript.json" in names
    assert "campaign_report.json" in names
    assert "final_session.json" in names
    assert "loadable_session.json" in names


def test_ci_phase7_end_to_end_saved_100_turn_fixture_surfaces_digest_drift(tmp_path):
    from tests.rpg.manual.end_to_end_saved_certification import certify_end_to_end_saved_100_turn_fixture
    from tests.rpg.manual.end_to_end_saved_certification import write_end_to_end_saved_100_turn_fixture
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    write_end_to_end_saved_100_turn_fixture(tmp_path)
    loadable_path = tmp_path / "loadable_session.json"
    loadable = json.loads(loadable_path.read_text(encoding="utf-8"))
    loadable["session"]["simulation_state"]["travel_state"]["current_location_id"] = "location:drifted"
    loadable_path.write_text(json.dumps(loadable, sort_keys=True), encoding="utf-8")

    emitted = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    payload = json.loads((tmp_path / "phase7_100_turn_certification.json").read_text(encoding="utf-8"))
    blocker_kinds = {row.get("kind") for row in payload["certification_result"]["blockers"]}

    assert emitted["ok"] is False
    assert "final_vs_loaded_checkpoint_digest_mismatch" in blocker_kinds
    assert "final_vs_loaded_state_digest_mismatch" in blocker_kinds

    # A fresh end-to-end fixture should still pass after the drift-specific check.
    clean_result = certify_end_to_end_saved_100_turn_fixture(tmp_path / "clean")
    assert clean_result["ok"] is True


def test_ci_phase7_end_to_end_saved_100_turn_fixture_ready():
    from tests.rpg.manual.end_to_end_saved_certification import (
        assert_phase7_end_to_end_saved_100_turn_fixture_certification_ready,
    )

    readiness = assert_phase7_end_to_end_saved_100_turn_fixture_certification_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_end_to_end_saved_100_turn_fixture_certification_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_end_to_end_saved_100_turn_fixture_certification_gate"
