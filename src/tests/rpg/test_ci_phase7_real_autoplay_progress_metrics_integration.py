import json


def _turns(count=100, *, repeated=False):
    rows = []
    for index in range(count):
        action = "wait" if repeated else f"progress step {index % 7}"
        location = "location:rusty_flagon" if repeated else f"location:{index % 5}"
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": action,
                "location_id": location,
                "destination_id": f"location:{(index + 1) % 5}" if not repeated and index % 3 == 0 else "",
                "quest_events": [{"quest_id": "quest:old_mill"}] if not repeated and index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if not repeated and index % 20 == 0 else {},
                "journal_updates": ["new clue"] if not repeated and index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if not repeated and index == 40 else None,
            }
        )
    return rows


def test_ci_phase7_real_autoplay_progress_metrics_reads_saved_transcript_and_report(tmp_path):
    from tests.rpg.manual.progress_metrics_certification import build_real_autoplay_progress_metrics_artifact

    rows = _turns()
    (tmp_path / "autoplay_transcript.json").write_text(json.dumps({"rows": rows}, sort_keys=True), encoding="utf-8")
    (tmp_path / "campaign_report.json").write_text(json.dumps({"report_bytes": 250_000}, sort_keys=True), encoding="utf-8")

    artifact = build_real_autoplay_progress_metrics_artifact({}, output_dir=tmp_path)
    readiness = artifact["readiness_result"]

    assert artifact["ok"] is True
    assert artifact["source"] == "deterministic_phase7_real_autoplay_progress_metrics_gate"
    assert artifact["saved_artifacts"]["turns"] == rows
    assert artifact["saved_artifacts"]["report_bytes"] == 250_000
    assert readiness["actual_turns"] == 100
    assert readiness["progress_counts"]["travel"] > 0
    assert readiness["progress_counts"]["quest"] > 0
    assert readiness["progress_counts"]["economy"] > 0
    assert readiness["progress_counts"]["combat"] > 0
    assert readiness["progress_counts"]["journal"] > 0


def test_ci_phase7_real_autoplay_progress_metrics_threads_into_saved_certification_payload(tmp_path):
    from tests.rpg.manual.certification_artifacts import CERTIFICATION_PAYLOAD_FILENAME
    from tests.rpg.manual.progress_metrics_certification import emit_real_autoplay_progress_metrics_certification_artifacts

    (tmp_path / "turn_rows.json").write_text(json.dumps(_turns(), sort_keys=True), encoding="utf-8")
    (tmp_path / "campaign_report.json").write_text(json.dumps({"html": "<html><body>ok</body></html>"}), encoding="utf-8")
    report_path = tmp_path / "html" / "campaign_report.html"

    result = emit_real_autoplay_progress_metrics_certification_artifacts({}, output_dir=tmp_path, report_html_path=report_path)
    payload = json.loads((tmp_path / CERTIFICATION_PAYLOAD_FILENAME).read_text(encoding="utf-8"))
    readiness = payload["certification_result"]["readiness_result"]

    assert result["ok"] is True
    assert result["progress_metrics_source"] == "deterministic_phase7_real_autoplay_progress_metrics_gate"
    assert payload["certification_result"]["certification_status"] == "final_100_turn_certification_passed"
    assert readiness["progress_counts"]["travel"] > 0
    assert report_path.read_text(encoding="utf-8").count("<!-- rpg-phase7-real-autoplay-certification -->") == 1


def test_ci_phase7_real_autoplay_progress_metrics_surfaces_loop_warnings_and_budget_blockers(tmp_path):
    from tests.rpg.manual.progress_metrics_certification import emit_real_autoplay_progress_metrics_certification_artifacts

    (tmp_path / "autoplay_transcript.json").write_text(json.dumps({"turns": _turns(repeated=True)}), encoding="utf-8")
    (tmp_path / "campaign_report.json").write_text(json.dumps({"report_bytes": 6_000_000}), encoding="utf-8")

    result = emit_real_autoplay_progress_metrics_certification_artifacts({}, output_dir=tmp_path)
    payload = json.loads((tmp_path / "phase7_100_turn_certification.json").read_text(encoding="utf-8"))
    readiness = payload["certification_result"]["readiness_result"]
    blocker_kinds = {row["kind"] for row in payload["certification_result"]["blockers"]}
    warning_kinds = {row["warning"] for row in payload["certification_result"]["warnings"] if "warning" in row}

    assert result["ok"] is False
    assert "readiness_critical_blocker" in blocker_kinds
    assert readiness["blockers"][0]["kind"] == "report_growth_budget_exceeded"
    assert "repeated_action_loop_risk" in warning_kinds
    assert "repeated_location_loop_risk" in warning_kinds
    assert "no_progress_loop_risk" in warning_kinds


def test_ci_phase7_real_autoplay_progress_metrics_blocks_missing_rows(tmp_path):
    from tests.rpg.manual.progress_metrics_certification import emit_real_autoplay_progress_metrics_certification_artifacts

    result = emit_real_autoplay_progress_metrics_certification_artifacts({}, output_dir=tmp_path)

    assert result["ok"] is False
    assert result["reason"] == "phase7_real_autoplay_progress_metrics_emitted_with_blockers"
    assert result["progress_metrics_blockers"][0]["kind"] == "missing_real_autoplay_progress_rows"


def test_ci_phase7_real_autoplay_progress_metrics_ready():
    from tests.rpg.manual.progress_metrics_certification import assert_phase7_real_autoplay_progress_metrics_ready

    readiness = assert_phase7_real_autoplay_progress_metrics_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_real_autoplay_progress_metrics_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_real_autoplay_progress_metrics_gate"
