def _completed_objective_state():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.objectives import update_objective_progress

    state = {}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=2)
    objective_result = update_objective_progress(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        event_id="combat:defeat:bandit_1",
        amount=1,
        turn_index=8,
    )
    return state, objective_result


def test_ci_phase3_journal_entry_records_happened_learned_next_with_source():
    from app.rpg.quests.journal import add_journal_entry

    state = {}
    result = add_journal_entry(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        event_type="objective_completed",
        what_happened="The road bandit was defeated.",
        what_i_learned="The old mill route is safer now.",
        next_objective="Return to Bran.",
        turn_index=8,
        tags=["quest", "combat"],
    )

    entry = result["entry"]
    assert result["ok"] is True
    assert result["source"] == "deterministic_quest_journal_runtime"
    assert entry["source"] == "deterministic_quest_journal_runtime"
    assert entry["what_happened"] == "The road bandit was defeated."
    assert entry["what_i_learned"] == "The old mill route is safer now."
    assert entry["next_objective"] == "Return to Bran."
    assert state["journal_state"]["entries"][0]["entry_id"].startswith("journal:quest:clear_the_road:objective:defeat_bandit:8:")


def test_ci_phase3_journal_entry_rejects_empty_or_missing_quest_without_mutation():
    from copy import deepcopy

    from app.rpg.quests.journal import add_journal_entry

    state = {"player_state": {"name": "CI"}}
    before = deepcopy(state)
    missing_quest = add_journal_entry(state, quest_id="", what_happened="Something happened.")
    empty_entry = add_journal_entry(state, quest_id="quest:clear_the_road")

    assert missing_quest["ok"] is False
    assert missing_quest["reason"] == "quest_id_missing"
    assert empty_entry["ok"] is False
    assert empty_entry["reason"] == "journal_entry_empty"
    assert state == before


def test_ci_phase3_journal_entry_can_be_created_from_objective_result():
    from app.rpg.quests.journal import add_journal_entry_from_objective_result

    state, objective_result = _completed_objective_state()
    result = add_journal_entry_from_objective_result(
        state,
        objective_result,
        turn_index=8,
        what_i_learned="Bandits were blocking trade on the old road.",
    )

    entry = result["entry"]
    assert result["ok"] is True
    assert entry["quest_id"] == "quest:clear_the_road"
    assert entry["objective_id"] == "objective:defeat_bandit"
    assert entry["event_type"] == "objective_completed"
    assert "Defeat the road bandit" in entry["what_happened"]
    assert entry["next_objective"] == "Return for the quest reward or ask about the next lead."
    assert "completed" in entry["tags"]


def test_ci_phase3_journal_summary_groups_entries_by_quest_and_latest_next_objective():
    from app.rpg.quests.journal import add_journal_entry, build_quest_journal_summary

    state = {}
    add_journal_entry(state, quest_id="quest:clear_the_road", what_happened="Accepted Bran's request.", next_objective="Find the bandit.", turn_index=2)
    add_journal_entry(state, quest_id="quest:clear_the_road", what_happened="Defeated the bandit.", next_objective="Return to Bran.", turn_index=8)

    summary = build_quest_journal_summary(state)
    quest_summary = summary["quests"][0]
    assert summary["source"] == "deterministic_quest_journal_runtime"
    assert summary["entry_count"] == 2
    assert quest_summary["quest_id"] == "quest:clear_the_road"
    assert quest_summary["latest_next_objective"] == "Return to Bran."
    assert quest_summary["sources"] == ["deterministic_quest_journal_runtime"]


def test_ci_phase3_quest_journal_report_renders_entries_and_escapes_html():
    from app.rpg.quests.journal import add_journal_entry, render_quest_journal_report_html

    state = {}
    add_journal_entry(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        what_happened="Defeated <bandit> near the road.",
        what_i_learned="The old mill is connected.",
        next_objective="Return to Bran.",
        turn_index=8,
    )

    html = render_quest_journal_report_html({"simulation_state": state})
    assert "Quest Journal" in html
    assert "Deterministic journal entries" in html
    assert "quest:clear_the_road" in html
    assert "objective:defeat_bandit" in html
    assert "Defeated &lt;bandit&gt; near the road." in html
    assert "Learned: The old mill is connected." in html
    assert "Next: Return to Bran." in html
    assert "deterministic_quest_journal_runtime" in html


def test_ci_phase3_journal_helpers_are_exported():
    from app.rpg import quests

    assert quests.add_journal_entry
    assert quests.add_journal_entry_from_objective_result
    assert quests.build_quest_journal_summary
    assert quests.render_quest_journal_report_html
