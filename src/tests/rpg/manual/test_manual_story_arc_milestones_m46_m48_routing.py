from tests.rpg.manual.scenarios.registry import build_service_scenarios


def _m1_m3_story_filter(check):
    check_type = str(check.get("type") or "")
    if check_type.startswith("story_arc_milestone"):
        return False
    if check_type.startswith("story_objective"):
        return False
    if check_type == "story_event_apply_for_milestone":
        return False
    return check_type.startswith("lore_") or check_type.startswith("story_arc")


def _m46_m48_milestone_filter(check):
    check_type = str(check.get("type") or "")
    return (
        check_type.startswith("story_arc_milestone")
        or check_type.startswith("story_objective")
        or check_type == "story_event_apply_for_milestone"
        or check_type == "campaign_journal_objective_contains"
        or check_type == "campaign_recap_objective"
    )


def test_story_arc_milestone_checks_are_not_m1_m3_story_checks():
    scenario = build_service_scenarios()["story_arc_milestone_adds_active_objective"]
    checks = scenario["checks"]

    m1_checks = [check for check in checks if isinstance(check, dict) and _m1_m3_story_filter(check)]
    m46_checks = [check for check in checks if isinstance(check, dict) and _m46_m48_milestone_filter(check)]

    assert m46_checks
    assert m1_checks == []


def test_m46_m48_scenarios_do_not_route_to_m1_m3_story_checker():
    scenarios = build_service_scenarios()
    names = [
        "story_arc_milestone_adds_active_objective",
        "story_arc_milestone_completion_is_idempotent",
        "story_event_adds_milestone_objective",
        "story_event_completes_milestone_and_records_journal",
        "campaign_recap_includes_active_story_objectives",
        "story_arc_milestone_missing_arc_rejected",
        "story_arc_milestone_missing_complete_rejected",
        "story_arc_milestone_state_is_bounded",
    ]

    for name in names:
        checks = scenarios[name]["checks"]
        bad = [check for check in checks if isinstance(check, dict) and _m1_m3_story_filter(check)]
        assert bad == [], f"{name} has checks that would route to M1-M3: {bad}"