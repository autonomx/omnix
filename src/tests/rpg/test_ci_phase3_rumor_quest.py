def test_ci_phase3_rumor_registers_with_source_and_heard_status():
    from app.rpg.quests.rumors import register_rumor

    state = {}
    result = register_rumor(
        state,
        rumor_id="rumor:old_mill_bandit",
        summary="Travelers whisper about a bandit near the old mill road.",
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        location_id="location:rusty_flagon",
        turn_index=3,
    )

    rumor = result["rumor"]
    assert result["ok"] is True
    assert result["source"] == "deterministic_rumor_quest_runtime"
    assert rumor["status"] == "heard"
    assert rumor["heard_turn"] == 3
    assert rumor["quest_id"] == "quest:clear_the_road"
    assert state["rumor_state"]["source"] == "deterministic_rumor_quest_runtime"


def test_ci_phase3_rumor_backing_records_evidence_and_dedupes():
    from app.rpg.quests.rumors import back_rumor_with_evidence, register_rumor

    state = {}
    register_rumor(state, rumor_id="rumor:old_mill_bandit", summary="Bandit rumor.", quest_id="quest:clear_the_road", giver_id="npc:bran")
    first = back_rumor_with_evidence(
        state,
        rumor_id="rumor:old_mill_bandit",
        evidence_id="evidence:bran:witness",
        source_id="npc:bran",
        summary="Bran saw road tolls rise after the bandit arrived.",
        kind="witness",
        turn_index=4,
    )
    duplicate = back_rumor_with_evidence(
        state,
        rumor_id="rumor:old_mill_bandit",
        evidence_id="evidence:bran:witness",
        source_id="npc:bran",
        summary="Duplicate.",
        turn_index=5,
    )

    assert first["reason"] == "rumor_backed"
    assert first["rumor"]["status"] == "backed"
    assert first["rumor"]["backed_turn"] == 4
    assert first["rumor"]["evidence"][0]["source"] == "deterministic_rumor_quest_runtime"
    assert duplicate["reason"] == "duplicate_evidence_ignored"
    assert len(duplicate["rumor"]["evidence"]) == 1


def test_ci_phase3_unbacked_rumor_does_not_convert_to_quest_offer():
    from copy import deepcopy

    from app.rpg.quests.rumors import convert_rumor_to_quest_offer, register_rumor

    state = {}
    register_rumor(state, rumor_id="rumor:old_mill_bandit", summary="Bandit rumor.", quest_id="quest:clear_the_road", giver_id="npc:bran")
    before = deepcopy(state)
    result = convert_rumor_to_quest_offer(state, rumor_id="rumor:old_mill_bandit", turn_index=6)

    assert result["ok"] is False
    assert result["reason"] == "rumor_not_backed"
    assert result["source"] == "deterministic_rumor_quest_runtime"
    assert state == before


def test_ci_phase3_backed_rumor_converts_to_quest_offer():
    from app.rpg.quests.givers import available_quest_offers
    from app.rpg.quests.rumors import back_rumor_with_evidence, convert_rumor_to_quest_offer, register_rumor

    state = {}
    register_rumor(state, rumor_id="rumor:old_mill_bandit", summary="Bandit rumor.", quest_id="quest:clear_the_road", giver_id="npc:bran")
    back_rumor_with_evidence(state, rumor_id="rumor:old_mill_bandit", evidence_id="evidence:bran:witness", source_id="npc:bran", summary="Bran confirms the old road danger.", turn_index=5)
    result = convert_rumor_to_quest_offer(state, rumor_id="rumor:old_mill_bandit", turn_index=6)
    offers = available_quest_offers(state, giver_id="npc:bran")

    assert result["ok"] is True
    assert result["reason"] == "rumor_converted_to_quest_offer"
    assert result["source"] == "deterministic_rumor_quest_runtime"
    assert result["rumor"]["status"] == "converted"
    assert result["rumor"]["converted_turn"] == 6
    assert result["offer_result"]["source"] == "deterministic_quest_giver_state"
    assert offers["offers"][0]["quest_id"] == "quest:clear_the_road"
    assert offers["offers"][0]["status"] == "offered"


def test_ci_phase3_backed_rumor_propagation_summary_is_source_backed():
    from app.rpg.quests.rumors import back_rumor_with_evidence, build_rumor_summary, propagate_backed_rumors, register_rumor

    state = {}
    register_rumor(state, rumor_id="rumor:old_mill_bandit", summary="Bandit rumor.", quest_id="quest:clear_the_road", giver_id="npc:bran")
    back_rumor_with_evidence(state, rumor_id="rumor:old_mill_bandit", evidence_id="evidence:road:toll", source_id="location:road", summary="Fresh toll markers were found on the old road.", turn_index=5)

    propagation = propagate_backed_rumors(state)
    summary = build_rumor_summary(state)

    assert propagation["ok"] is True
    assert propagation["source"] == "deterministic_rumor_quest_runtime"
    assert propagation["backed_rumors"][0]["rumor_id"] == "rumor:old_mill_bandit"
    assert propagation["backed_rumors"][0]["evidence_count"] == 1
    assert summary["source"] == "deterministic_rumor_quest_runtime"
    assert summary["rumor_count"] == 1
    assert summary["backed_count"] == 1


def test_ci_phase3_rumor_helpers_are_exported():
    from app.rpg import quests

    assert quests.register_rumor
    assert quests.back_rumor_with_evidence
    assert quests.convert_rumor_to_quest_offer
    assert quests.propagate_backed_rumors
    assert quests.build_rumor_summary
