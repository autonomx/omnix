def _phase3_complete_state():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.journal import add_journal_entry_from_objective_result
    from app.rpg.quests.objectives import complete_objective_lifecycle
    from app.rpg.quests.return_flow import report_completed_quest_to_giver
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
    report_completed_quest_to_giver(
        state,
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        player_text="I return to Bran and report the quest is done.",
        turn_index=9,
    )
    return state


def test_ci_phase3_completion_audit_marks_all_phase3_gates_complete():
    from app.rpg.quests.completion_audit import build_phase3_completion_audit

    audit = build_phase3_completion_audit(_phase3_complete_state())

    assert audit["source"] == "deterministic_phase3_completion_audit"
    assert audit["phase"] == "3.10"
    assert audit["status"] == "complete"
    assert audit["gate_count"] == 13
    assert audit["completed_gate_count"] == 13
    assert [row["pr"] for row in audit["completed_prs"]] == [149, 150, 151, 152, 153, 154, 155, 156, 157]
    assert all(row["complete"] is True for row in audit["gates"])
    assert audit["next_recommended_phase"] == "Phase 4.1 — canonical location graph foundation"


def test_ci_phase3_completion_audit_uses_runtime_matrix_evidence():
    from app.rpg.quests.completion_audit import assert_phase3_completion_ready, build_phase3_completion_audit

    ready = assert_phase3_completion_ready(_phase3_complete_state())
    incomplete = build_phase3_completion_audit({})

    assert ready["ok"] is True
    assert ready["reason"] == "phase3_completion_ready"
    assert ready["audit"]["runtime_ready"] is True
    assert ready["audit"]["blockers"] == []
    assert incomplete["runtime_ready"] is False
    assert incomplete["blockers"][0]["kind"] == "runtime_matrix_coverage"
    assert "quest_state" in incomplete["blockers"][0]["missing"]


def test_ci_phase3_completion_audit_scorecard_updates_are_source_backed():
    from app.rpg.quests.completion_audit import build_phase3_completion_audit

    audit = build_phase3_completion_audit(_phase3_complete_state())
    scorecard = audit["scorecard_updates"]

    assert scorecard["core_gameplay_mechanics"]["from"] == 6.2
    assert scorecard["core_gameplay_mechanics"]["to"] == 6.8
    assert "Quest lifecycle" in scorecard["core_gameplay_mechanics"]["reason"]
    assert scorecard["testability_diagnostics"]["to"] == 8.8
    assert scorecard["production_readiness"]["to"] == 3.8


def test_ci_phase3_completion_audit_helpers_are_exported():
    from app.rpg import quests

    assert quests.build_phase3_completion_audit
    assert quests.assert_phase3_completion_ready
