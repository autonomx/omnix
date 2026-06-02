import json
import zipfile


def _saved_artifacts(count=100):
    turns = []
    for index in range(count):
        turns.append(
            {
                "turn_index": index + 1,
                "action_text": f"saved writer step {index % 7}",
                "location_id": f"location:{index % 5}",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return {
        "transcript": {
            "rows": turns,
            "text": "\n".join(row["action_text"] for row in turns),
        },
        "report": {"html": "<html><body><h1>Campaign Report</h1></body></html>"},
        "checkpoint": {
            "final_checkpoint_digest": "digest:phase7:writer",
            "loaded_checkpoint_digest": "digest:phase7:writer",
        },
        "artifact_source": "test_phase7_saved_certification_artifact_writer",
    }


def test_ci_phase7_saved_certification_artifact_writer_emits_json_and_html(tmp_path):
    from tests.rpg.manual.certification_artifacts import (
        CERTIFICATION_PAYLOAD_FILENAME,
        emit_saved_100_turn_certification_artifacts,
    )

    report_path = tmp_path / "manual-html" / "campaign_report.html"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("<html><body><h1>Campaign Report</h1></body></html>", encoding="utf-8")

    result = emit_saved_100_turn_certification_artifacts(
        _saved_artifacts(),
        output_dir=tmp_path,
        report_html_path=report_path,
    )
    payload_path = tmp_path / CERTIFICATION_PAYLOAD_FILENAME
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    report_html = report_path.read_text(encoding="utf-8")

    assert result["ok"] is True
    assert result["reason"] == "phase7_saved_certification_artifacts_emitted"
    assert result["source"] == "deterministic_phase7_saved_certification_artifact_writer_gate"
    assert result["payload_path"] == str(payload_path)
    assert result["payload_bytes"] > 0
    assert result["html_report"]["appended"] is True
    assert payload["artifact_writer_source"] == "deterministic_phase7_saved_certification_artifact_writer_gate"
    assert payload["certification_result"]["certification_status"] == "final_100_turn_certification_passed"
    assert "<!-- rpg-phase7-real-autoplay-certification -->" in report_html


def test_ci_phase7_saved_certification_artifact_writer_is_idempotent_and_zip_included(tmp_path):
    from tests.rpg.manual.certification_artifacts import (
        CERTIFICATION_PAYLOAD_FILENAME,
        emit_saved_100_turn_certification_artifacts,
    )
    from tests.rpg.manual.output_artifacts import _is_result_zip_candidate

    report_path = tmp_path / "campaign_report.html"
    emit_saved_100_turn_certification_artifacts(_saved_artifacts(), output_dir=tmp_path, report_html_path=report_path)
    first_html = report_path.read_text(encoding="utf-8")
    emit_saved_100_turn_certification_artifacts(_saved_artifacts(), output_dir=tmp_path, report_html_path=report_path)
    second_html = report_path.read_text(encoding="utf-8")
    payload_path = tmp_path / CERTIFICATION_PAYLOAD_FILENAME

    assert first_html == second_html
    assert second_html.count("<!-- rpg-phase7-real-autoplay-certification -->") == 1
    assert _is_result_zip_candidate(payload_path) is True

    zip_path = tmp_path / "results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if _is_result_zip_candidate(payload_path):
            zf.write(payload_path, payload_path.name)
    with zipfile.ZipFile(zip_path, "r") as zf:
        assert CERTIFICATION_PAYLOAD_FILENAME in zf.namelist()


def test_ci_phase7_saved_certification_artifact_writer_blocks_bad_artifacts(tmp_path):
    from tests.rpg.manual.certification_artifacts import emit_saved_100_turn_certification_artifacts

    saved = _saved_artifacts(99)
    saved["checkpoint"]["loaded_checkpoint_digest"] = "digest:phase7:writer-drift"
    result = emit_saved_100_turn_certification_artifacts(saved, output_dir=tmp_path)
    payload = json.loads((tmp_path / "phase7_100_turn_certification.json").read_text(encoding="utf-8"))
    blocker_kinds = {row["kind"] for row in payload["certification_result"]["blockers"]}

    assert result["ok"] is False
    assert result["reason"] == "phase7_saved_certification_artifacts_emitted_with_blockers"
    assert "artifact_turn_count_not_exact" in blocker_kinds
    assert "final_vs_loaded_checkpoint_digest_mismatch" in blocker_kinds


def test_ci_phase7_saved_certification_artifact_writer_readiness():
    from tests.rpg.manual.certification_artifacts import assert_phase7_saved_certification_artifact_writer_ready

    readiness = assert_phase7_saved_certification_artifact_writer_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_saved_certification_artifact_writer_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_saved_certification_artifact_writer_gate"
