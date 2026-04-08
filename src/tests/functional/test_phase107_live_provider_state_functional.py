from app.rpg.orchestration.live_provider import (
    build_provider_execution_id,
    ensure_live_provider_state,
    get_live_provider_state,
)


def test_phase107_live_provider_state_is_created_and_normalized():
    state = ensure_live_provider_state({})
    live_state = get_live_provider_state(state)

    assert "orchestration_state" in state
    assert "live_provider" in state["orchestration_state"]
    assert live_state["executions"] == []


def test_phase107_provider_execution_id_is_deterministic():
    assert build_provider_execution_id("llmreq:12:3:comp:lyra:0") == "provexec:llmreq:12:3:comp:lyra:0"


def test_phase107_live_provider_state_is_bounded():
    executions = []
    for i in range(20):
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