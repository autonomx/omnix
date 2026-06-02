def _accepted_state():
    from app.rpg.quests.givers import accept_quest_offer

    state = {}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=2)
    return state


def test_ci_phase3_objective_starts_open_with_zero_progress_from_template():
    from app.rpg.quests.objectives import create_objective
    from app.rpg.quests.state import start_quest

    state = {}
    start_quest(state, "quest:test", title="Test Quest", turn_index=1)
    result = create_objective(
        state,
        quest_id="quest:test",
        objective_template={
            "objective_id": "objective:collect_herbs",
            "description": "Collect two herbs.",
            "type": "collect",
            "target_ids": ["item:herb"],
            "required": 2,
        },
    )

    objective = result["objective"]
    assert result["ok"] is True
    assert result["source"] == "deterministic_quest_objective_lifecycle"
    assert objective["status"] == "open"
    assert objective["progress"] == 0
    assert objective["required"] == 2
    assert objective["event_ids"] == []


def test_ci_phase3_objective_progress_updates_deterministically():
    from app.rpg.quests.objectives import update_objective_progress

    state = _accepted_state()
    result = update_objective_progress(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        event_id="combat:defeat:bandit_1",
        amount=1,
        turn_index=4,
    )

    objective = result["objective"]
    assert result["ok"] is True
    assert result["reason"] == "objective_completed"
    assert objective["progress"] == 1
    assert objective["status"] == "completed"
    assert objective["completed_turn"] == 4
    assert result["quest"]["status"] == "completed"
    assert result["source"] == "deterministic_quest_objective_lifecycle"


def test_ci_phase3_objective_duplicate_event_does_not_overcount():
    from app.rpg.quests.objectives import create_objective, update_objective_progress
    from app.rpg.quests.state import start_quest

    state = {}
    start_quest(state, "quest:test", title="Test Quest", turn_index=1)
    create_objective(
        state,
        quest_id="quest:test",
        objective_template={"objective_id": "objective:collect_herbs", "required": 2},
    )

    first = update_objective_progress(
        state,
        quest_id="quest:test",
        objective_id="objective:collect_herbs",
        event_id="pickup:herb:1",
        amount=1,
        turn_index=3,
    )
    duplicate = update_objective_progress(
        state,
        quest_id="quest:test",
        objective_id="objective:collect_herbs",
        event_id="pickup:herb:1",
        amount=1,
        turn_index=4,
    )

    assert first["objective"]["progress"] == 1
    assert first["objective"]["status"] == "open"
    assert duplicate["reason"] == "duplicate_event_ignored"
    assert duplicate["objective"]["progress"] == 1
    assert duplicate["objective"]["status"] == "open"


def test_ci_phase3_quest_completes_when_all_required_objectives_complete():
    from app.rpg.quests.objectives import complete_objective_lifecycle

    state = _accepted_state()
    result = complete_objective_lifecycle(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        turn_index=8,
    )

    assert result["ok"] is True
    assert result["reason"] == "objective_completed"
    assert result["quest"]["status"] == "completed"
    assert result["quest"]["stage"] == "completed"
    assert result["quest"]["completed_turn"] == 8


def test_ci_phase3_objective_failure_records_reason_source_and_fails_quest():
    from app.rpg.quests.objectives import fail_objective

    state = _accepted_state()
    result = fail_objective(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        reason="bandit_escaped",
        turn_index=5,
    )

    objective = result["objective"]
    assert result["ok"] is True
    assert result["reason"] == "objective_failed"
    assert result["source"] == "deterministic_quest_objective_lifecycle"
    assert objective["status"] == "failed"
    assert objective["failure_reason"] == "bandit_escaped"
    assert objective["failed_turn"] == 5
    assert result["quest"]["status"] == "failed"
    assert result["quest"]["metadata"]["failure_reason"] == "bandit_escaped"


def test_ci_phase3_missing_quest_or_objective_rejects_without_mutation():
    from copy import deepcopy

    from app.rpg.quests.objectives import fail_objective, update_objective_progress

    missing_quest_state = {}
    missing_quest = update_objective_progress(
        missing_quest_state,
        quest_id="quest:missing",
        objective_id="objective:missing",
        event_id="event:1",
    )

    state = _accepted_state()
    before = deepcopy(state)
    missing_objective = fail_objective(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:missing",
        reason="not_found",
    )

    assert missing_quest["ok"] is False
    assert missing_quest["reason"] == "quest_missing"
    assert missing_quest["source"] == "deterministic_quest_objective_lifecycle"
    assert missing_quest_state == {}
    assert missing_objective["ok"] is False
    assert missing_objective["reason"] == "objective_missing"
    assert missing_objective["source"] == "deterministic_quest_objective_lifecycle"
    assert state == before


def test_ci_phase3_lifecycle_responses_include_source_fields():
    from app.rpg.quests.objectives import derive_quest_lifecycle, update_objective_progress

    state = _accepted_state()
    progress = update_objective_progress(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        event_id="combat:defeat:bandit_1",
        amount=1,
    )
    lifecycle = derive_quest_lifecycle(state, quest_id="quest:clear_the_road")

    assert progress["source"] == "deterministic_quest_objective_lifecycle"
    assert progress["objective"]["source"] == "deterministic_quest_objective_lifecycle"
    assert lifecycle["source"] == "deterministic_quest_objective_lifecycle"
