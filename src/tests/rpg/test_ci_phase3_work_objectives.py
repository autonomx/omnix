def test_ci_phase3_work_inquiry_classifier_detects_work_terms():
    from app.rpg.quests.work import classify_work_inquiry

    result = classify_work_inquiry("Do you have any work or rumors for me?")

    assert result["ok"] is True
    assert result["reason"] == "work_inquiry_detected"
    assert "work" in result["matched_terms"]
    assert "rumors" in result["matched_terms"]
    assert result["source"] == "deterministic_work_inquiry_runtime"


def test_ci_phase3_work_inquiry_classifier_rejects_unrelated_text():
    from app.rpg.quests.work import classify_work_inquiry

    result = classify_work_inquiry("I buy two rations.")

    assert result["ok"] is False
    assert result["reason"] == "work_inquiry_not_detected"
    assert result["matched_terms"] == []
    assert result["source"] == "deterministic_work_inquiry_runtime"


def test_ci_phase3_work_inquiry_routes_to_available_quest_offer():
    from app.rpg.quests.work import route_work_inquiry

    state = {}
    result = route_work_inquiry(
        state,
        giver_id="npc:bran",
        player_text="Any work around here?",
        turn_index=4,
    )

    offers = result["offers"]["offers"]
    assert result["ok"] is True
    assert result["reason"] == "work_inquiry_routed"
    assert result["source"] == "deterministic_work_inquiry_runtime"
    assert result["classification"]["source"] == "deterministic_work_inquiry_runtime"
    assert offers[0]["quest_id"] == "quest:clear_the_road"
    assert offers[0]["status"] == "offered"
    assert state["quest_giver_state"]["givers"]["npc:bran"]["offers"]["quest:clear_the_road"]["offered_turn"] == 4


def test_ci_phase3_non_work_inquiry_does_not_mutate_state():
    from copy import deepcopy

    from app.rpg.quests.work import route_work_inquiry

    state = {"player_state": {"name": "CI"}}
    before = deepcopy(state)
    result = route_work_inquiry(
        state,
        giver_id="npc:bran",
        player_text="I rent a room.",
        turn_index=4,
    )

    assert result["ok"] is False
    assert result["reason"] == "not_work_inquiry"
    assert result["source"] == "deterministic_work_inquiry_runtime"
    assert state == before


def test_ci_phase3_objective_suggestions_use_active_open_objectives():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.work import suggest_objectives

    state = {}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=5)
    result = suggest_objectives(state, limit=2)

    suggestion = result["suggestions"][0]
    assert result["ok"] is True
    assert result["reason"] == "objective_suggestions_built"
    assert result["source"] == "deterministic_work_inquiry_runtime"
    assert suggestion["quest_id"] == "quest:clear_the_road"
    assert suggestion["objective_id"] == "objective:defeat_bandit"
    assert suggestion["suggested_action"] == "Track and defeat enemy:bandit_1."
    assert suggestion["source"] == "deterministic_work_inquiry_runtime"


def test_ci_phase3_work_narration_contract_limits_claims():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.work import build_work_inquiry_narration_contract, route_work_inquiry

    state = {}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=2)
    result = route_work_inquiry(
        state,
        giver_id="npc:bran",
        player_text="Do you have any work?",
        turn_index=6,
    )
    contract = build_work_inquiry_narration_contract(result)

    assert contract["source"] == "deterministic_work_inquiry_runtime"
    assert "Objective suggestion: quest:clear_the_road / objective:defeat_bandit" in contract["allowed_work_claims"]
    assert any("Do not invent unavailable jobs" in claim for claim in contract["forbidden_work_claims"])
    assert any("Do not mark objectives complete" in claim for claim in contract["forbidden_work_claims"])


def test_ci_phase3_work_helpers_are_exported():
    from app.rpg import quests

    assert quests.classify_work_inquiry
    assert quests.route_work_inquiry
    assert quests.suggest_objectives
    assert quests.build_work_inquiry_narration_contract
