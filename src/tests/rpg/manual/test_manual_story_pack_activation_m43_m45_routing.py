from tests.rpg.manual.scenarios.registry import build_service_scenarios


def _m13_m15_story_pack_filter(check):
    check_type = str(check.get("type") or "")
    return check_type.startswith("story_pack") and not check_type.startswith("story_pack_activation")


def _m43_m45_story_pack_activation_filter(check):
    return str(check.get("type") or "").startswith("story_pack_activation")


def test_story_pack_activation_checks_are_not_m13_m15_story_pack_checks():
    scenario = build_service_scenarios()["story_pack_activation_enables_director_rules"]
    checks = scenario["checks"]

    m13_checks = [check for check in checks if isinstance(check, dict) and _m13_m15_story_pack_filter(check)]
    m43_checks = [check for check in checks if isinstance(check, dict) and _m43_m45_story_pack_activation_filter(check)]

    assert m43_checks
    assert m13_checks == []


def test_story_pack_activation_scenarios_have_only_m43_story_pack_activation_checks():
    scenarios = build_service_scenarios()
    names = [
        "story_pack_imported_pack_starts_inactive",
        "story_pack_activation_enables_director_rules",
        "story_pack_activation_director_applies_active_pack_event",
        "story_pack_deactivation_disables_director_rules",
        "story_pack_activation_missing_pack_rejected",
        "story_authoring_approval_import_without_auto_activate_stays_inactive",
        "story_authoring_approval_auto_activate_bridges_to_director",
        "story_pack_activation_snapshot_is_bounded",
    ]

    for name in names:
        checks = scenarios[name]["checks"]
        bad = [
            check
            for check in checks
            if isinstance(check, dict)
            and str(check.get("type") or "").startswith("story_pack")
            and not str(check.get("type") or "").startswith("story_pack_activation")
        ]
        assert bad == [], f"{name} has checks that would route to M13-M15: {bad}"