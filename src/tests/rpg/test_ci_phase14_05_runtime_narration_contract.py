from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_campaign as campaign
from tests.rpg import interactive_cli_live_llm_playtest as live_playtest


FINAL_TEXT = "Bran keeps the answer grounded: the old road still shows bandit tracks. You can ask the guard, question Elara, or follow the trail."


def _pending_turn() -> dict:
    return {
        "turn_index": 1,
        "player_input": "I ask Bran what danger remains nearby.",
        "raw_narration": "The moment responds without producing a major new consequence.",
        "llm_called": False,
        "narration_source": "deferred_runtime_narration_pending",
        "raw_narration_payload": {
            "source": "deferred_runtime_narration_pending",
            "narration_status": "pending",
            "narration": "The moment responds without producing a major new consequence.",
        },
        "raw_result": {
            "ok": True,
            "llm_called": False,
            "narration_status": "queued",
            "narration": "The moment responds without producing a major new consequence.",
            "narration_payload": {
                "source": "deferred_runtime_narration_pending",
                "narration_status": "pending",
                "narration": "The moment responds without producing a major new consequence.",
            },
            "result": {
                "action_type": "observe",
                "visible_interaction_reason": "road_danger_inquiry",
            },
            "session": {"runtime_state": {}, "simulation_state": {"player_state": {}}},
        },
    }


def _completed_payload() -> dict:
    return {
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


def test_phase14_05_interactive_campaign_owns_deferred_narration_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(campaign, "_reset_manual_session_artifacts", lambda session_id: None)
    monkeypatch.setattr(campaign, "_ensure_manual_session", lambda session_id: None)
    monkeypatch.setattr(campaign, "extract_service_offer_context", lambda result: {})
    monkeypatch.setattr(campaign, "apply_commerce_followup_repair", lambda turn_summary, **kwargs: turn_summary)
    monkeypatch.setattr(campaign, "apply_quest_followup_repair", lambda turn_summary, **kwargs: turn_summary)
    monkeypatch.setattr(campaign, "apply_survival_visible_response_repair", lambda turn_summary, **kwargs: turn_summary)
    monkeypatch.setattr(
        campaign,
        "classify_service_intent_with_fallback",
        lambda **kwargs: {"provider_requested": False, "provider_called": False},
    )
    monkeypatch.setattr(campaign, "_run_manual_turn_with_trace", lambda **kwargs: (_pending_turn(), {"row_count": 0}))

    result = campaign.run_interactive_campaign(
        turns=1,
        session_id="phase14_05_runtime_contract",
        output_dir=tmp_path / "out",
        scripted_commands=["I ask Bran what danger remains nearby."],
        reset_session=True,
        console_llm=False,
        include_raw_result=True,
        defer_runtime_narration=True,
        enforce_deferred_narration_contract=True,
        deferred_narration_drain_func=lambda **kwargs: _completed_payload(),
        enable_llm_intent_fallback=False,
    )

    transcript = json.loads(Path(result["artifacts"]["transcript_path"]).read_text(encoding="utf-8"))
    turn = transcript["turns"][0]
    contract = result["summary"]["runtime_narration_contract"]
    assert contract["enabled"] is True
    assert contract["deferred_narration_drain"]["pending_count"] == 1
    assert contract["deferred_narration_drain"]["completed_count"] == 1
    assert turn["narration_source"] == "provider_runtime_narration"
    assert turn["narration_status"] == "completed"
    assert turn["llm_called"] is True
    assert turn["raw_narration"] == FINAL_TEXT
    assert turn["raw_result"]["narration_payload"]["source"] == "provider_runtime_narration"
    assert transcript["runtime_transcript_provenance_normalization"]["already_normalized_count"] == 1


def test_phase14_05_live_runner_delegates_contract_to_campaign_runner(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_campaign_runner(**kwargs):
        captured.update(kwargs)
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        turn = _pending_turn()
        turn["raw_narration"] = FINAL_TEXT
        turn["llm_called"] = True
        turn["narration_source"] = "provider_runtime_narration"
        turn["narration_status"] = "completed"
        turn["raw_narration_payload"] = _completed_payload()
        turn["raw_result"]["narration_payload"] = _completed_payload()
        transcript_path.write_text(json.dumps({"format_version": "interactive_cli_campaign_v4", "turns": [turn]}), encoding="utf-8")
        return {
            "summary": {
                "completed_turns": 1,
                "runtime_narration_contract": {
                    "enabled": True,
                    "deferred_narration_drain": {
                        "pending_count": 1,
                        "completed_count": 1,
                        "timeout_count": 0,
                        "error_types": [],
                    },
                    "transcript_provenance_normalization": {"normalized_count": 0},
                },
            },
            "turns": [turn],
            "artifacts": {"transcript_path": str(transcript_path)},
        }

    result = live_playtest.run_live_llm_playtest(
        allow_live=True,
        output_dir=tmp_path / "live",
        commands=["I ask Bran what danger remains nearby."],
        campaign_runner=fake_campaign_runner,
    )

    assert result["ok"] is True
    assert captured["defer_runtime_narration"] is True
    assert captured["enforce_deferred_narration_contract"] is True
    assert callable(captured.get("deferred_narration_drain_func")) is False
    assert "after_turn_hook" not in captured
    assert result["runtime_narration_contract"]["deferred_narration_drain"]["completed_count"] == 1
