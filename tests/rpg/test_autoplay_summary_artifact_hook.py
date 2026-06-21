import json

from tests.rpg.autoplay.summary_artifact_hook import attach_summary_artifact_status


def test_attach_summary_artifact_status_promotes_applied_action_text(tmp_path):
    summary_path = tmp_path / "autoplay-summary.json"
    transcript_path = tmp_path / "autoplay-transcript.json"
    rows = [
        {
            "turn_index": 1,
            "player_action": "continue turn 1",
            "turn_result": {
                "ok": True,
                "autoplay_action_text": "continue turn 1 while following the north road",
                "autoplay_action_context_applied": True,
                "simulation_state": {},
            },
        }
    ]
    summary_path.write_text(json.dumps({"turns_executed": 1, "transcript_rows": rows}), encoding="utf-8")
    transcript_path.write_text(json.dumps(rows), encoding="utf-8")

    result = attach_summary_artifact_status(tmp_path, turns_requested=1)

    assert result["ok"] is True
    assert result["action_context_promoted"] is True
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert summary["transcript_rows"][0]["player_action"] == "continue turn 1 while following the north road"
    assert transcript[0]["player_action"] == "continue turn 1 while following the north road"
    assert summary["transcript_rows"][0]["autoplay_action_context_applied"] is True


def test_attach_summary_artifact_status_leaves_direct_rows_unchanged(tmp_path):
    summary_path = tmp_path / "autoplay-summary.json"
    transcript_path = tmp_path / "autoplay-transcript.json"
    applied_text = "continue turn 1 while following the north road"
    rows = [
        {
            "turn_index": 1,
            "player_action": applied_text,
            "autoplay_action_context_applied": True,
            "turn_result": {
                "ok": True,
                "autoplay_action_text": applied_text,
                "autoplay_action_context_applied": True,
                "simulation_state": {},
            },
        }
    ]
    summary_path.write_text(
        json.dumps({"turns_executed": 1, "transcript_rows": rows}),
        encoding="utf-8",
    )
    transcript_path.write_text(json.dumps(rows), encoding="utf-8")

    result = attach_summary_artifact_status(tmp_path, turns_requested=1)

    assert result["ok"] is True
    assert result["action_context_promoted"] is False
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert transcript == rows
