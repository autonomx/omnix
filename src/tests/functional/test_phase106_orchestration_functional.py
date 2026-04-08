"""Phase 10.6 — Functional tests for orchestration layer."""
import pytest

from app.rpg.orchestration.controller import execute_llm_request_for_turn
from app.rpg.orchestration.provider_interface import set_llm_provider_mode
from app.rpg.orchestration.state import (
    append_llm_stream_event,
    begin_llm_request,
    fail_llm_request,
    finalize_llm_request,
    get_llm_orchestration_state,
)
from app.rpg.orchestration.stream_adapter import apply_provider_result_to_runtime_turn
from app.rpg.runtime.dialogue_runtime import (
    begin_runtime_turn,
    get_runtime_dialogue_state,
)


def test_phase106_begin_llm_request_creates_pending_active_request():
    state = {}
    state = begin_llm_request(
        state,
        tick=15,
        sequence_index=2,
        actor_id="comp:lyra",
        turn_id="turn:15:2:comp:lyra",
        sequence_id="seq:15:0",
        speaker_id="comp:lyra",
        mode="dialogue",
        provider="openai",
        model="gpt-test",
        input_payload={"prompt": "test"},
    )

    llm = get_llm_orchestration_state(state)
    assert llm["request_counter"] == 1
    assert len(llm["active_requests"]) == 1
    request = llm["active_requests"][0]
    assert request["request_id"] == "llmreq:15:2:comp:lyra:0"
    assert request["status"] == "pending"
    assert request["provider"] == "openai"
    assert request["model"] == "gpt-test"
    assert request["input_payload"] == {"prompt": "test"}


def test_phase106_execute_llm_request_for_turn_disabled_mode_finalizes_without_text_by_default():
    from app.rpg.runtime.dialogue_runtime import begin_runtime_turn

    state = {}
    state = set_llm_provider_mode(state, "disabled")
    state = begin_runtime_turn(
        state,
        tick=10,
        sequence_index=1,
        actor_id="comp:lyra",
        speaker_id="comp:lyra",
        speaker_name="Lyra",
        role="companion",
        sequence_id="seq:10:0",
    )

    state = execute_llm_request_for_turn(
        state,
        turn_id="turn:10:1:comp:lyra",
        mode="dialogue",
        extra_constraints={"allow_emotional_fallback": False},
    )

    runtime = get_runtime_dialogue_state(state)
    turn = runtime["turns"][0]
    assert turn["status"] == "complete"
    assert turn["text"] == ""

    llm = get_llm_orchestration_state(state)
    assert llm["active_requests"] == []
    assert len(llm["completed_requests"]) == 1
    assert llm["completed_requests"][0]["status"] == "failed"


def test_phase106_execute_llm_request_for_turn_disabled_mode_can_use_fallback():
    state = {}
    state = set_llm_provider_mode(state, "disabled")
    state = begin_runtime_turn(
        state,
        tick=11,
        sequence_index=1,
        actor_id="comp:lyra",
        speaker_id="comp:lyra",
        speaker_name="Lyra",
        role="companion",
        sequence_id="seq:11:0",
    )

    state = execute_llm_request_for_turn(
        state,
        turn_id="turn:11:1:comp:lyra",
        mode="dialogue",
        extra_constraints={"allow_emotional_fallback": True},
    )

    runtime = get_runtime_dialogue_state(state)
    turn = runtime["turns"][0]
    assert turn["status"] == "complete"


def test_phase106_execute_llm_request_for_turn_replay_mode_writes_stream_and_output():
    state = {}
    state = set_llm_provider_mode(state, "replay")
    state = begin_runtime_turn(
        state,
        tick=20,
        sequence_index=0,
        actor_id="npc:guard",
        speaker_id="npc:guard",
        speaker_name="Guard",
        role="npc",
        sequence_id="seq:20:0",
    )

    # Seed replay artifact
    state["orchestration_state"] = {
        "llm": {
            "provider_mode": "replay",
            "request_counter": 0,
            "active_requests": [],
            "completed_requests": [
                {
                    "request_id": "llmreq:20:0:npc:guard:0",
                    "tick": 20,
                    "sequence_id": "seq:20:0",
                    "turn_id": "turn:20:0:npc:guard",
                    "actor_id": "npc:guard",
                    "speaker_id": "npc:guard",
                    "mode": "dialogue",
                    "status": "complete",
                    "provider": "openai",
                    "model": "gpt-test",
                    "input_payload": {},
                    "stream_events": [
                        {"event_index": 0, "event_type": "text_chunk", "text": "Hold ", "final": False, "raw": {}},
                        {"event_index": 1, "event_type": "text_chunk", "text": "there.", "final": True, "raw": {}},
                    ],
                    "output_text": "Hold there.",
                    "error": "",
                }
            ],
            "last_error": {},
        }
    }

    state = execute_llm_request_for_turn(
        state,
        turn_id="turn:20:0:npc:guard",
        mode="dialogue",
    )

    runtime = get_runtime_dialogue_state(state)
    turn = runtime["turns"][0]
    assert turn["status"] == "complete"
    assert turn["text"] == "Hold there."
    assert len(turn["chunks"]) == 2

    llm = get_llm_orchestration_state(state)
    assert llm["active_requests"] == []
    assert llm["completed_requests"][-1]["status"] == "replayed"


def test_phase106_apply_provider_result_to_runtime_turn_streams_and_finalizes():
    state = {}
    state = begin_runtime_turn(
        state,
        tick=30,
        sequence_index=2,
        actor_id="npc:guard",
        speaker_id="npc:guard",
        speaker_name="Guard",
        role="npc",
        sequence_id="seq:30:0",
    )

    state = apply_provider_result_to_runtime_turn(
        state,
        turn_id="turn:30:2:npc:guard",
        actor_id="npc:guard",
        speaker_id="npc:guard",
        provider_result={
            "stream_events": [
                {"event_index": 0, "event_type": "text_chunk", "text": "Hold ", "final": False},
                {"event_index": 1, "event_type": "text_chunk", "text": "there.", "final": True},
            ],
            "output_text": "Hold there.",
        },
        allow_emotional_fallback=False,
    )

    runtime = get_runtime_dialogue_state(state)
    turn = runtime["turns"][0]
    assert turn["status"] == "complete"
    assert turn["text"] == "Hold there."
    assert len(turn["chunks"]) == 2


def test_phase106_request_counter_increments_deterministically():
    state = {}
    state = begin_llm_request(
        state,
        tick=5,
        sequence_index=0,
        actor_id="comp:lyra",
        turn_id="turn:5:0:comp:lyra",
    )
    state = begin_llm_request(
        state,
        tick=5,
        sequence_index=1,
        actor_id="npc:guard",
        turn_id="turn:5:1:npc:guard",
    )

    llm = get_llm_orchestration_state(state)
    assert llm["request_counter"] == 2
    assert [v["request_id"] for v in llm["active_requests"]] == [
        "llmreq:5:0:comp:lyra:0",
        "llmreq:5:1:npc:guard:1",
    ]