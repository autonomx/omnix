"""Phase 10.6 — Regression tests for orchestration layer."""
import copy
import pytest

from app.rpg.orchestration.state import (
    begin_llm_request,
    finalize_llm_request,
    get_llm_orchestration_state,
)
from app.rpg.orchestration.fallback import should_allow_llm_fallback
from app.rpg.orchestration.replay import require_replayable_llm_request
from app.rpg.orchestration.request_builder import build_llm_request_payload
from app.rpg.presentation.orchestration_bridge import build_orchestration_presentation_payload


def test_phase106_replay_mode_never_allows_silent_fallback():
    payload = {
        "constraints": {
            "allow_emotional_fallback": True,
        }
    }
    assert should_allow_llm_fallback(payload, provider_mode="replay") is False


def test_phase106_replay_mode_missing_artifact_fails_hard():
    with pytest.raises(ValueError):
        require_replayable_llm_request(
            {},
            turn_id="turn:404:0:npc:guard",
        )


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


def test_phase106_request_builder_same_input_produces_same_payload():
    state = {
        "runtime_state": {
            "dialogue": {
                "active_sequence_id": "seq:1:0",
                "turn_cursor": 0,
                "turns": [
                    {
                        "turn_id": "turn:1:0:comp:lyra",
                        "sequence_id": "seq:1:0",
                        "tick": 1,
                        "sequence_index": 0,
                        "actor_id": "comp:lyra",
                        "speaker_id": "comp:lyra",
                        "speaker_name": "Lyra",
                        "role": "companion",
                        "text": "",
                        "status": "pending",
                        "emotion": "supportive",
                        "style_tags": ["emotion:supportive"],
                        "interruption": False,
                        "interrupt_target_id": "",
                        "chunks": [],
                    }
                ],
            }
        }
    }

    payload_a = build_llm_request_payload(state, turn_id="turn:1:0:comp:lyra")
    payload_b = build_llm_request_payload(state, turn_id="turn:1:0:comp:lyra")

    assert payload_a == payload_b


def test_phase106_orchestration_bridge_does_not_mutate_input_state():
    state = {
        "orchestration_state": {
            "llm": {
                "provider_mode": "replay",
                "request_counter": 2,
                "active_requests": [],
                "completed_requests": [
                    {
                        "request_id": "llmreq:1:0:comp:lyra:0",
                        "tick": 1,
                        "sequence_id": "seq:1:0",
                        "turn_id": "turn:1:0:comp:lyra",
                        "actor_id": "comp:lyra",
                        "speaker_id": "comp:lyra",
                        "mode": "dialogue",
                        "status": "replayed",
                        "provider": "openai",
                        "model": "gpt-test",
                        "input_payload": {"prompt": "x"},
                        "stream_events": [],
                        "output_text": "Hello.",
                        "error": "",
                    }
                ],
                "last_error": {},
            }
        }
    }

    before = copy.deepcopy(state)
    payload = build_orchestration_presentation_payload(state)

    assert state == before
    assert payload["llm_orchestration"]["provider_mode"] == "replay"
    assert payload["llm_orchestration"]["completed_requests"][0]["is_replayed"] is True