from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_playtest as playtest


FINAL_TEXT = (
    "Elara wraps two rations and names the silver price. "
    "You can pay now, haggle once, or ask which landmark marks the safer trail."
)


def _turn_with_stale_source(source: str = "survival_repaired") -> dict:
    payload = {
        "format_version": "rpg_narration_v2",
        "source": "provider_runtime_narration",
        "narration_status": "completed",
        "narration": FINAL_TEXT,
        "runtime_narration_diagnostics": {
            "provider_attempted": True,
            "provider_present": True,
            "provider_valid": True,
            "provider_errors": [],
        },
    }
    return {
        "turn_index": 2,
        "player_input": "I buy two rations and ask the exact price.",
        "raw_narration": "Short repaired placeholder.",
        "llm_called": True,
        "narration_source": source,
        "narration_status": "completed",
        "raw_result": {
            "ok": True,
            "llm_called": True,
            "narration_source": "provider_runtime_narration",
            "narration_status": "completed",
            "narration": FINAL_TEXT,
            "narration_payload": payload,
            "result": {
                "action_type": "buy",
                "visible_interaction_reason": "commerce_purchase",
                "narration_source": "provider_runtime_narration",
                "narration_status": "completed",
                "narration_payload": payload,
            },
        },
        "deferred_narration_drain": {
            "pending_before": True,
            "completed": True,
            "timed_out": False,
            "source": "provider_runtime_narration",
        },
        "interactive_cli_state_bundle": {"states": {}},
    }


def test_phase14_04_normalizes_stale_repair_source_in_transcript_payload() -> None:
    transcript = {
        "format_version": "interactive_cli_campaign_v4",
        "turns": [_turn_with_stale_source("survival_repaired"), _turn_with_stale_source("quest_repaired")],
    }

    normalized, summary = playtest.normalize_deferred_live_narration_transcript_payload(transcript)

    assert summary["format_version"] == playtest.LIVE_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION
    assert summary["turn_count"] == 2
    assert summary["normalized_count"] == 2
    for turn in normalized["turns"]:
        assert turn["narration_source"] == "provider_runtime_narration"
        assert turn["narration_status"] == "completed"
        assert turn["llm_called"] is True
        assert turn["raw_narration"] == FINAL_TEXT
        assert turn["raw_narration_payload"]["source"] == "provider_runtime_narration"
        assert turn["raw_result"]["narration_source"] == "provider_runtime_narration"
        assert turn["raw_result"]["result"]["narration_source"] == "provider_runtime_narration"
    assert normalized["live_transcript_provenance_normalization"]["normalized_count"] == 2


def test_phase14_04_normalizes_transcript_file_before_quality_scoring(tmp_path: Path) -> None:
    transcript_path = tmp_path / "interactive-transcript.json"
    transcript_path.write_text(
        json.dumps({"format_version": "interactive_cli_campaign_v4", "turns": [_turn_with_stale_source("survival_repaired")]}),
        encoding="utf-8",
    )

    summary = playtest.normalize_deferred_live_narration_transcript_file(transcript_path)
    rewritten = json.loads(transcript_path.read_text(encoding="utf-8"))

    assert summary["normalized_count"] == 1
    assert rewritten["turns"][0]["narration_source"] == "provider_runtime_narration"
    assert rewritten["turns"][0]["raw_narration"] == FINAL_TEXT


def test_phase14_04_live_runner_rewrites_stale_transcript_before_quality_eval(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        transcript_path.write_text(
            json.dumps({"format_version": "interactive_cli_campaign_v4", "turns": [_turn_with_stale_source("survival_repaired")]}),
            encoding="utf-8",
        )
        return {
            "summary": {"completed_turns": 1},
            "turns": [],
            "artifacts": {"transcript_path": str(transcript_path)},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        output_dir=tmp_path / "out",
        commands=["I buy two rations and ask the exact price."],
        campaign_runner=fake_runner,
    )

    transcript = json.loads(Path(result["transcript_path"]).read_text(encoding="utf-8"))
    turn = transcript["turns"][0]
    assert result["transcript_provenance_normalization"]["normalized_count"] == 1
    assert result["quality"]["signals"]["llm_narration_ratio"] == 1.0
    assert turn["narration_source"] == "provider_runtime_narration"
    assert turn["raw_result"]["narration_payload"]["source"] == "provider_runtime_narration"
    assert captured["defer_runtime_narration"] is True
    assert callable(captured["after_turn_hook"])
