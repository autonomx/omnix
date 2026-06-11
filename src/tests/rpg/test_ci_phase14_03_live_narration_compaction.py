from __future__ import annotations

from tests.rpg import interactive_cli_live_llm_playtest as playtest


def _pending_turn_with_large_context() -> dict:
    huge_text = "ancient road clue " * 5000
    return {
        "turn_index": 3,
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
            "result": {
                "action_type": "observe",
                "visible_interaction_reason": "road_danger_inquiry",
                "forbidden_narration": ["do not invent victory", "do not invent reward"],
            },
            "turn_contract": {
                "player_input": "I ask Bran what danger remains nearby.",
                "oversized_debug_blob": huge_text,
            },
            "narration_context": {
                "recent_authoritative_facts": [huge_text, "Bran warned about bandit tracks near the old road."],
            },
            "npc": {"id": "npc:bran", "name": "Bran", "role": "innkeeper", "biography": huge_text},
            "session": {
                "runtime_state": {
                    "current_scene": {
                        "id": "loc:rusty_flagon",
                        "name": "Rusty Flagon Tavern",
                        "description": huge_text,
                    }
                },
                "simulation_state": {
                    "player_state": {
                        "location_id": "loc:rusty_flagon",
                        "nearby_npc_ids": ["npc:bran"],
                        "inventory_state": {"items": ["ration"], "currency": {"silver": 10}},
                    }
                },
            },
        },
        "interactive_cli_state_bundle": {"states": {"debug": huge_text}},
    }


def test_phase14_03_live_deferred_narration_context_is_compact() -> None:
    context = playtest._grounded_live_narration_context(_pending_turn_with_large_context())
    encoded = playtest.json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)

    assert context["format_version"] == playtest.LIVE_DEFERRED_NARRATION_CONTEXT_VERSION
    assert context["player_input"] == "I ask Bran what danger remains nearby."
    assert context["action_type"] == "observe"
    assert "interactive_cli_state_bundle" not in encoded
    assert "ancient road clue " * 100 not in encoded
    assert len(encoded) < playtest.LIVE_DEFERRED_NARRATION_MAX_CONTEXT_CHARS


def test_phase14_03_context_overflow_errors_are_classified() -> None:
    message = "HTTP error 400: n_keep: 47095 >= n_ctx: 37376; context length exceeded"

    assert playtest._classify_live_deferred_narration_error(message) == "deferred_narration_context_overflow"


def test_phase14_03_drain_result_reports_context_overflow_type() -> None:
    turn = _pending_turn_with_large_context()

    def fake_drain_func(**kwargs):
        return {
            "source": playtest.LIVE_DEFERRED_NARRATION_DRAIN_SOURCE,
            "narration_status": "failed",
            "narration": "",
            "runtime_narration_diagnostics": {
                "provider_attempted": True,
                "provider_present": True,
                "provider_valid": False,
                "provider_error_type": "deferred_narration_context_overflow",
                "provider_errors": ["HTTP error 400: n_keep: 47095 >= n_ctx: 37376"],
            },
        }

    result = playtest.drain_deferred_live_narration_turn(
        turn_summary=turn,
        session_id="session-context-overflow",
        turn_index=3,
        player_input=turn["player_input"],
        drain_func=fake_drain_func,
    )

    assert result["pending_before"] is True
    assert result["completed"] is False
    assert result["timed_out"] is True
    assert result["error_type"] == "deferred_narration_context_overflow"
    assert turn["deferred_narration_drain"]["error_type"] == "deferred_narration_context_overflow"


def test_phase14_03_completed_drain_normalizes_top_level_and_nested_sources() -> None:
    turn = _pending_turn_with_large_context()
    narration = "Bran keeps his warning grounded: the old north road still shows bandit tracks. You can question Elara, ask the guard, or follow the trail."

    result = playtest.drain_deferred_live_narration_turn(
        turn_summary=turn,
        session_id="session-completed-drain",
        turn_index=3,
        player_input=turn["player_input"],
        drain_func=lambda **_: {
            "format_version": "rpg_narration_v2",
            "source": "provider_runtime_narration",
            "narration_status": "completed",
            "narration": narration,
            "runtime_narration_diagnostics": {
                "provider_attempted": True,
                "provider_present": True,
                "provider_valid": True,
                "provider_errors": [],
            },
        },
    )

    assert result["completed"] is True
    assert turn["llm_called"] is True
    assert turn["narration_source"] == "provider_runtime_narration"
    assert turn["narration_status"] == "completed"
    assert turn["raw_narration"] == narration
    assert turn["raw_narration_payload"]["source"] == "provider_runtime_narration"
    assert turn["raw_result"]["narration_source"] == "provider_runtime_narration"
    assert turn["raw_result"]["narration_payload"]["narration_status"] == "completed"
    assert turn["raw_result"]["result"]["narration_source"] == "provider_runtime_narration"
