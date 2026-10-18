"""Phase 10.6 — Functional tests for orchestration layer."""

from app.apps.rpg.narration.orchestration_state import (
    begin_llm_request,
    get_llm_orchestration_state,
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