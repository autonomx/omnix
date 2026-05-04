from tests.rpg.manual.scenarios.registry import build_service_scenarios


def _m4_m6_story_event_filter(check):
    check_type = str(check.get("type") or "")
    if check_type == "story_event_apply_for_milestone":
        return False
    return check_type.startswith("story_event_") and not check_type.startswith("story_event_queue_")


def _m31_m33_campaign_journal_filter(check):
    check_type = str(check.get("type") or "")
    if check_type == "campaign_journal_objective_contains":
        return False
    return (
        check_type.startswith("campaign_journal")
        or check_type.startswith("campaign_story_recap")
    )


def _m46_m48_milestone_filter(check):
    check_type = str(check.get("type") or "")
    return (
        check_type.startswith("story_arc_milestone")
        or check_type.startswith("story_objective")
        or check_type == "story_event_apply_for_milestone"
        or check_type == "campaign_journal_objective_contains"
        or check_type == "campaign_recap_objective"
    )


def test_story_event_apply_for_milestone_does_not_route_to_m4_m6():
    scenario = build_service_scenarios()["story_event_adds_milestone_objective"]
    checks = scenario["checks"]

    m46_checks = [check for check in checks if isinstance(check, dict) and _m46_m48_milestone_filter(check)]
    m4_checks = [check for check in checks if isinstance(check, dict) and _m4_m6_story_event_filter(check)]

    assert any(check.get("type") == "story_event_apply_for_milestone" for check in m46_checks)
    assert m4_checks == []


def test_campaign_journal_objective_contains_does_not_route_to_m31_m33():
    scenario = build_service_scenarios()["story_event_completes_milestone_and_records_journal"]
    checks = scenario["checks"]

    m46_checks = [check for check in checks if isinstance(check, dict) and _m46_m48_milestone_filter(check)]
    m31_checks = [check for check in checks if isinstance(check, dict) and _m31_m33_campaign_journal_filter(check)]

    assert any(check.get("type") == "campaign_journal_objective_contains" for check in m46_checks)
    assert m31_checks == []


def test_all_m46_m48_scenarios_do_not_route_to_older_m4_or_m31_checkers():
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
        bad_m4 = [check for check in checks if isinstance(check, dict) and _m4_m6_story_event_filter(check)]
        bad_m31 = [check for check in checks if isinstance(check, dict) and _m31_m33_campaign_journal_filter(check)]
        assert bad_m4 == [], f"{name} has checks that would route to M4-M6: {bad_m4}"
        assert bad_m31 == [], f"{name} has checks that would route to M31-M33: {bad_m31}"