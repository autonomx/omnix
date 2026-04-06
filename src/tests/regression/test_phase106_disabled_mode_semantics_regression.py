"""Phase 10.6 — Regression tests for disabled-mode semantics fixes."""
from app.rpg.runtime.dialogue_runtime import begin_runtime_turn
from app.rpg.orchestration.provider_interface import set_llm_provider_mode
from app.rpg.orchestration.controller import execute_llm_request_for_turn
from app.rpg.orchestration.state import get_llm_orchestration_state


def test_phase106_disabled_mode_without_fallback_is_not_marked_success():
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
        extra_constraints={"allow_emotional_fallback": False},
    )

    llm = get_llm_orchestration_state(state)
    assert llm["active_requests"] == []
    assert len(llm["completed_requests"]) == 1
    assert llm["completed_requests"][0]["status"] == "failed"
    assert llm["last_error"]["error"] == "Provider mode disabled and fallback not allowed"