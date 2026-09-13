from app.rpg.session.item_endurance_scenarios import build_item_endurance_plan, summarize_item_endurance_progress


def test_build_item_endurance_plan_covers_100_turn_targets() -> None:
    plan = build_item_endurance_plan(total_turns=100)

    assert plan["total_turns"] == 100
    assert plan["summary"] == {"milestone_count": 10, "first_turn": 5, "final_turn": 100}
    assert plan["coverage_targets"] == [
        "combat",
        "crafting",
        "diagnostics",
        "maintenance",
        "merchant",
        "modification",
        "pickup",
        "recipe_discovery",
        "report",
        "use_effect",
    ]
    assert plan["milestones"][0]["payload"] == {"action": "item_diagnostics", "record": True}
    assert plan["milestones"][-1]["payload"]["action"] == "item_scenario"


def test_build_item_endurance_plan_short_run_adds_final_report() -> None:
    plan = build_item_endurance_plan(total_turns=12)

    assert [milestone["turn"] for milestone in plan["milestones"]] == [5, 10, 12]
    assert plan["milestones"][-1]["coverage_target"] == "report"


def test_summarize_item_endurance_progress_scores_observed_targets() -> None:
    plan = build_item_endurance_plan(total_turns=20)
    progress = summarize_item_endurance_progress(
        plan,
        [
            {"coverage_target": "diagnostics"},
            {"kind": "pickup"},
            {"action": "use_effect"},
        ],
    )

    assert progress["ok"] is False
    assert progress["coverage_score"] == 0.75
    assert progress["covered_targets"] == ["diagnostics", "pickup", "use_effect"]
    assert progress["missing_targets"] == ["recipe_discovery"]


def test_summarize_item_endurance_progress_is_ok_when_all_targets_observed() -> None:
    plan = build_item_endurance_plan(total_turns=10)
    progress = summarize_item_endurance_progress(
        plan,
        [{"coverage_target": "diagnostics"}, {"coverage_target": "pickup"}, {"coverage_target": "report"}],
    )

    assert progress["ok"] is True
    assert progress["coverage_score"] == 1.0
    assert progress["missing_targets"] == []
