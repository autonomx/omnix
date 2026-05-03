from tests.rpg.manual.scenarios.registry import build_service_scenarios


def test_story_event_queue_checks_are_not_m4_m6_story_event_checks():
    scenario = build_service_scenarios()["story_event_queue_enqueues_without_applying"]
    checks = scenario["checks"]

    m4_m6_checks = [
        check
        for check in checks
        if (
            isinstance(check, dict)
            and str(check.get("type") or "").startswith("story_event_")
            and not str(check.get("type") or "").startswith("story_event_queue_")
        )
    ]
    queue_checks = [
        check
        for check in checks
        if isinstance(check, dict)
        and str(check.get("type") or "").startswith("story_event_queue_")
    ]

    assert queue_checks
    assert m4_m6_checks == []