from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_quality_eval as quality


def _good_transcript() -> dict[str, object]:
    return {
        "format_version": "interactive_cli_campaign_v4",
        "turns": [
            {
                "turn_index": 1,
                "player_input": "I ask Bran about the bandit trail.",
                "raw_narration": "Bran lowers his voice in the Rusty Flagon tavern. He points toward the old mill road and warns that fresh boot prints mark the bandit trail. You can question Elara at the market next or follow the muddy tracks before dusk.",
                "interactive_cli_memory_state": {"facts": {"topic": "bandit trail"}},
            },
            {
                "turn_index": 2,
                "player_input": "I follow the muddy tracks toward the old mill.",
                "raw_narration": "The muddy tracks bend north toward the old mill, exactly as Bran warned. A torn red sash hangs on a fence post, and Captain Aldric's patrol horn sounds far behind you. Do you inspect the sash or press deeper along the trail?",
                "interactive_cli_travel_state": {"location": "old-mill-road"},
            },
            {
                "turn_index": 3,
                "player_input": "I inspect the sash and ready my sword.",
                "raw_narration": "The sash is still damp, and a silver tavern token from Bran's counter is knotted into the cloth. As you ready your sword, a bandit steps from the mill shadow and offers a nervous bargain. Will you challenge him or hear the offer?",
                "interactive_cli_equipment_state": {"equipped": ["sword"]},
                "turn_contract": {"combat": {"threat": "bandit"}},
            },
        ],
    }


def test_phase13_94_quality_eval_scores_specific_grounded_transcript() -> None:
    result = quality.evaluate_live_quality_transcript(_good_transcript())

    assert result["format_version"] == quality.LIVE_QUALITY_EVAL_VERSION
    assert result["ok"] is True
    assert result["turn_count"] == 3
    assert result["scores"]["coherence"] >= 4.0
    assert result["scores"]["agency"] >= 4.0
    assert result["scores"]["specificity"] >= 4.0
    assert result["scores"]["fun"] >= 4.0
    assert result["signals"]["grounded_turn_count"] == 3
    assert result["signals"]["narration_metadata_turn_count"] == 0
    assert result["failures"] == []


def test_phase13_94_quality_eval_flags_boring_generic_transcript() -> None:
    transcript = {
        "turns": [
            {"turn_index": 1, "player_input": "I ask Bran for work.", "raw_narration": "The air is thick. You feel a sense of unease."},
            {"turn_index": 2, "player_input": "I go north.", "raw_narration": "The air is thick. You feel a sense of unease."},
            {"turn_index": 3, "player_input": "I search the road.", "raw_narration": "The air is thick. You feel a sense of unease."},
        ]
    }

    result = quality.evaluate_live_quality_transcript(transcript)

    assert result["ok"] is False
    assert "average_quality_score_below_threshold" in result["failures"]
    assert "generic_turn_ratio_high" in result["warnings"]
    assert "duplicate_response_ratio_high" in result["warnings"]
    assert result["signals"]["duplicate_response_count"] == 2


def test_phase13_94_quality_eval_reports_missing_narration() -> None:
    result = quality.evaluate_live_quality_transcript({"turns": [{"turn_index": 1, "player_input": "hello"}]})

    assert result["ok"] is False
    assert "turn_1_missing_narration" in result["failures"]


def test_phase13_94_quality_eval_accepts_live_llm_narration_metadata() -> None:
    transcript = _good_transcript()
    for turn in transcript["turns"]:  # type: ignore[index]
        turn["llm_called"] = True
        turn["narration_source"] = "deferred_llm_narration"

    result = quality.evaluate_live_quality_transcript(transcript)

    assert result["ok"] is True
    assert result["signals"]["narration_metadata_turn_count"] == 3
    assert result["signals"]["llm_narration_turn_count"] == 3
    assert result["signals"]["llm_narration_ratio"] == 1.0
    assert result["signals"]["visible_repair_turn_count"] == 0
    assert result["signals"]["deterministic_fallback_turn_count"] == 0


def test_phase14_01_quality_eval_fails_when_live_narration_is_repaired_or_fallback() -> None:
    transcript = {
        "turns": [
            {
                "turn_index": 1,
                "player_input": "I ask Bran about the road.",
                "raw_narration": "Bran warns that the old road bends toward the bandit trail. Do you follow the tracks or question Elara first?",
                "llm_called": True,
                "narration_source": "deferred_llm_narration",
            },
            {
                "turn_index": 2,
                "player_input": "I buy two rations.",
                "raw_narration": "Elara counts two rations and names the silver price before you leave the market.",
                "llm_called": False,
                "narration_source": "dialogue_repaired",
            },
            {
                "turn_index": 3,
                "player_input": "I check whether the bandit is still armed.",
                "raw_narration": "The moment responds without producing a major new consequence.",
                "llm_called": False,
                "narration_source": "deterministic_fallback",
            },
        ]
    }

    result = quality.evaluate_live_quality_transcript(transcript)

    assert result["ok"] is False
    assert "llm_narration_ratio_below_threshold" in result["failures"]
    assert "visible_response_repair_ratio_high" in result["failures"]
    assert "deterministic_fallback_ratio_high" in result["failures"]
    assert result["signals"]["narration_metadata_turn_count"] == 3
    assert result["signals"]["llm_narration_turn_count"] == 1
    assert result["signals"]["visible_repair_turn_count"] == 1
    assert result["signals"]["deterministic_fallback_turn_count"] == 1
    assert "turn_2_visible_response_repair" in result["warnings"]
    assert "turn_3_deterministic_fallback" in result["warnings"]


def test_phase13_94_quality_reader_handles_bad_inputs(tmp_path: Path) -> None:
    assert quality.read_live_quality_transcript(tmp_path / "missing.json") == {
        "format_version": quality.LIVE_QUALITY_EVAL_VERSION,
        "ok": False,
        "error": "transcript_missing",
    }

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    assert quality.read_live_quality_transcript(invalid_json)["error"] == "transcript_json_invalid"

    non_object = tmp_path / "list.json"
    non_object.write_text("[]", encoding="utf-8")
    assert quality.read_live_quality_transcript(non_object)["error"] == "transcript_payload_not_object"


def test_phase13_94_quality_cli_writes_summary_and_marker(tmp_path: Path, capsys) -> None:
    transcript_path = tmp_path / "interactive-transcript.json"
    summary_path = tmp_path / "nested" / "live-quality-summary.json"
    transcript_path.write_text(json.dumps(_good_transcript(), sort_keys=True), encoding="utf-8")

    assert quality.main([str(transcript_path), "--summary-path", str(summary_path)]) == 0

    output = capsys.readouterr()
    stdout_payload = json.loads(output.out)
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert stdout_payload["ok"] is True
    assert summary_payload["format_version"] == quality.LIVE_QUALITY_EVAL_VERSION
    assert output.err.strip().startswith("[RPG_LIVE_QUALITY_EVAL] ok=true turn_count=3")


def test_phase13_94_quality_status_marker_reports_failure() -> None:
    marker = quality.render_live_quality_status_marker(
        {
            "ok": False,
            "turn_count": 2,
            "avg_score": 2.5,
            "scores": {"fun": 2.0},
            "failures": ["average_quality_score_below_threshold"],
        }
    )

    assert marker == "[RPG_LIVE_QUALITY_EVAL] ok=false turn_count=2 avg_score=2.500 fun=2.000 error=average_quality_score_below_threshold"
