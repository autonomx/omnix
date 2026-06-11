from __future__ import annotations

from tests.rpg.manual import runtime_narration_contract as contract

FINAL_TEXT = (
    "Bran remembers that your trail name is Ash Lantern and says he will use that name "
    "if he needs to warn you. You can ask about the road, speak with Elara, or leave "
    "for the north trail."
)


def _late_dialogue_repair_turn() -> dict:
    return {
        "turn_index": 3,
        "player_input": "I ask Bran what name he should use if he needs to warn me later.",
        "raw_narration": "Bran the Innkeeper answers carefully.",
        "llm_called": True,
        "narration_source": "dialogue_repaired",
        "narration_status": "completed",
        "raw_result": {
            "ok": True,
            "llm_called": True,
            "final_narration": "Bran the Innkeeper answers carefully.",
            "narration_status": "completed",
            "result": {
                "action_type": "dialogue",
                "visible_interaction_reason": "memory_name_question",
            },
            "npc": {"id": "npc:bran", "name": "Bran", "role": "innkeeper"},
            "session": {
                "runtime_state": {"current_scene": {"id": "loc:rusty_flagon", "name": "Rusty Flagon Tavern"}},
                "simulation_state": {
                    "player_state": {
                        "location_id": "loc:rusty_flagon",
                        "nearby_npc_ids": ["npc:bran"],
                    }
                },
            },
        },
        "deferred_narration_drain": {
            "pending_before": False,
            "requires_provider_narration": False,
            "source": "not_pending",
        },
    }


def _completed_payload(*, turn_summary, **kwargs) -> dict:
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


def test_phase14_07_late_top_level_repair_is_contract_visible(monkeypatch) -> None:
    monkeypatch.setattr(contract, "generate_runtime_deferred_narration_payload", _completed_payload)

    payload = {
        "format_version": "interactive_cli_campaign_v4",
        "summary": {"session_id": "phase14_07_late_repair"},
        "turns": [_late_dialogue_repair_turn()],
    }

    normalized, summary = contract.normalize_runtime_narration_transcript_payload(payload)
    turn = normalized["turns"][0]

    assert summary["late_repair_required_count"] == 1
    assert summary["late_repair_completed_count"] == 1
    assert summary["late_repair_timeout_count"] == 0
    assert summary["normalized_count"] == 1
    assert summary["turns"][0]["before_source"] == "dialogue_repaired"
    assert summary["turns"][0]["after_source"] == "provider_runtime_narration"
    assert turn["narration_source"] == "provider_runtime_narration"
    assert turn["narration_status"] == "completed"
    assert turn["llm_called"] is True
    assert turn["raw_narration"] == FINAL_TEXT
    assert turn["raw_narration_payload"]["source"] == "provider_runtime_narration"
    assert turn["raw_result"]["narration_payload"]["source"] == "provider_runtime_narration"
    assert turn["raw_result"]["result"]["narration_source"] == "provider_runtime_narration"


def test_phase14_07_late_repair_timeout_is_reported(monkeypatch) -> None:
    def failed_payload(*, turn_summary, **kwargs) -> dict:
        return {
            "source": contract.RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE,
            "narration_status": "failed",
            "narration": "",
            "runtime_narration_diagnostics": {
                "provider_error_type": "deferred_narration_provider_error",
                "provider_errors": ["provider failed"],
            },
        }

    monkeypatch.setattr(contract, "generate_runtime_deferred_narration_payload", failed_payload)
    payload = {
        "format_version": "interactive_cli_campaign_v4",
        "summary": {"session_id": "phase14_07_late_repair_timeout"},
        "turns": [_late_dialogue_repair_turn()],
    }

    normalized, summary = contract.normalize_runtime_narration_transcript_payload(payload)
    turn = normalized["turns"][0]

    assert summary["late_repair_required_count"] == 1
    assert summary["late_repair_completed_count"] == 0
    assert summary["late_repair_timeout_count"] == 1
    assert "deferred_narration_provider_error" in summary["error_types"]
    assert turn["narration_source"] == "dialogue_repaired"
    assert turn["deferred_narration_drain"]["timed_out"] is True
