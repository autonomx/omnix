def _completed_unreported_state():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.objectives import complete_objective_lifecycle

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"silver": 2}}}}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=2)
    complete_objective_lifecycle(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        turn_index=8,
    )
    return state


def test_ci_phase3_quest_return_classifier_detects_return_terms():
    from app.rpg.quests.return_flow import classify_quest_return

    result = classify_quest_return("I return to Bran and report the job is done.")

    assert result["ok"] is True
    assert result["reason"] == "quest_return_detected"
    assert "return" in result["matched_terms"]
    assert "report" in result["matched_terms"]
    assert result["source"] == "deterministic_quest_return_flow"


def test_ci_phase3_non_return_text_rejects_without_mutation():
    from copy import deepcopy

    from app.rpg.quests.return_flow import report_completed_quest_to_giver

    state = _completed_unreported_state()
    before = deepcopy(state)
    result = report_completed_quest_to_giver(
        state,
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        player_text="I buy a ration.",
        turn_index=9,
    )

    assert result["ok"] is False
    assert result["reason"] == "not_quest_return"
    assert result["source"] == "deterministic_quest_return_flow"
    assert state == before


def test_ci_phase3_incomplete_quest_report_rejects_without_mutation():
    from copy import deepcopy

    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.return_flow import report_completed_quest_to_giver

    state = {"player_state": {"inventory_state": {"currency": {"silver": 2}}}}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=2)
    before = deepcopy(state)
    result = report_completed_quest_to_giver(
        state,
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        player_text="I report the quest is complete.",
        turn_index=9,
    )

    assert result["ok"] is False
    assert result["reason"] == "quest_not_completed"
    assert result["source"] == "deterministic_quest_return_flow"
    assert state == before


def test_ci_phase3_completed_quest_report_claims_reward_and_adds_journal():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.quests.return_flow import report_completed_quest_to_giver

    state = _completed_unreported_state()
    result = report_completed_quest_to_giver(
        state,
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        player_text="I return to Bran to report the job is done and claim my reward.",
        turn_index=9,
    )

    quest = state["quest_state"]["quests"]["quest:clear_the_road"]
    assert result["ok"] is True
    assert result["reason"] == "quest_reported_to_giver"
    assert result["source"] == "deterministic_quest_return_flow"
    assert result["reward_result"]["reason"] == "rewards_claimed"
    assert get_player_currency(state) == {"gold": 1, "silver": 4, "copper": 0}
    assert quest["reported_to_giver"] is True
    assert quest["reported_to_giver_id"] == "npc:bran"
    assert quest["report_log"][0]["source"] == "deterministic_quest_return_flow"
    assert state["journal_state"]["entries"][-1]["event_type"] == "quest_reported_to_giver"


def test_ci_phase3_completed_quest_report_is_idempotent_for_rewards():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.quests.return_flow import report_completed_quest_to_giver

    state = _completed_unreported_state()
    first = report_completed_quest_to_giver(
        state,
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        player_text="I report the quest is finished.",
        turn_index=9,
    )
    second = report_completed_quest_to_giver(
        state,
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        player_text="I report the quest is finished again.",
        turn_index=10,
    )

    assert first["reward_result"]["reason"] == "rewards_claimed"
    assert second["ok"] is True
    assert second["reason"] == "quest_already_reported_to_giver"
    assert second["reward_result"]["reason"] == "already_claimed"
    assert get_player_currency(state) == {"gold": 1, "silver": 4, "copper": 0}
    assert len(state["quest_state"]["quests"]["quest:clear_the_road"]["report_log"]) == 2


def test_ci_phase3_return_narration_contract_limits_claims():
    from app.rpg.quests.return_flow import build_quest_return_narration_contract, report_completed_quest_to_giver

    state = _completed_unreported_state()
    result = report_completed_quest_to_giver(
        state,
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        player_text="I return and report it is complete.",
        turn_index=9,
    )
    contract = build_quest_return_narration_contract(result)

    assert contract["source"] == "deterministic_quest_return_flow"
    assert "Quest reported: quest:clear_the_road to npc:bran" in contract["allowed_return_claims"]
    assert any(claim.startswith("Rewards claimed:") for claim in contract["allowed_return_claims"])
    assert any("Do not claim unearned rewards" in claim for claim in contract["forbidden_return_claims"])
    assert any("Do not report an incomplete quest" in claim for claim in contract["forbidden_return_claims"])


def test_ci_phase3_return_helpers_are_exported():
    from app.rpg import quests

    assert quests.classify_quest_return
    assert quests.report_completed_quest_to_giver
    assert quests.build_quest_return_narration_contract
