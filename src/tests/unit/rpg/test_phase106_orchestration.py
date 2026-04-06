"""Phase 10.6 — Unit tests for orchestration layer."""
import pytest

from app.rpg.orchestration.state import (
    ensure_llm_orchestration_state,
    get_llm_orchestration_state,
    build_llm_request_id,
    begin_llm_request,
    append_llm_stream_event,
    finalize_llm_request,
    fail_llm_request,
    _dedupe_and_sort_stream_events,
    _normalize_request,
)
from app.rpg.orchestration.request_builder import build_llm_request_payload
from app.rpg.orchestration.provider_interface import (
    get_llm_provider_mode,
    set_llm_provider_mode,
    build_disabled_provider_result,
    build_replay_provider_result,
)
from app.rpg.orchestration.replay import (
    find_replayable_llm_request,
    require_replayable_llm_request,
)
from app.rpg.orchestration.fallback import (
    should_allow_llm_fallback,
    build_llm_fallback_result,
)
from app.rpg.orchestration.controller import _request_id_counter


# --- Tests ---

def test_phase106_llm_orchestration_state_is_created_and_normalized():
    state = ensure_llm_orchestration_state({})
    llm = get_llm_orchestration_state(state)

    assert "orchestration_state" in state
    assert "llm" in state["orchestration_state"]
    assert llm["active_requests"] == []
    assert llm["completed_requests"] == []
    assert llm["request_counter"] == 0
    assert llm["provider_mode"] == "disabled"
    assert llm["last_error"] == {}


def test_phase106_llm_request_ids_are_deterministic():
    assert build_llm_request_id(12, 3, "comp:lyra", 0) == "llmreq:12:3:comp:lyra:0"


def test_phase106_llm_state_is_bounded():
    active_requests = []
    completed_requests = []
    for i in range(10):
        active_requests.append({
            "request_id": f"llmreq:1:{i}:npc:{i}:0",
            "tick": 1,
            "sequence_id": "seq:1:0",
            "turn_id": f"turn:1:{i}:npc:{i}",
            "actor_id": f"npc:{i}",
            "speaker_id": f"npc:{i}",
            "mode": "dialogue",
            "status": "pending",
            "provider": "test",
            "model": "test-model",
            "input_payload": {},
            "stream_events": [],
            "output_text": "",
            "error": "",
        })
    for i in range(30):
        completed_requests.append({
            "request_id": f"llmreq:2:{i}:npc:{i}:0",
            "tick": 2,
            "sequence_id": "seq:2:0",
            "turn_id": f"turn:2:{i}:npc:{i}",
            "actor_id": f"npc:{i}",
            "speaker_id": f"npc:{i}",
            "mode": "dialogue",
            "status": "complete",
            "provider": "test",
            "model": "test-model",
            "input_payload": {},
            "stream_events": [],
            "output_text": "ok",
            "error": "",
        })

    state = ensure_llm_orchestration_state({
        "orchestration_state": {
            "llm": {
                "active_requests": active_requests,
                "completed_requests": completed_requests,
                "request_counter": 99,
                "provider_mode": "capture",
            }
        }
    })
    llm = get_llm_orchestration_state(state)
    assert len(llm["active_requests"]) == 4
    assert len(llm["completed_requests"]) == 20
    assert llm["provider_mode"] == "capture"
    assert llm["request_counter"] == 99


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


def test_phase106_append_llm_stream_event_updates_active_request():
    state = {}
    state = begin_llm_request(
        state,
        tick=20,
        sequence_index=1,
        actor_id="npc:guard",
        turn_id="turn:20:1:npc:guard",
    )
    state = append_llm_stream_event(
        state,
        request_id="llmreq:20:1:npc:guard:0",
        event_index=0,
        event_type="text_chunk",
        text="Hold ",
        final=False,
    )
    state = append_llm_stream_event(
        state,
        request_id="llmreq:20:1:npc:guard:0",
        event_index=1,
        event_type="text_chunk",
        text="there.",
        final=False,
    )

    llm = get_llm_orchestration_state(state)
    request = llm["active_requests"][0]
    assert request["status"] == "streaming"
    assert len(request["stream_events"]) == 2
    assert request["stream_events"][0]["text"] == "Hold "
    assert request["stream_events"][1]["text"] == "there."


def test_phase106_append_llm_stream_event_dedupes_by_event_index_and_type():
    state = {}
    state = begin_llm_request(
        state,
        tick=22,
        sequence_index=0,
        actor_id="npc:guard",
        turn_id="turn:22:0:npc:guard",
    )
    state = append_llm_stream_event(
        state,
        request_id="llmreq:22:0:npc:guard:0",
        event_index=0,
        event_type="text_chunk",
        text="Old",
    )
    state = append_llm_stream_event(
        state,
        request_id="llmreq:22:0:npc:guard:0",
        event_index=0,
        event_type="text_chunk",
        text="New",
    )

    llm = get_llm_orchestration_state(state)
    request = llm["active_requests"][0]
    assert len(request["stream_events"]) == 1
    assert request["stream_events"][0]["text"] == "New"


def test_phase106_finalize_llm_request_moves_to_completed():
    state = {}
    state = begin_llm_request(
        state,
        tick=30,
        sequence_index=3,
        actor_id="comp:lyra",
        turn_id="turn:30:3:comp:lyra",
    )
    state = append_llm_stream_event(
        state,
        request_id="llmreq:30:3:comp:lyra:0",
        event_index=0,
        text="We should move.",
    )
    state = finalize_llm_request(
        state,
        request_id="llmreq:30:3:comp:lyra:0",
        output_text="We should move.",
    )

    llm = get_llm_orchestration_state(state)
    assert llm["active_requests"] == []
    assert len(llm["completed_requests"]) == 1
    request = llm["completed_requests"][0]
    assert request["status"] == "complete"
    assert request["output_text"] == "We should move."


def test_phase106_finalize_llm_request_can_mark_replayed():
    state = {}
    state = begin_llm_request(
        state,
        tick=31,
        sequence_index=0,
        actor_id="npc:guard",
        turn_id="turn:31:0:npc:guard",
    )
    state = finalize_llm_request(
        state,
        request_id="llmreq:31:0:npc:guard:0",
        output_text="Stop.",
        replayed=True,
    )

    llm = get_llm_orchestration_state(state)
    request = llm["completed_requests"][0]
    assert request["status"] == "replayed"
    assert request["output_text"] == "Stop."


def test_phase106_fail_llm_request_moves_to_completed_and_sets_last_error():
    state = {}
    state = begin_llm_request(
        state,
        tick=40,
        sequence_index=1,
        actor_id="npc:guard",
        turn_id="turn:40:1:npc:guard",
    )
    state = fail_llm_request(
        state,
        request_id="llmreq:40:1:npc:guard:0",
        error="provider timeout",
    )

    llm = get_llm_orchestration_state(state)
    assert llm["active_requests"] == []
    assert len(llm["completed_requests"]) == 1
    request = llm["completed_requests"][0]
    assert request["status"] == "failed"
    assert request["error"] == "provider timeout"
    assert llm["last_error"] == {
        "request_id": "llmreq:40:1:npc:guard:0",
        "error": "provider timeout",
    }


def test_phase106_provider_mode_defaults_to_disabled():
    assert get_llm_provider_mode({}) == "disabled"


def test_phase106_set_llm_provider_mode_normalizes_values():
    state = {}
    state = set_llm_provider_mode(state, "capture")
    assert get_llm_provider_mode(state) == "capture"

    state = set_llm_provider_mode(state, "INVALID")
    assert get_llm_provider_mode(state) == "disabled"


def test_phase106_build_disabled_provider_result_is_empty_and_deterministic():
    result = build_disabled_provider_result({
        "turn": {
            "turn_id": "turn:10:1:comp:lyra",
        }
    })
    assert result == {
        "provider_mode": "disabled",
        "provider": "",
        "model": "",
        "status": "disabled",
        "turn_id": "turn:10:1:comp:lyra",
        "output_text": "",
        "stream_events": [],
        "error": "",
    }


def test_phase106_build_replay_provider_result_uses_captured_request_record():
    result = build_replay_provider_result({
        "provider": "openai",
        "model": "gpt-test",
        "turn_id": "turn:11:0:npc:guard",
        "output_text": "Hold there.",
        "stream_events": [
            {"event_index": 0, "event_type": "text_chunk", "text": "Hold ", "final": False, "raw": {}},
            {"event_index": 1, "event_type": "text_chunk", "text": "there.", "final": True, "raw": {}},
        ],
        "error": "",
    })

    assert result["provider_mode"] == "replay"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-test"
    assert result["turn_id"] == "turn:11:0:npc:guard"
    assert result["output_text"] == "Hold there."
    assert len(result["stream_events"]) == 2


def test_phase106_dedupe_and_sort_stream_events_overwrites_duplicates():
    events = [
        {
            "event_index": 1,
            "event_type": "text_chunk",
            "text": "B",
            "final": False,
            "raw": {},
        },
        {
            "event_index": 0,
            "event_type": "text_chunk",
            "text": "A",
            "final": False,
            "raw": {},
        },
        {
            "event_index": 1,
            "event_type": "text_chunk",
            "text": "B2",
            "final": False,
            "raw": {},
        },
    ]

    out = _dedupe_and_sort_stream_events(events)
    assert len(out) == 2
    assert out[0]["event_index"] == 0
    assert out[0]["text"] == "A"
    assert out[1]["event_index"] == 1
    assert out[1]["text"] == "B2"


def test_phase106_normalize_request_bounds_stream_events():
    request = {
        "request_id": "llmreq:1:0:npc:a:0",
        "tick": 1,
        "sequence_id": "seq:1:0",
        "turn_id": "turn:1:0:npc:a",
        "actor_id": "npc:a",
        "speaker_id": "npc:a",
        "mode": "dialogue",
        "status": "streaming",
        "provider": "test",
        "model": "test-model",
        "input_payload": {},
        "stream_events": [
            {
                "event_index": i,
                "event_type": "text_chunk",
                "text": str(i),
                "final": False,
                "raw": {},
            }
            for i in range(60)
        ],
        "output_text": "",
        "error": "",
    }

    out = _normalize_request(request)
    assert len(out["stream_events"]) == 40
    assert out["stream_events"][0]["event_index"] == 20
    assert out["stream_events"][-1]["event_index"] == 59


def test_phase106_should_allow_llm_fallback_policy():
    payload = {
        "constraints": {
            "allow_emotional_fallback": True,
        }
    }
    assert should_allow_llm_fallback(payload, provider_mode="disabled") is True
    assert should_allow_llm_fallback(payload, provider_mode="capture") is True
    assert should_allow_llm_fallback(payload, provider_mode="live") is True
    assert should_allow_llm_fallback(payload, provider_mode="replay") is False


def test_phase106_request_id_counter_parses_correctly():
    assert _request_id_counter("llmreq:10:1:comp:lyra:0") == 0
    assert _request_id_counter("llmreq:10:1:comp:lyra:5") == 5


def test_phase106_build_llm_fallback_result_is_structured():
    result = build_llm_fallback_result(
        {
            "turn": {
                "turn_id": "turn:12:0:npc:guard",
            }
        },
        provider_mode="disabled",
        allow_fallback=True,
    )
    assert result == {
        "provider_mode": "disabled",
        "provider": "",
        "model": "",
        "status": "fallback",
        "turn_id": "turn:12:0:npc:guard",
        "output_text": "",
        "stream_events": [],
        "error": "",
        "allow_fallback": True,
    }