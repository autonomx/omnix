from app.rpg.mechanics.mechanics_opportunities import (
    describe_mechanic_opportunity_state,
    list_available_mechanic_opportunities,
    match_mechanic_opportunity,
)


def test_old_mill_lists_combat_opportunity_alias():
    opportunities = list_available_mechanic_opportunities(
        state={"current_location": "location:old_mill"},
        scenario_state={},
        missing_mechanics=["combat_started"],
    )

    assert any(item["mechanic"] == "combat_started" for item in opportunities)


def test_wagon_yard_lists_combat_opportunity_alias():
    opportunities = list_available_mechanic_opportunities(
        state={"current_location": "location:wagon_yard"},
        scenario_state={},
        missing_mechanics=["combat_started"],
    )

    assert any(item["mechanic"] == "combat_started" for item in opportunities)


def test_describe_mechanic_opportunity_state_reports_current_location():
    diagnostics = describe_mechanic_opportunity_state(
        state={"current_location": "location:old_mill"},
        scenario_state={},
        missing_mechanics=["combat_started"],
    )

    assert diagnostics["current_location"] == "location:old_mill"
    assert diagnostics["opportunity_count_for_current_location"] >= 1


def test_mechanic_match_does_not_resolve_unrelated_dialogue_to_travel():
    match = match_mechanic_opportunity(
        player_input="I ask Bran for a room, but I also ask why the tavern feels tense.",
        state={"current_location": "scene:rusty_flagon"},
        scenario_state={},
    )

    assert match["ok"] is False


def test_mechanic_match_does_not_resolve_unrelated_dialogue_to_combat():
    match = match_mechanic_opportunity(
        player_input="I ask Bran what direction the cloaked traveler went after leaving.",
        state={
            "current_location": "location:old_mill",
            "flags": {"encounter:mill_bandit_scouts.started": True},
        },
        scenario_state={},
    )

    assert match["ok"] is False


def test_mechanic_match_resolves_buy_rations():
    match = match_mechanic_opportunity(
        player_input="I buy two rations from Bran.",
        state={"current_location": "scene:rusty_flagon"},
        scenario_state={},
    )

    assert match["ok"] is True
    assert match["opportunity"]["mechanic"] == "buying"


def test_mechanic_match_resolves_lodging_payment():
    match = match_mechanic_opportunity(
        player_input="I pay Bran 5 silver for a common room.",
        state={"current_location": "scene:rusty_flagon"},
        scenario_state={},
    )

    assert match["ok"] is True
    assert match["opportunity"]["mechanic"] == "service_or_lodging"


def test_mechanic_match_resolves_bandit_combat_only_with_target():
    match = match_mechanic_opportunity(
        player_input="I confront the bandit scouts at the old mill.",
        state={"current_location": "location:old_mill"},
        scenario_state={},
    )

    assert match["ok"] is True
    assert match["opportunity"]["mechanic"] == "combat_started"


def test_combat_match_does_not_start_from_scouting_ambush_signs():
    match = match_mechanic_opportunity(
        player_input="I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        state={"current_location": "location:old_mill"},
        scenario_state={},
    )

    assert match["ok"] is False


def test_service_forced_command_matches_common_room():
    match = match_mechanic_opportunity(
        player_input="I pay Bran 5 silver for a common room.",
        state={"current_location": "scene:rusty_flagon"},
        scenario_state={},
    )

    assert match["ok"] is True
    assert match["opportunity"]["mechanic"] == "service_or_lodging"


def test_buy_forced_command_matches_rations():
    match = match_mechanic_opportunity(
        player_input="I buy two rations from Bran.",
        state={"current_location": "scene:rusty_flagon"},
        scenario_state={},
    )

    assert match["ok"] is True
    assert match["opportunity"]["mechanic"] == "buying"


def test_combat_resolve_forced_command_matches_after_started_flag():
    match = match_mechanic_opportunity(
        player_input="I press the attack until the bandit scouts are defeated.",
        state={
            "current_location": "location:old_mill",
            "flags": {"encounter:mill_bandit_scouts.started": True},
        },
        scenario_state={},
    )

    assert match["ok"] is True
    assert match["opportunity"]["mechanic"] == "combat_resolved"