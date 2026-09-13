from __future__ import annotations


def test_npc_plan_is_dialogue_without_runtime() -> None:
    from app.rpg.session.turn_plan import build_turn_plan_for_response

    plan = build_turn_plan_for_response(
        intent_result={"kind": "request", "confidence": "high"},
        world_assessment={"actionability": "respond_only", "state_change_allowed": False, "confidence": "high"},
        response_authority={"source": "addressed_npc", "confidence": "high"},
    )

    assert plan["runtime_required"] is False
    assert plan["presentation_type"] == "npc_dialogue"
    assert plan["state_mutation_allowed"] is False
    assert plan["renderer_may_decide_truth"] is False


def test_system_plan_is_clarification() -> None:
    from app.rpg.session.turn_plan import build_turn_plan_for_response

    plan = build_turn_plan_for_response(
        intent_result={"kind": "unknown", "confidence": "unknown"},
        world_assessment={"actionability": "clarify", "state_change_allowed": False, "confidence": "unknown"},
        response_authority={"source": "system", "confidence": "high"},
    )

    assert plan["runtime_required"] is False
    assert plan["presentation_type"] == "system_clarification"
