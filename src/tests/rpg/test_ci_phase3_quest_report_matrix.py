def _phase3_matrix_state():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.journal import add_journal_entry_from_objective_result
    from app.rpg.quests.objectives import complete_objective_lifecycle
    from app.rpg.quests.rewards import claim_quest_rewards
    from app.rpg.quests.rumors import back_rumor_with_evidence, convert_rumor_to_quest_offer, register_rumor

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"silver": 2}}}}
    register_rumor(
        state,
        rumor_id="rumor:old_mill_bandit",
        summary="Travelers whisper about a bandit near the old mill road.",
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        location_id="location:rusty_flagon",
        turn_index=1,
    )
    back_rumor_with_evidence(
        state,
        rumor_id="rumor:old_mill_bandit",
        evidence_id="evidence:bran:witness",
        source_id="npc:bran",
        summary="Bran confirms the road danger.",
        turn_index=2,
    )
    convert_rumor_to_quest_offer(state, rumor_id="rumor:old_mill_bandit", turn_index=3)
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=4)
    objective_result = complete_objective_lifecycle(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        turn_index=8,
    )
    add_journal_entry_from_objective_result(
        state,
        objective_result,
        turn_index=8,
        what_i_learned="The old road is safe enough for trade again.",
    )
    claim_quest_rewards(state, quest_id="quest:clear_the_road", turn_index=9)
    return state


def test_ci_phase3_quest_report_model_covers_lifecycle_sources_and_counts():
    from app.rpg.quests.reporting import build_phase3_quest_report_model

    model = build_phase3_quest_report_model(_phase3_matrix_state())
    summary = model["summary"]
    quest = model["quests"][0]

    assert model["source"] == "deterministic_phase3_quest_report"
    assert summary["quest_count"] == 1
    assert summary["completed_count"] == 1
    assert summary["journal_entry_count"] == 1
    assert summary["rumor_count"] == 1
    assert summary["reward_log_count"] == 1
    assert quest["quest_id"] == "quest:clear_the_road"
    assert quest["status"] == "completed"
    assert quest["reward_claimed"] is True
    assert quest["objectives"][0]["objective_id"] == "objective:defeat_bandit"
    assert quest["objectives"][0]["status"] == "completed"
    assert model["persistence"]["source"] == "deterministic_quest_persistence"


def test_ci_phase3_quest_report_html_is_escaped_and_source_backed():
    from app.rpg.quests.journal import add_journal_entry
    from app.rpg.quests.reporting import render_phase3_quest_report_html

    state = _phase3_matrix_state()
    add_journal_entry(
        state,
        quest_id="quest:<unsafe>",
        what_happened="Saw <script>bad</script>",
        next_objective="Return <home>",
        turn_index=10,
    )

    html = render_phase3_quest_report_html(state)

    assert "Phase 3 Quest Report" in html
    assert "Quests: <strong>1</strong>" in html
    assert "quest:clear_the_road" in html
    assert "objective:defeat_bandit: completed" in html
    assert "quest:&lt;unsafe&gt;: Return &lt;home&gt;" in html
    assert "<script>bad</script>" not in html
    assert "deterministic_phase3_quest_report" in html


def test_ci_phase3_matrix_payload_requires_all_phase3_substates():
    from app.rpg.quests.reporting import build_phase3_matrix_scenario_payload

    full = build_phase3_matrix_scenario_payload(_phase3_matrix_state())
    empty = build_phase3_matrix_scenario_payload({})

    assert full["source"] == "deterministic_phase3_quest_report"
    assert full["scenario_id"] == "phase3_full_quest_lifecycle_matrix"
    assert full["ready"] is True
    assert full["covered"] == {
        "quest_state": True,
        "objective_state": True,
        "journal_state": True,
        "rumor_state": True,
        "reward_state": True,
        "persistence_state": True,
    }
    assert empty["ready"] is False
    assert empty["covered"]["quest_state"] is False


def test_ci_phase3_reporting_helpers_are_exported():
    from app.rpg import quests

    assert quests.build_phase3_quest_report_model
    assert quests.render_phase3_quest_report_html
    assert quests.build_phase3_matrix_scenario_payload
