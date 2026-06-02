import json


def test_ci_phase7_real_completion_path_smoke_skips_missing_output_directory_without_mutation(tmp_path):
    from tests.rpg.manual.completion_path_smoke import emit_phase7_saved_certification_from_completion_path

    missing_dir = tmp_path / "missing-output"
    result = emit_phase7_saved_certification_from_completion_path({}, output_dir=missing_dir)

    assert result["ok"] is False
    assert result["reason"] == "phase7_real_completion_path_smoke_skipped_missing_output_directory"
    assert result["source"] == "deterministic_phase7_real_completion_path_smoke_gate"
    assert result["emission_hook_source"] == ""
    assert {row.get("kind") for row in result["diagnostics"]} == {"missing_output_directory"}
    assert not missing_dir.exists()


def test_ci_phase7_real_completion_path_smoke_skips_incomplete_saved_outputs_without_writing_payload(tmp_path):
    from tests.rpg.manual.completion_path_smoke import emit_phase7_saved_certification_from_completion_path

    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "campaign_report.html").write_text("<html><body>incomplete report</body></html>", encoding="utf-8")

    result = emit_phase7_saved_certification_from_completion_path({}, output_dir=tmp_path)
    blocker_groups = {row.get("group") for row in result["blockers"]}

    assert result["ok"] is False
    assert result["reason"] == "phase7_real_completion_path_smoke_skipped_missing_saved_artifacts"
    assert "transcript_artifact" in blocker_groups
    assert "final_state_artifact" in blocker_groups
    assert "loadable_state_artifact" in blocker_groups
    assert not (tmp_path / "phase7_100_turn_certification.json").exists()


def test_ci_phase7_real_completion_path_smoke_emits_from_complete_saved_outputs(tmp_path):
    from tests.rpg.manual.completion_path_smoke import emit_phase7_saved_certification_from_completion_path
    from tests.rpg.manual.end_to_end_saved_certification import write_end_to_end_saved_100_turn_fixture

    write_end_to_end_saved_100_turn_fixture(tmp_path)
    result = emit_phase7_saved_certification_from_completion_path({}, output_dir=tmp_path)
    payload_path = tmp_path / "phase7_100_turn_certification.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    report_html = (tmp_path / "campaign_report.html").read_text(encoding="utf-8")
    diagnostic_pairs = {(row.get("kind"), row.get("group")) for row in result["completion_path_diagnostics"]}

    assert result["ok"] is True
    assert result["source"] == "deterministic_phase7_real_completion_path_smoke_gate"
    assert result["completion_path_source"] == "deterministic_phase7_real_completion_path_smoke_gate"
    assert result["emission_hook_source"] == "deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate"
    assert payload["emission_hook_source"] == "deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate"
    assert payload["emission_hook_diagnostics"]
    assert payload["emission_hook_blockers"] == []
    assert payload["certification_result"]["certification_status"] == "final_100_turn_certification_passed"
    assert "Phase 7.7 Real Autoplay Certification" in report_html
    assert "Phase 7 Saved Certification Diagnostics" in report_html
    assert ("completion_artifact_found", "report_html") in diagnostic_pairs
    assert ("completion_artifact_found", "transcript_artifact") in diagnostic_pairs
    assert ("completion_artifact_found", "final_state_artifact") in diagnostic_pairs
    assert ("completion_artifact_found", "loadable_state_artifact") in diagnostic_pairs


def test_ci_phase7_real_completion_path_smoke_ready_contract_names_real_entry_points():
    from tests.rpg.manual.completion_path_smoke import assert_phase7_real_completion_path_smoke_ready

    readiness = assert_phase7_real_completion_path_smoke_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_real_completion_path_smoke_ready"
    assert readiness["source"] == "deterministic_phase7_real_completion_path_smoke_gate"
    assert "tests.rpg.manual.cli.main" in readiness["entry_points"]
    assert "tests.rpg.manual.output_artifacts.write_results_zip" in readiness["entry_points"]
    assert "campaign_report.html" in readiness["required_artifacts"]
    assert "autoplay_transcript.json" in readiness["required_artifacts"]
    assert "final_session.json" in readiness["required_artifacts"]
    assert "loadable_session.json" in readiness["required_artifacts"]


def test_ci_phase7_real_completion_path_smoke_is_wired_into_manual_cli_and_workflow():
    cli_source = open("src/tests/rpg/manual/cli.py", encoding="utf-8").read()
    workflow_source = open(".github/workflows/rpg-pr-deterministic.yml", encoding="utf-8").read()

    assert "emit_phase7_saved_certification_from_completion_path" in cli_source
    assert "--no-saved-certification" in cli_source
    assert "RPG CI Phase 7 real completion path smoke gate" in workflow_source
    assert "test_ci_phase7_real_completion_path_smoke.py" in workflow_source
    assert workflow_source.index("RPG CI Phase 7 end-to-end saved 100-turn fixture certification gate") < workflow_source.index(
        "RPG CI Phase 7 real completion path smoke gate"
    )
    assert workflow_source.index("RPG CI Phase 7 real completion path smoke gate") < workflow_source.index(
        "RPG CI runtime facade manifest gate"
    )
