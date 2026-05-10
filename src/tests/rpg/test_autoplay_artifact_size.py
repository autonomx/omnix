from types import SimpleNamespace

from tests.rpg.autoplay_llm_campaign import (
    _effective_transcript_detail,
    _prepare_transcript_artifacts,
    _slim_transcript_row,
)


def test_slim_transcript_row_removes_heavy_payloads():
    row = {
        "turn": 1,
        "player_action": "I ask Bran about the tavern.",
        "scenario_progression_summary": {"changed": True, "matched_node_ids": ["ask_bran_about_tension"]},
        "runtime_state": {"huge": "x" * 1_000_000},
        "raw_result": {"huge": "y" * 1_000_000},
        "player_context": {"huge": "z" * 1_000_000},
    }

    slim = _slim_transcript_row(row, max_row_bytes=50_000)

    assert slim["turn"] == 1
    assert slim["player_action"]
    assert "runtime_state" not in slim
    assert "raw_result" not in slim
    assert "player_context" not in slim
    assert slim["_artifact_slimmed"] is True


def test_prepare_transcript_artifacts_uses_slim_for_100_turn_profile():
    transcript = [
        {
            "turn": i,
            "player_action": "action",
            "runtime_state": {"huge": "x" * 1_000_000},
        }
        for i in range(100)
    ]
    args = SimpleNamespace(
        turns=100,
        autoplay_profile="smoke_100",
        transcript_detail="auto",
        max_transcript_row_bytes=50_000,
        max_transcript_artifact_mb=10,
        debug_transcript_tail_rows=3,
    )

    artifacts = _prepare_transcript_artifacts(transcript, args)

    assert artifacts["summary"]["used_slim_transcript"] is True
    assert artifacts["summary"]["row_count"] == 100
    assert len(artifacts["debug_tail"]) == 3
    assert artifacts["summary"]["slim_mb"] < artifacts["summary"]["full_mb"]


def test_auto_transcript_detail_uses_slim_for_30_turn_debug_runs():
    args = SimpleNamespace(turns=30, autoplay_profile="custom", transcript_detail="auto")

    assert _effective_transcript_detail(args) == "slim"