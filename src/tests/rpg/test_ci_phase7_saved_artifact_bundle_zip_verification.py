import json
import zipfile


def _turns(count=100):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"bundle verification step {index % 7}",
                "location_id": f"location:{index % 5}",
                "destination_id": f"location:{(index + 1) % 5}" if index % 3 == 0 else "",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return rows


def _session():
    return {
        "manifest": {"id": "phase7.14:test", "session_id": "phase7.14:test"},
        "installed_packs": ["base"],
        "simulation_state": {
            "travel_state": {"current_location_id": "location:old_mill"},
            "player_state": {"inventory_state": {"items": [{"item_id": "ration", "qty": 1}]}},
        },
        "runtime_state": {"tick": 100, "elapsed_ms": 999},
    }


def _write_complete_output_dir(tmp_path):
    rows = _turns()
    session = _session()
    (tmp_path / "autoplay_transcript.json").write_text(json.dumps({"rows": rows}, sort_keys=True), encoding="utf-8")
    (tmp_path / "campaign_report.html").write_text("<html><body>bundle report</body></html>", encoding="utf-8")
    (tmp_path / "final_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")
    (tmp_path / "loadable_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")


def test_ci_phase7_saved_artifact_bundle_zip_verification_writes_and_verifies_zip(tmp_path, monkeypatch):
    from tests.rpg.manual import output_artifacts
    from tests.rpg.manual.bundle_verification import write_and_verify_saved_artifact_bundle_zip
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    _write_complete_output_dir(tmp_path)
    monkeypatch.setattr(output_artifacts, "TEST_RESULTS_ROOT", tmp_path)

    emitted = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    result = write_and_verify_saved_artifact_bundle_zip(
        output_dir=tmp_path,
        zip_path=tmp_path / "manual-rpg-test-results.zip",
    )
    diagnostic_pairs = {(row.get("kind"), row.get("group")) for row in result["diagnostics"]}

    assert emitted["ok"] is True
    assert result["ok"] is True
    assert result["source"] == "deterministic_phase7_saved_artifact_bundle_zip_verification_gate"
    assert ("bundle_artifact_found", "certification_payload") in diagnostic_pairs
    assert ("bundle_artifact_found", "report_html") in diagnostic_pairs
    assert ("zip_artifact_found", "certification_payload") in diagnostic_pairs
    assert ("zip_artifact_found", "transcript_artifact") in diagnostic_pairs
    with zipfile.ZipFile(tmp_path / "manual-rpg-test-results.zip", "r") as archive:
        names = set(archive.namelist())
    assert "phase7_100_turn_certification.json" in names
    assert "autoplay_transcript.json" in names
    assert "final_session.json" in names
    assert "loadable_session.json" in names
    assert "campaign_report.html" in names


def test_ci_phase7_saved_artifact_bundle_zip_verification_surfaces_missing_artifacts(tmp_path):
    from tests.rpg.manual.bundle_verification import build_saved_artifact_bundle_verification

    (tmp_path / "manual-rpg-test-results.zip").write_bytes(b"not a zip")

    result = build_saved_artifact_bundle_verification(
        output_dir=tmp_path,
        zip_path=tmp_path / "manual-rpg-test-results.zip",
    )
    blocker_kinds = {row["kind"] for row in result["blockers"]}
    blocker_groups = {row.get("group") for row in result["blockers"]}

    assert result["ok"] is False
    assert result["reason"] == "phase7_saved_artifact_bundle_zip_blocked"
    assert "missing_bundle_artifact" in blocker_kinds
    assert "unreadable_or_empty_results_zip" in blocker_kinds
    assert "certification_payload" in blocker_groups
    assert "report_html" in blocker_groups


def test_ci_phase7_saved_artifact_bundle_zip_verification_detects_missing_zip_member(tmp_path):
    from tests.rpg.manual.bundle_verification import build_saved_artifact_bundle_verification
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    _write_complete_output_dir(tmp_path)
    emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    with zipfile.ZipFile(tmp_path / "manual-rpg-test-results.zip", "w") as archive:
        archive.write(tmp_path / "phase7_100_turn_certification.json", "phase7_100_turn_certification.json")

    result = build_saved_artifact_bundle_verification(
        output_dir=tmp_path,
        zip_path=tmp_path / "manual-rpg-test-results.zip",
    )
    missing_zip_groups = {row.get("group") for row in result["blockers"] if row["kind"] == "missing_zip_artifact"}

    assert result["ok"] is False
    assert "transcript_artifact" in missing_zip_groups
    assert "final_state_artifact" in missing_zip_groups
    assert "loadable_state_artifact" in missing_zip_groups


def test_ci_phase7_saved_artifact_bundle_zip_verification_ready():
    from tests.rpg.manual.bundle_verification import assert_phase7_saved_artifact_bundle_zip_verification_ready

    readiness = assert_phase7_saved_artifact_bundle_zip_verification_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_saved_artifact_bundle_zip_verification_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_saved_artifact_bundle_zip_verification_gate"
