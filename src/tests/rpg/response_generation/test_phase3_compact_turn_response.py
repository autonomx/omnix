from __future__ import annotations

from app.rpg.presentation.turn_response import (
    TURN_RESPONSE_CONTRACT_VERSION,
    TURN_RESPONSE_MAX_BYTES,
    build_turn_response_v2,
    turn_response_size_bytes,
)


def test_compact_turn_response_omits_runtime_graph_and_preserves_dialogue() -> None:
    huge_text = "x" * 200_000
    session = {
        "manifest": {"session_id": "session:bran", "title": "Rusty Flagon", "turn_count": 3},
        "state": {
            "scene": {"location_name": "Rusty Flagon Tavern"},
            "player": {"level": 1, "hp": 20},
            "huge_state": huge_text,
        },
        "runtime_state": {"state_revision": 7, "interaction_seq": 4, "huge_runtime": huge_text},
    }
    result = {
        "ok": True,
        "submission_id": "submit:one",
        "turn_id": "turn:3",
        "tick": 3,
        "stateful": False,
        "semantic_family": "social",
        "action_type": "npc_interpretive_dialogue",
        "manual_turn_stage_timing": {
            "manual_turn_ms": 612.3,
            "pre_runtime_intent_llm_ms": 488.1,
            "private_internal_metric": 999,
        },
        "final_narration": "Bran rests the polishing rag on the counter.",
        "npc": {
            "id": "npc:bran",
            "speaker": "Bran",
            "line": "Steady enough, though the road traffic has thinned this week.",
        },
        "session": session,
        "simulation_state": {"raw": huge_text},
        "runtime_state": {"raw": huge_text},
        "first_call_grounding_diagnostics": {"prompt": huge_text},
        "foreground_job": {
            "id": "job:foreground",
            "output_refs": [{"raw_turn_result": {"raw": huge_text}}],
        },
        "creation_server_trace": {
            "job_id": "job:foreground",
            "server_job_created_at": "2026-07-12T00:00:00Z",
            "private_blob": huge_text,
        },
    }

    payload = build_turn_response_v2(
        result,
        session_id="session:bran",
        command="I ask Bran how business is doing.",
        session=session,
        trace_id="turn-trace",
    )

    assert payload["contract_version"] == TURN_RESPONSE_CONTRACT_VERSION
    assert payload["response"] == (
        "Bran rests the polishing rag on the counter.\n\n"
        'Bran: "Steady enough, though the road traffic has thinned this week."'
    )
    assert payload["visible_response"]["messages"][0]["speaker"] == "Bran"
    assert payload["state"] == {
        "revision": 7,
        "changed": True,
        "changed_domains": ["conversation"],
    }
    assert payload["session_summary"]["location"] == "Rusty Flagon Tavern"
    assert payload["timing"] == {
        "manual_turn_ms": 612.3,
        "pre_runtime_intent_llm_ms": 488.1,
    }
    assert "session" not in payload
    assert "game" not in payload
    assert "simulation_state" not in payload
    assert "runtime_state" not in payload
    assert "foreground_job" not in payload
    assert "private_blob" not in payload["creation_server_trace"]
    assert turn_response_size_bytes(payload) < TURN_RESPONSE_MAX_BYTES


def test_compact_turn_response_maps_stateful_domains_without_full_state() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "turn_id": "turn:8",
            "tick": 8,
            "stateful": True,
            "semantic_family": "trade",
            "action_type": "trade",
            "narration": "You pay for two rations.",
        },
        session_id="session:bran",
        command="I buy two rations.",
    )

    assert payload["state"]["changed_domains"] == [
        "conversation",
        "currency",
        "inventory",
        "merchant",
    ]
    assert payload["content"] == "You pay for two rations."
    assert turn_response_size_bytes(payload) < TURN_RESPONSE_MAX_BYTES


def test_compact_turn_response_uses_explicit_changed_domains() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "changed_domains": ["combat", "player", "journal"],
            "narration": "The exchange ends.",
        },
        session_id="session:test",
        command="I lower my sword.",
    )

    assert payload["state"]["changed_domains"] == ["combat", "player", "journal"]
