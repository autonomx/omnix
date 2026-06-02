import json
import zipfile


SOURCE = "deterministic_phase7_real_artifact_discovery_hardening_gate"


def _turns(count=100):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"artifact discovery step {index % 7}",
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
        "manifest": {"id": "phase7.18:test", "session_id": "phase7.18:test"},
        "installed_packs": ["base"],
        "simulation_state": {
            "travel_state": {"current_location_id": location},
            "player_state": {"inventory_state": {"items": [{"item_id": "ration", "qty": 1}]}},
        },
        "runtime_state": {"tick": 100, "elapsed_ms": 999},
    }


def _write_nested_output_dir(tmp_path):
    rows = _turns()
    session = _session()
    (tmp_path / "reports").mkdir()
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "states").mkdir()
    (tmp_path / "reports" / "campaign_report.html").write_text(
        "<html><body>nested discovery report</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "reports" / "campaign_report.json").write_text(
        json.dumps({"turn_rows": rows, "report_bytes": 2048}, sort_keys=True),
        encoding="utf-8",
    )
    (tmp_path / "transcripts" / "autoplay_transcript.json").write_text(
        json.dumps({"rows": rows}, sort_keys=True),
        encoding="utf-8",
    )
    (tmp_path / "states" / "final_session.json").write_text(
        json.dumps({"session": session}, sort_keys=True),
        encoding="utf-8",
    )
    (tmp_path / "states" / "loadable_session.json").write_text(
        json.dumps({"session": session}, sort_keys=True),
        encoding="utf-8",
    )


def test_ci_phase7_real_artifact_discovery_finds_nested_artifacts(tmp_path):
    from tests.rpg.manual.artifact_discovery import discover_artifact_group, expanded_artifact_candidates

    _write_nested_output_dir(tmp_path)

    candidates = expanded_artifact_candidates(("campaign_report.html", "autoplay_transcript.json", "final_session.json"))
    report = discover_artifact_group(
        output_dir=tmp_path,
        group="report_html",
        names=("campaign_report.html",),
    )
    transcript = discover_artifact_group(
        output_dir=tmp_path,
        group="transcript_artifact",
        names=("autoplay_transcript.json",),
    )
    final = discover_artifact_group(
        output_dir=tmp_path,
        group="final_state_artifact",
        names=("final_session.json",),
    )

    assert "reports/campaign_report.html" in candidates
    assert "transcripts/autoplay_transcript.json" in candidates
    assert "states/final_session.json" in candidates
    assert report["selected_path"] == "reports/campaign_report.html"
    assert transcript["selected_path"] == "transcripts/autoplay_transcript.json"
    assert final["selected_path"] == "states/final_session.json"
    assert report["source"] == SOURCE


def test_ci_phase7_real_artifact_discovery_surfaces_ambiguous_duplicates(tmp_path):
    from tests.rpg.manual.artifact_discovery import discover_artifact_group

    (tmp_path / "reports").mkdir()
    (tmp_path / "campaign_report.html").write_text("root report", encoding="utf-8")
    (tmp_path / "reports" / "campaign_report.html").write_text("nested report", encoding="utf-8")

    result = discover_artifact_group(output_dir=tmp_path, group="report_html", names=("campaign_report.html",))
    diagnostic_kinds = {row["kind"] for row in result["diagnostics"]}

    assert result["selected_path"] == "campaign_report.html"
    assert "ambiguous_artifact_group_candidates" in diagnostic_kinds
    assert "reports/campaign_report.html" in result["matches"]


def test_ci_phase7_real_artifact_discovery_emission_uses_nested_outputs(tmp_path):
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    _write_nested_output_dir(tmp_path)

    result = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    payload = json.loads((tmp_path / "phase7_100_turn_certification.json").read_text(encoding="utf-8"))
    report_html = (tmp_path / "reports" / "campaign_report.html").read_text(encoding="utf-8")
    diagnostic_paths = {row.get("path") for row in result["emission_hook_diagnostics"] if row.get("path")}

    assert result["ok"] is True
    assert payload["certification_result"]["certification_status"] == "final_100_turn_certification_passed"
    assert payload["emission_hook_blockers"] == []
    assert "reports/campaign_report.html" in diagnostic_paths
    assert "transcripts/autoplay_transcript.json" in diagnostic_paths
    assert "states/final_session.json" in diagnostic_paths
    assert "states/loadable_session.json" in diagnostic_paths
    assert "Phase 7 Saved Certification Diagnostics" in report_html


def test_ci_phase7_real_artifact_discovery_bundle_verifies_nested_disk_and_zip(tmp_path):
    from tests.rpg.manual.bundle_verification import build_saved_artifact_bundle_verification
    from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks

    _write_nested_output_dir(tmp_path)
    emitted = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=tmp_path)
    zip_path = tmp_path / "manual-rpg-test-results.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(tmp_path / "phase7_100_turn_certification.json", "phase7_100_turn_certification.json")
        archive.write(tmp_path / "transcripts" / "autoplay_transcript.json", "transcripts/autoplay_transcript.json")
        archive.write(tmp_path / "states" / "final_session.json", "states/final_session.json")
        archive.write(tmp_path / "states" / "loadable_session.json", "states/loadable_session.json")

    result = build_saved_artifact_bundle_verification(output_dir=tmp_path, zip_path=zip_path)
    diagnostic_pairs = {(row.get("kind"), row.get("group")) for row in result["diagnostics"]}

    assert emitted["ok"] is True
    assert result["ok"] is True
    assert ("bundle_artifact_found", "report_html") in diagnostic_pairs
    assert ("bundle_artifact_found", "transcript_artifact") in diagnostic_pairs
    assert ("zip_artifact_found", "transcript_artifact") in diagnostic_pairs
    assert ("zip_artifact_found", "final_state_artifact") in diagnostic_pairs
    assert ("zip_artifact_found", "loadable_state_artifact") in diagnostic_pairs


def test_ci_phase7_real_artifact_discovery_ready_and_workflow_wired():
    from tests.rpg.manual.artifact_discovery import assert_phase7_real_artifact_discovery_hardening_ready

    workflow_source = open(".github/workflows/rpg-pr-deterministic.yml", encoding="utf-8").read()
    readiness = assert_phase7_real_artifact_discovery_hardening_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_real_artifact_discovery_hardening_ready"
    assert readiness["source"] == SOURCE
    assert "RPG CI Phase 7 real artifact discovery hardening gate" in workflow_source
    assert "test_ci_phase7_real_artifact_discovery_hardening.py" in workflow_source
    assert workflow_source.index("RPG CI Phase 7 real completion path smoke gate") < workflow_source.index(
        "RPG CI Phase 7 real artifact discovery hardening gate"
    )
    assert workflow_source.index("RPG CI Phase 7 real artifact discovery hardening gate") < workflow_source.index(
        "RPG CI runtime facade manifest gate"
    )
