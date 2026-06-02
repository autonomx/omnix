import json


def _turns(count=100):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"real saved state step {index % 7}",
                "location_id": f"location:{index % 5}",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return rows


def _session(location="location:old_mill"):
    return {
        "manifest": {"id": "phase7.10:test", "session_id": "phase7.10:test"},
        "installed_packs": ["base"],
        "simulation_state": {
            "travel_state": {"current_location_id": location},
            "player_state": {"inventory_state": {"items": [{"item_id": "ration", "qty": 1}]}},
        },
        "runtime_state": {"tick": 100, "elapsed_ms": 999},
    }


def _saved_artifacts():
    return {
        "transcript": {"rows": _turns(), "text": "real saved state transcript"},
        "report": {"html": "<html><body>real saved state report</body></html>"},
        "artifact_source": "test_phase7_real_saved_state_certification_integration",
    }


def test_ci_phase7_real_saved_state_certification_reads_final_and_loadable_state(tmp_path):
    from tests.rpg.manual.saved_state_certification import build_real_saved_state_certification_artifact

    session = _session()
    (tmp_path / "final_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")
    (tmp_path / "loadable_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")

    artifact = build_real_saved_state_certification_artifact(_saved_artifacts(), output_dir=tmp_path)
    saved = artifact["saved_artifacts"]

    assert artifact["ok"] is True
    assert artifact["source"] == "deterministic_phase7_real_saved_state_certification_gate"
    assert saved["final_checkpoint_digest"] == saved["loaded_checkpoint_digest"]
    assert saved["final_state_digest"] == saved["loaded_state_digest"]
    assert saved["state_diff_source"] == "deterministic_phase7_real_saved_state_certification_gate"
    assert {row["kind"] for row in artifact["metadata"]} == {"final_saved_state", "loadable_saved_state"}


def test_ci_phase7_real_saved_state_certification_emits_payload_and_html(tmp_path):
    from tests.rpg.manual.certification_artifacts import CERTIFICATION_PAYLOAD_FILENAME
    from tests.rpg.manual.saved_state_certification import emit_real_saved_state_certification_artifacts

    session = _session()
    (tmp_path / "final_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")
    (tmp_path / "loadable_session.json").write_text(json.dumps({"session": session}, sort_keys=True), encoding="utf-8")
    report_path = tmp_path / "html" / "campaign_report.html"

    result = emit_real_saved_state_certification_artifacts(
        _saved_artifacts(),
        output_dir=tmp_path,
        report_html_path=report_path,
    )
    payload = json.loads((tmp_path / CERTIFICATION_PAYLOAD_FILENAME).read_text(encoding="utf-8"))
    report_html = report_path.read_text(encoding="utf-8")

    assert result["ok"] is True
    assert result["reason"] == "phase7_saved_certification_artifacts_emitted"
    assert result["saved_state_source"] == "deterministic_phase7_real_saved_state_certification_gate"
    assert payload["certification_result"]["certification_status"] == "final_100_turn_certification_passed"
    assert payload["normalized_artifact"]["state_diff_source"] == "deterministic_phase7_real_saved_state_certification_gate"
    assert "<!-- rpg-phase7-real-autoplay-certification -->" in report_html


def test_ci_phase7_real_saved_state_certification_blocks_missing_and_mismatched_state(tmp_path):
    from tests.rpg.manual.saved_state_certification import emit_real_saved_state_certification_artifacts

    (tmp_path / "final_session.json").write_text(json.dumps({"session": _session("location:old_mill")}, sort_keys=True), encoding="utf-8")
    (tmp_path / "loadable_session.json").write_text(
        json.dumps({"session": _session("location:rusty_flagon")}, sort_keys=True),
        encoding="utf-8",
    )

    result = emit_real_saved_state_certification_artifacts(_saved_artifacts(), output_dir=tmp_path)
    payload = json.loads((tmp_path / "phase7_100_turn_certification.json").read_text(encoding="utf-8"))
    blocker_kinds = {row["kind"] for row in payload["certification_result"]["blockers"]}

    assert result["ok"] is False
    assert "final_vs_loaded_checkpoint_digest_mismatch" in blocker_kinds
    assert "final_vs_loaded_state_digest_mismatch" in blocker_kinds


def test_ci_phase7_real_saved_state_certification_ready():
    from tests.rpg.manual.saved_state_certification import assert_phase7_real_saved_state_certification_ready

    readiness = assert_phase7_real_saved_state_certification_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_real_saved_state_certification_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_real_saved_state_certification_gate"
