import json


def _turns(count=100):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"completion hook step {index % 7}",
                "location_id": f"location:{index % 5}",
                "destination_id": f"location:{(index + 1) % 5}" if index % 3 == 0 else "",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return rows


def _session(location="location:old_mill"):
    return {
        "manifest": {"id": "phase7.13:test", "session_id": "phase7.13:test"},
        "installed_packs": ["base"],
        "simulation_state": {
            "travel_state": {"current_location_id": location},
            "player_state": {"inventory_state": {"items": [{"item_id": "ration", "qty": 1}]}},
        },
        "runtime_state": {"tick": 100, "elapsed_ms": 999},
    }


def _write_complete_output_dir(tmp_path):
    rows = _turns()
    session = _session()
    (tmp_path / "autoplay_transcript.json").write_text(json.dumps({"rows": rows}, sort_keys=True), encoding="utf-8")
    (tmp_path / "campaign_report.html").write_text("<html><body>completion report</body></html>", encoding="utf-8")
    (tmp_path / "final_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")
    (tmp_path / "loadable_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")


def test_ci_phase7_live_manual_saved_artifact_completion_hook_emits_payload_and_appends_html(tmp_path):
    from tests.rpg.manual.certification_artifacts import CERTIFICATION_PAYLOAD_FILENAME
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    _write_complete_output_dir(tmp_path)

    result = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    payload = json.loads((tmp_path / CERTIFICATION_PAYLOAD_FILENAME).read_text(encoding="utf-8"))
    report_html = (tmp_path / "campaign_report.html").read_text(encoding="utf-8")
    diagnostic_kinds = {row["kind"] for row in result["emission_hook_diagnostics"]}

    assert result["ok"] is True
    assert result["emission_hook_source"] == "deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate"
    assert payload["certification_result"]["certification_status"] == "final_100_turn_certification_passed"
    assert payload["normalized_artifact"]["emission_hook_source"] == result["emission_hook_source"]
    assert "completion_report_html_found" in diagnostic_kinds
    assert "completion_transcript_artifact_found" in diagnostic_kinds
    assert "completion_state_checkpoint_artifacts_found" in diagnostic_kinds
    assert report_html.count("<!-- rpg-phase7-real-autoplay-certification -->") == 1
    second = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    assert second["ok"] is True
    assert (tmp_path / "campaign_report.html").read_text(encoding="utf-8").count(
        "<!-- rpg-phase7-real-autoplay-certification -->"
    ) == 1


def test_ci_phase7_live_manual_saved_artifact_completion_hook_surfaces_missing_directory(tmp_path):
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    missing_dir = tmp_path / "missing-output"

    result = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=missing_dir)

    assert result["ok"] is False
    assert result["reason"] == "phase7_live_manual_saved_artifact_emission_blocked"
    assert result["emission_hook_blockers"][0]["kind"] == "missing_output_directory"


def test_ci_phase7_live_manual_saved_artifact_completion_hook_can_skip_without_mutation(tmp_path):
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    _write_complete_output_dir(tmp_path)

    result = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path, enabled=False)

    assert result["ok"] is False
    assert result["reason"] == "phase7_live_manual_saved_artifact_emission_skipped"
    assert result["diagnostics"][0]["kind"] == "skipped_emission"
    assert not (tmp_path / "phase7_100_turn_certification.json").exists()
    assert "<!-- rpg-phase7-real-autoplay-certification -->" not in (tmp_path / "campaign_report.html").read_text(
        encoding="utf-8"
    )


def test_ci_phase7_live_manual_saved_artifact_completion_hook_emits_with_missing_artifact_diagnostics(tmp_path):
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    result = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    payload = json.loads((tmp_path / "phase7_100_turn_certification.json").read_text(encoding="utf-8"))
    diagnostic_kinds = {row["kind"] for row in result["emission_hook_diagnostics"]}

    assert result["ok"] is False
    assert result["reason"] == "phase7_live_manual_saved_artifact_emission_emitted_with_blockers"
    assert "missing_report_html" in diagnostic_kinds
    assert "missing_transcript_artifacts" in diagnostic_kinds
    assert "missing_state_checkpoint_artifacts" in diagnostic_kinds
    assert "certification_payload_emission_blocker" in diagnostic_kinds
    assert payload["normalized_artifact"]["emission_hook_diagnostics"]


def test_ci_phase7_live_manual_saved_artifact_completion_hook_ready():
    from tests.rpg.manual.emission_hooks import assert_phase7_live_manual_saved_artifact_emission_hooks_ready

    readiness = assert_phase7_live_manual_saved_artifact_emission_hooks_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_live_manual_saved_artifact_emission_hooks_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate"
