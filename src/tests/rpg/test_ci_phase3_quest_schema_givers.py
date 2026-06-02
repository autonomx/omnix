def test_ci_phase3_quest_template_schema_normalizes_default_road_quest():
    from app.rpg.quests.templates import get_quest_template, quest_template_to_start_payload

    template = get_quest_template("quest:clear_the_road")
    payload = quest_template_to_start_payload(template)

    assert template["source"] == "deterministic_quest_templates"
    assert template["quest_id"] == "quest:clear_the_road"
    assert template["giver_id"] == "npc:bran"
    assert template["objectives"][0]["objective_id"] == "objective:defeat_bandit"
    assert template["objectives"][0]["target_ids"] == ["enemy:bandit_1"]
    assert payload["source"] == "deterministic_quest_templates"
    assert payload["stage"] == "offered"
    assert payload["objectives"]["objective:defeat_bandit"]["status"] == "open"
    assert payload["metadata"]["giver_id"] == "npc:bran"


def test_ci_phase3_quest_giver_registers_available_offer_idempotently():
    from app.rpg.quests.givers import available_quest_offers, register_quest_offer

    state = {}
    first = register_quest_offer(
        state,
        giver_id="npc:bran",
        quest_id="quest:clear_the_road",
        turn_index=3,
    )
    second = register_quest_offer(
        state,
        giver_id="npc:bran",
        quest_id="quest:clear_the_road",
        turn_index=9,
    )
    offers = available_quest_offers(state, giver_id="npc:bran")

    assert first["ok"] is True
    assert first["source"] == "deterministic_quest_giver_state"
    assert first["offer"]["status"] == "offered"
    assert second["offer"]["status"] == "offered"
    assert second["offer"]["offered_turn"] == 3
    assert state["quest_giver_state"]["source"] == "deterministic_quest_giver_state"
    assert offers["offers"][0]["quest_id"] == "quest:clear_the_road"
    assert offers["offers"][0]["available"] is True
    assert offers["offers"][0]["conditions"]["ok"] is True


def test_ci_phase3_quest_giver_accepts_offer_and_starts_quest_from_template():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.state import get_quest

    state = {}
    result = accept_quest_offer(
        state,
        giver_id="npc:bran",
        quest_id="quest:clear_the_road",
        turn_index=7,
    )
    quest = get_quest(state, "quest:clear_the_road")
    offer = state["quest_giver_state"]["givers"]["npc:bran"]["offers"]["quest:clear_the_road"]

    assert result["ok"] is True
    assert result["reason"] == "quest_offer_accepted"
    assert result["source"] == "deterministic_quest_giver_state"
    assert offer["status"] == "accepted"
    assert offer["accepted_turn"] == 7
    assert quest["status"] == "active"
    assert quest["stage"] == "offered"
    assert quest["started_turn"] == 7
    assert quest["metadata"]["giver_id"] == "npc:bran"
    assert quest["objectives"]["objective:defeat_bandit"]["status"] == "open"
    assert quest["objectives"]["objective:defeat_bandit"]["metadata"]["target_ids"] == ["enemy:bandit_1"]
    assert quest["rewards"][0] == {"type": "currency", "currency": {"silver": 12}}


def test_ci_phase3_quest_giver_rejects_wrong_giver_without_mutation():
    from app.rpg.quests.givers import register_quest_offer

    state = {}
    result = register_quest_offer(
        state,
        giver_id="npc:elara",
        quest_id="quest:clear_the_road",
        turn_index=1,
    )

    assert result["ok"] is False
    assert result["reason"] == "quest_giver_mismatch"
    assert result["expected_giver_id"] == "npc:bran"
    assert "quest_giver_state" not in state
