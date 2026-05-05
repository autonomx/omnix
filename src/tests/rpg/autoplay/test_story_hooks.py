from tests.rpg.autoplay.seeding import seed_tavern_story_campaign
from tests.rpg.autoplay.story_hooks import (
    apply_autoplay_story_hooks,
    seed_witness_resolution_hooks,
)


def test_seed_witness_resolution_hooks_adds_hooks():
    state = {}

    result = seed_witness_resolution_hooks(state)

    assert result["ok"] is True
    assert result["hook_count"] == 5
    assert state["autoplay_story_hook_state"]["enabled"] is True


def test_ask_bran_hook_adds_journal_and_arc_stage():
    state = {}
    seed_tavern_story_campaign(state)

    result = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I ask Bran about the witness.",
        turn_index=1,
    )

    after = result["simulation_state"]
    assert result["changed"] is True
    assert result["fired_hooks"][0]["hook_id"] == "hook:witness:ask_bran"
    assert after["story_arc_state"]["arcs"]["arc:witness_search"]["stage"] == "lead_found"
    assert after["campaign_journal_state"]["entries"]
    assert after["story_event_queue_state"]["queue"]
    assert result["display"]["npc"]["speaker"] == "Bran"
    assert result["display"]["npc"]["line"]


def test_find_witness_hook_requires_prior_hook():
    state = {}
    seed_tavern_story_campaign(state)

    first = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I sit and think.",
        turn_index=1,
    )

    assert first["changed"] is False

    second = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I ask Bran about the witness.",
        turn_index=2,
    )
    third = apply_autoplay_story_hooks(
        simulation_state=second["simulation_state"],
        player_action="I walk outside and follow the cloaked traveler to find the witness.",
        turn_index=3,
    )

    after = third["simulation_state"]
    milestone = after["story_arc_milestone_state"]["arcs"]["arc:witness_search"]["milestones"][0]
    assert third["changed"] is True
    assert milestone["status"] == "completed"
    assert after["story_arc_state"]["arcs"]["arc:witness_search"]["stage"] == "witness_found"


def test_hooks_are_one_shot():
    state = {}
    seed_tavern_story_campaign(state)

    first = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I ask Bran about the witness.",
        turn_index=1,
    )
    second = apply_autoplay_story_hooks(
        simulation_state=first["simulation_state"],
        player_action="I ask Bran about the witness again.",
        turn_index=2,
    )

    assert first["changed"] is True
    assert second["changed"] is False


def test_report_to_bran_adds_next_branch_objective():
    state = {}
    seed_tavern_story_campaign(state)

    first = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I ask Bran about the witness.",
        turn_index=1,
    )
    second = apply_autoplay_story_hooks(
        simulation_state=first["simulation_state"],
        player_action="I walk outside and follow the cloaked traveler to find the witness.",
        turn_index=2,
    )
    third = apply_autoplay_story_hooks(
        simulation_state=second["simulation_state"],
        player_action="I return to Bran and talk about the witness findings.",
        turn_index=3,
    )

    after = third["simulation_state"]
    milestones = after["story_arc_milestone_state"]["arcs"]["arc:witness_search"]["milestones"]
    milestone_by_id = {row["milestone_id"]: row for row in milestones}

    assert third["changed"] is True
    assert after["story_arc_state"]["arcs"]["arc:witness_search"]["stage"] == "reported_to_bran"
    assert milestone_by_id["milestone:report_findings_to_bran"]["status"] == "completed"
    assert milestone_by_id["milestone:pursue_bandit_trail"]["status"] == "active"


def test_pursue_bandit_trail_completes_branch_objective():
    state = {}
    seed_tavern_story_campaign(state)

    state = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I ask Bran about the witness.",
        turn_index=1,
    )["simulation_state"]
    state = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I walk outside and follow the cloaked traveler to find the witness.",
        turn_index=2,
    )["simulation_state"]
    state = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I return to Bran and talk about the witness findings.",
        turn_index=3,
    )["simulation_state"]
    result = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I leave the tavern and pursue the bandit trail along the road.",
        turn_index=4,
    )

    after = result["simulation_state"]
    milestones = after["story_arc_milestone_state"]["arcs"]["arc:witness_search"]["milestones"]
    milestone_by_id = {row["milestone_id"]: row for row in milestones}

    assert result["changed"] is True
    assert after["story_arc_state"]["arcs"]["arc:witness_search"]["stage"] == "bandit_trail"
    assert milestone_by_id["milestone:pursue_bandit_trail"]["status"] == "completed"


def test_story_hooks_do_not_cascade_prerequisites_in_same_turn():
    state = {}
    seed_tavern_story_campaign(state)

    result = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I ask Bran about the witness and follow the cloaked traveler outside.",
        turn_index=1,
    )

    fired_ids = [row["hook_id"] for row in result["fired_hooks"]]

    assert fired_ids == ["hook:witness:ask_bran"]


def test_report_to_bran_matches_found_witness_language():
    state = {}
    seed_tavern_story_campaign(state)
    state = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I ask Bran about the witness.",
        turn_index=1,
    )["simulation_state"]
    state = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I follow the cloaked traveler outside to find the witness.",
        turn_index=2,
    )["simulation_state"]

    result = apply_autoplay_story_hooks(
        simulation_state=state,
        player_action="I approach Bran and state that I found the witness.",
        turn_index=3,
    )

    assert result["changed"] is True
    assert result["fired_hooks"][0]["hook_id"] == "hook:witness:report_to_bran"


def test_pursue_bandit_trail_adds_followup_preparation_objective():
    state = {}
    seed_tavern_story_campaign(state)
    for turn_index, action in enumerate(
        [
            "I ask Bran about the witness.",
            "I inspect the tavern for the witness trail.",
            "I follow the cloaked traveler outside to find the witness.",
            "I return to Bran and report the findings.",
            "I leave the tavern and pursue the bandit trail along the road.",
        ],
        start=1,
    ):
        state = apply_autoplay_story_hooks(
            simulation_state=state,
            player_action=action,
            turn_index=turn_index,
        )["simulation_state"]

    milestones = state["story_arc_milestone_state"]["arcs"]["arc:witness_search"]["milestones"]
    by_id = {row["milestone_id"]: row for row in milestones}

    assert by_id["milestone:prepare_for_bandit_road"]["status"] == "active"


def test_tavern_story_seed_gives_player_starter_inventory():
    state = {}
    seed_tavern_story_campaign(state)

    inventory = state["player_state"]["inventory"]

    assert inventory["currency"]["gold"] == 15
    assert any(item["item_id"] == "item:iron_dagger" for item in inventory["items"])
    assert state["inventory_state"]["currency"]["gold"] == 15


def test_all_campaign_seed_variants_have_director_lore_npcs_and_arc():
    from tests.rpg.autoplay.seeding import available_campaign_seeds, seed_campaign

    for seed_name in available_campaign_seeds():
        state = {}
        result = seed_campaign(state, seed_name)

        assert result["ok"] is True
        assert state["campaign_director_state"]["campaign_title"]
        assert state["lore_state"]["entries"]
        assert state["npc_profile_state"]["profiles"]
        assert state["story_arc_state"]["arcs"]
        assert state["story_arc_milestone_state"]["arcs"]
        assert state["player_state"]["inventory"]["items"]