"""Phase 107 — Live Provider State regression tests.

Ensures that the live provider state module maintains backward
compatibility and does not regress on core invariants.
"""
from app.rpg.orchestration.live_provider import (
    ensure_live_provider_state,
    get_live_provider_state,
    begin_provider_execution,
    append_provider_execution_event,
    finalize_provider_execution,
    fail_provider_execution,
    build_provider_execution_id,
)


def test_phase107_empty_state_returns_empty_executions():
    state = ensure_live_provider_state({})
    live_state = get_live_provider_state(state)
    assert live_state["executions"] == []


def test_phase107_existing_executions_are_preserved():
    state = {
        "orchestration_state": {
            "live_provider": {
                "executions": [
                    {
                        "execution_id": "provexec:llmreq:1:1:npc:guard:0",
                        "request_id": "llmreq:1:1:npc:guard:0",
                        "tick": 1,
                        "provider": "openai",
                        "model": "gpt-test",
                        "status": "complete",
                        "events": [],
                        "output_text": "ok",
                        "error": "",
                    }
                ]
            }
        }
    }
    state = ensure_live_provider_state(state)
    live_state = get_live_provider_state(state)
    assert len(live_state["executions"]) == 1
    assert live_state["executions"][0]["execution_id"] == "provexec:llmreq:1:1:npc:guard:0"


def test_phase107_execution_id_format_is_stable():
    assert build_provider_execution_id("llmreq:1:1:npc:guard:0") == "provexec:llmreq:1:1:npc:guard:0"


def test_phase107_begin_execution_does_not_mutate_original_state():
    original = {}
    state = dict(original)
    state = begin_provider_execution(
        state,
        request_id="llmreq:5:1:npc:guard:0",
        tick=5,
        provider="openai",
        model="gpt-test",
    )
    assert "orchestration_state" not in original
    assert "orchestration_state" in state


def test_phase107_finalize_execution_preserves_events():
    state = {}
    state = begin_provider_execution(
        state,
        request_id="llmreq:10:1:npc:guard:0",
        tick=10,
        provider="openai",
        model="gpt-test",
    )
    state = append_provider_execution_event(
        state,
        execution_id="provexec:llmreq:10:1:npc:guard:0",
        event_index=0,
        event_type="request_started",
    )
    state = finalize_provider_execution(
        state,
        execution_id="provexec:llmreq:10:1:npc:guard:0",
        output_text="done",
    )
    live_state = get_live_provider_state(state)
    execution = live_state["executions"][0]
    assert len(execution["events"]) == 1
    assert execution["output_text"] == "done"


def test_phase107_fail_execution_preserves_error_message():
    state = {}
    state = begin_provider_execution(
        state,
        request_id="llmreq:15:1:npc:guard:0",
        tick=15,
        provider="openai",
        model="gpt-test",
    )
    state = fail_provider_execution(
        state,
        execution_id="provexec:llmreq:15:1:npc:guard:0",
        error="connection refused",
    )
    live_state = get_live_provider_state(state)
    execution = live_state["executions"][0]
    assert execution["status"] == "failed"
    assert execution["error"] == "connection refused"


def test_phase107_max_executions_is_enforced():
    executions = []
    for i in range(15):
        executions.append({
            "execution_id": f"provexec:llmreq:1:{i}:npc:{i}:0",
            "request_id": f"llmreq:1:{i}:npc:{i}:0",
            "tick": 1,
            "provider": "openai",
            "model": "gpt-test",
            "status": "complete",
            "events": [],
            "output_text": "ok",
            "error": "",
        })

    state = ensure_live_provider_state({
        "orchestration_state": {
            "live_provider": {
                "executions": executions,
            }
        }
    })
    live_state = get_live_provider_state(state)
    assert len(live_state["executions"]) == 12