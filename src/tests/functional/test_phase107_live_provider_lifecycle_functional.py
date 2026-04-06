from app.rpg.orchestration.live_provider import (
    begin_provider_execution,
    append_provider_execution_event,
    finalize_provider_execution,
    fail_provider_execution,
    get_live_provider_state,
)


def test_phase107_begin_provider_execution_creates_pending_execution():
    state = {}
    state = begin_provider_execution(
        state,
        request_id="llmreq:15:2:comp:lyra:0",
        tick=15,
        provider="openai",
        model="gpt-test",
    )

    live_state = get_live_provider_state(state)
    assert len(live_state["executions"]) == 1
    execution = live_state["executions"][0]
    assert execution["execution_id"] == "provexec:llmreq:15:2:comp:lyra:0"
    assert execution["status"] == "pending"
    assert execution["provider"] == "openai"
    assert execution["model"] == "gpt-test"


def test_phase107_append_provider_execution_event_updates_execution():
    state = {}
    state = begin_provider_execution(
        state,
        request_id="llmreq:20:1:npc:guard:0",
        tick=20,
        provider="openai",
        model="gpt-test",
    )
    state = append_provider_execution_event(
        state,
        execution_id="provexec:llmreq:20:1:npc:guard:0",
        event_index=0,
        event_type="request_started",
    )
    state = append_provider_execution_event(
        state,
        execution_id="provexec:llmreq:20:1:npc:guard:0",
        event_index=1,
        event_type="text_chunk",
        text="Hold ",
        final=False,
    )

    live_state = get_live_provider_state(state)
    execution = live_state["executions"][0]
    assert execution["status"] == "streaming"
    assert len(execution["events"]) == 2
    assert execution["events"][1]["text"] == "Hold "


def test_phase107_finalize_provider_execution_marks_complete():
    state = {}
    state = begin_provider_execution(
        state,
        request_id="llmreq:30:3:comp:lyra:0",
        tick=30,
        provider="openai",
        model="gpt-test",
    )
    state = finalize_provider_execution(
        state,
        execution_id="provexec:llmreq:30:3:comp:lyra:0",
        output_text="We should move.",
    )

    live_state = get_live_provider_state(state)
    execution = live_state["executions"][0]
    assert execution["status"] == "complete"
    assert execution["output_text"] == "We should move."


def test_phase107_fail_provider_execution_marks_failed():
    state = {}
    state = begin_provider_execution(
        state,
        request_id="llmreq:40:1:npc:guard:0",
        tick=40,
        provider="openai",
        model="gpt-test",
    )
    state = fail_provider_execution(
        state,
        execution_id="provexec:llmreq:40:1:npc:guard:0",
        error="timeout",
    )

    live_state = get_live_provider_state(state)
    execution = live_state["executions"][0]
    assert execution["status"] == "failed"
    assert execution["error"] == "timeout"