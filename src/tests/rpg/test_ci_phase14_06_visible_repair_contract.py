from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_campaign as campaign
from tests.rpg.manual import runtime_narration_contract as contract


FINAL_TEXT = "Bran remembers the name Ash Lantern and says he will use it if he needs to warn you. You can ask about the road, speak with Elara, or leave for the north trail."


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


def _dialogue_repaired_turn() -> dict:
    return {
        "turn_index": 1,
        "player_input": "I ask Bran what name he should use if he needs to warn me later.",
        "raw_narration": "Bran the Innkeeper answers carefully.",
        "llm_called": True,
        "narration_source": "dialogue_repaired",
        "narration_status": "completed",
        "raw_result": {
            "ok": True,
            "llm_called": True,
            "narration": "Bran the Innkeeper answers carefully.",
            "narration_source": "dialogue_repaired",
            "narration_status": "completed",
            "result": {
                "action_type": "dialogue",
                "visible_interaction_reason": "memory_name_question",
                "narration_source": "dialogue_repaired",
            },
            "npc": {"id": "npc:bran", "name": "Bran", "role": "innkeeper"},
            "session": {
                "runtime_state": {"current_scene": {"id": "loc:rusty_flagon", "name": "Rusty Flagon Tavern"}},
                "simulation_state": {"player_state": {"location_id": "loc:rusty_flagon", "nearby_npc_ids": ["npc:bran"]}},
            },
        },
    }


def test_phase14_06_visible_repair_sources_require_runtime_provider_narration() -> None:
    turn = _dialogue_repaired_turn()

    result = contract.drain_deferred_runtime_narration_turn(
        turn_summary=turn,
        session_id="phase14_06_visible_repair",
        turn_index=1,
        player_input=turn["player_input"],
        drain_func=lambda **kwargs: _completed_payload(),
    )

    assert result["pending_before"] is True
    assert result["requires_provider_narration"] is True
    assert result["before_source"] == "dialogue_repaired"
    assert result["completed"] is True
    assert result["source"] == "provider_runtime_narration"
    assert turn["narration_source"] == "provider_runtime_narration"
    assert turn["narration_status"] == "completed"
    assert turn["raw_narration"] == FINAL_TEXT
    assert turn["raw_result"]["narration_source"] == "provider_runtime_narration"
    assert turn["raw_result"]["result"]["narration_source"] == "provider_runtime_narration"


def test_phase14_06_runtime_campaign_routes_dialogue_repair_through_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(campaign, "_reset_manual_session_artifacts", lambda session_id: None)
    monkeypatch.setattr(campaign, "_ensure_manual_session", lambda session_id: None)
    monkeypatch.setattr(campaign, "extract_service_offer_context", lambda result: {})
    monkeypatch.setattr(campaign, "apply_commerce_followup_repair", lambda turn_summary, **kwargs: turn_summary)
    monkeypatch.setattr(campaign, "apply_survival_visible_response_repair", lambda turn_summary, **kwargs: turn_summary)
    monkeypatch.setattr(
        campaign,
        "classify_service_intent_with_fallback",
        lambda **kwargs: {"provider_requested": False, "provider_called": False},
    )
    monkeypatch.setattr(campaign, "_run_manual_turn_with_trace", lambda **kwargs: (_dialogue_repaired_turn(), {"row_count": 0}))
    monkeypatch.setattr(campaign, "apply_quest_followup_repair", lambda turn_summary, **kwargs: turn_summary)

    result = campaign.run_interactive_campaign(
        turns=1,
        session_id="phase14_06_campaign_visible_repair",
        output_dir=tmp_path / "out",
        scripted_commands=["I ask Bran what name he should use if he needs to warn me later."],
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
    drain = result["summary"]["runtime_narration_contract"]["deferred_narration_drain"]
    assert drain["pending_count"] == 1
    assert drain["completed_count"] == 1
    assert drain["visible_repair_required_count"] == 1
    assert turn["narration_source"] == "provider_runtime_narration"
    assert turn["raw_narration"] == FINAL_TEXT
    assert turn["raw_result"]["narration_payload"]["source"] == "provider_runtime_narration"
