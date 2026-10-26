"""The turn pipeline's steps for look and wait (RQ-1.4): plan, resolve, world tick, and the reducer."""
from __future__ import annotations

import pytest

from app.apps.rpg.foundation.state.changes import WorldTicked
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.intent.grammar import IntentCandidate
from app.apps.rpg.session.turn import PlannedAction, TurnRequest, plan_action, run_planned_turn
from app.apps.rpg.session.turn.resolution import resolve_turn
from app.apps.rpg.session.turn.resolvers import outcome_lines, resolve
from app.apps.rpg.session.turn.world_tick import world_tick


def _run(campaign, text, reading):
    planned = plan_action(reading)
    return run_planned_turn(campaign, request=TurnRequest(kind="player_text", session_id="rpg_test", text=text),
                            planned=planned, reading=reading, resolution=resolve_turn(planned, campaign, text))


def _campaign(**simulation):
    """A campaign as its creation leaves it: with the world map it opens on (``projected_map_state``)."""
    from app.apps.rpg.world.map_world_integration import projected_map_state

    campaign = {
        "manifest": {"session_id": "rpg_test", "turn_count": 3},
        "state": {"turn_count": 3, "current_location_name": "Gate"},
        "runtime_state": {"tick": 5},
        "simulation_state": {
            "tick": 5,
            "player_state": {"location_id": "loc:gate"},
            "survival": {"enabled": True, "hunger": 10, "thirst": 99, "fatigue": 0},
            "world_model": {"locations": {"loc:gate": {"name": "The Gate", "exits": {"north": "loc:inn"}},
                                          "loc:inn": {"name": "The Inn"}},
                            "npcs": {"npc:wren": {"name": "Wren"}}},
            "present_npc_state": {"present_npc_ids": ["npc:wren"]},
            **simulation,
        },
    }
    projected = projected_map_state(campaign)
    return reduce(campaign, [projected])[0] if projected is not None else campaign


@pytest.mark.parametrize(("reading", "planned"), [
    (IntentCandidate("look", confidence=0.9, reason="looks"), "look"),
    (IntentCandidate("wait", confidence=0.9, reason="waits"), "wait"),
    (IntentCandidate("look", confidence=0.5), None),  # not confident: the older path decides
    (IntentCandidate("wait", confidence=0.9, clauses=("wait", "look")), None),  # two steps
    (IntentCandidate("buy", target_id="offer:bread", target_kind="offer", confidence=0.9), "trade"),
    (IntentCandidate("sell", target_id="item:dagger", target_kind="item", confidence=0.9), "trade"),
    (IntentCandidate("give", target_id="item:dagger", target_kind="item", confidence=0.9), "give"),
    (IntentCandidate("give", confidence=0.5), None),  # nothing named to give: the intent call reads it
])
def test_only_confident_single_step_look_and_wait_are_planned(reading, planned) -> None:
    plan = plan_action(reading)
    assert (plan.mechanic if plan else None) == planned


def test_look_counts_the_turn_and_passes_a_tick_and_states_what_is_seen() -> None:
    campaign = _campaign()
    changes = resolve(PlannedAction(mechanic="look"), campaign)
    assert [change.type for change in changes] == ["turn_counted", "time_advanced"]
    assert changes[0].turn_count == 4
    assert outcome_lines(PlannedAction(mechanic="look"), campaign) == [
        "You look around The Gate.", "Here: Wren.", "Paths lead to The Inn."]


def test_a_hero_with_no_place_is_placed_where_the_world_begins() -> None:
    campaign = _campaign(player_state={}, world_model={"start_location_id": "loc:gate"})
    assert [change.type for change in resolve(PlannedAction(mechanic="wait"), campaign)][1] == "location_changed"


def test_needs_rise_once_a_turn_and_stop_at_their_ceiling() -> None:
    changes, receipt, _ = world_tick(_campaign(), needs="wait", minutes=0, turn_key="turn:6")
    [needs] = changes
    assert (needs.hunger, needs.thirst, needs.fatigue) == (1, 1, 1) and receipt == {}  # thirst stops at 100
    assert world_tick(_campaign(survival={"enabled": False}), needs="wait", minutes=0, turn_key="t")[0] == []
    assert world_tick(_campaign(), needs=None, minutes=0, turn_key="t")[0] == []  # time away


def test_the_one_clock_moves_by_the_turns_minutes_and_the_play_screen_shows_it() -> None:
    campaign = _campaign()
    campaign["state"]["world"] = {"environment": {"absolute_minutes": 9 * 60 + 50, "active_events": []}}
    changes, _, _ = world_tick(campaign, needs="wait", minutes=30, turn_key="turn:6")
    document, _ = reduce(campaign, changes)
    assert document["simulation_state"]["environment"]["absolute_minutes"] == 10 * 60 + 20
    assert document["state"]["world"]["environment"]["absolute_minutes"] == 10 * 60 + 20
    assert document["state"]["world"]["time"].endswith("10:20") and document["state"]["world"]["time"].startswith("Day 1")


def test_the_world_tick_may_replace_only_the_sections_it_owns() -> None:
    with pytest.raises(ValueError, match="does not own"):
        WorldTicked(simulation={"player_state": {}})
    document, _ = reduce(_campaign(), [WorldTicked(simulation={"economy_state": {"prices": 2}},
                                                   runtime={"causal_last_applied_tick": 6})])
    assert document["simulation_state"]["economy_state"] == {"prices": 2}
    assert document["runtime_state"]["causal_last_applied_tick"] == 6


def test_a_planned_turn_is_its_changes_reduced_onto_the_turn_start_campaign() -> None:
    campaign = _campaign()
    reading = IntentCandidate("wait", confidence=0.9, reason="waits")
    result = _run(campaign, "wait", reading)
    assert campaign["simulation_state"]["tick"] == 5  # the turn-start campaign is not touched
    document = result["session"]
    assert document["simulation_state"]["tick"] == 8 and document["state"]["turn_count"] == 4  # a while: 3 ticks
    assert document["simulation_state"]["survival"]["hunger"] == 11
    assert document["simulation_state"]["environment"]["absolute_minutes"] == 9 * 60 + 30
    assert [change["type"] for change in result["turn_pipeline"]["changes"]] == [
        "turn_counted", "time_advanced", "needs_changed", "whereabouts_changed", "world_ticked", "journal_written"]
    assert document["simulation_state"]["npc_index"]["npc:wren"]["location_id"] == "loc:gate"  # in the scene: here
    assert result["resolved_result"]["outcome_lines"] == ["You wait a while in The Gate; time passes.", "Around you: Wren."]
    assert document["runtime_state"]["player_journal"]["entries"]


def test_an_unclear_command_is_planned_as_the_games_question_and_a_bare_attack_in_a_fight_strikes() -> None:
    from app.apps.rpg.rules.intent.grammar import SceneView, parse_command

    unclear = parse_command("I talk to him.", SceneView(()))
    plan = plan_action(unclear)
    assert (plan.mechanic, plan.question, plan.ticks) == ("clarify", "Who are you speaking to?", 0)
    no_target = IntentCandidate("clarify", confidence=0.9, reason="attack_without_target")
    assert plan_action(no_target).mechanic == "clarify"
    assert (plan_action(no_target, fighting=True).mechanic, plan_action(no_target, fighting=True).reason) == (
        "fight", "attack")  # the foe in front of the hero (combat.md)


def test_a_question_back_is_a_counted_turn_in_which_no_time_passes() -> None:
    from app.apps.rpg.rules.intent.grammar import SceneView, parse_command

    campaign = _campaign()
    reading = parse_command("I talk to him.", SceneView(()))
    result = _run(campaign, "I talk to him.", reading)
    assert [change["type"] for change in result["turn_pipeline"]["changes"]] == ["turn_counted"]
    assert result["clarification"] == "Who are you speaking to?"
    canonical = result["canonical_narrative_response"]
    assert [block["text"] for block in canonical["blocks"]] == ["Who are you speaking to?"]
    assert result["session"]["simulation_state"]["tick"] == 5


def test_word_of_a_pressure_turning_reaches_the_hero() -> None:
    """RQ-4.4: the world's turns of fortune are told, the hero's region first, at most two a turn."""
    from app.apps.rpg.world.causal_runtime import bootstrap_causal_runtime

    def pressure(pressure_id: str, region: str, severity: float) -> dict:
        return {"pressure_id": pressure_id, "name": f"Danger in {region}", "severity": severity, "trend": "escalating",
                "escalation_threshold": 75.0, "resolution_threshold": 15.0,
                "next_tick_delta": {"target_id": region, "dimension": "trade_access", "operation": "decrease", "value": 1.0},
                "levers": []}

    runtime = bootstrap_causal_runtime({
        "present_day_state": {"state": {"region:a": {"trade_access": 30}, "region:b": {"trade_access": 30},
                                        "region:c": {"trade_access": 30}}},
        "pressure_plan": {"pressures": [pressure("pressure:b", "region:b", 74), pressure("pressure:a", "region:a", 74),
                                        pressure("pressure:c", "region:c", 74)]}})
    campaign = {"manifest": {}, "state": {"turn_count": 3}, "runtime_state": {}, "simulation_state": {
        "causal_world_runtime": runtime, "world_model": {"locations": {"loc:here": {"region_id": "region:a"}}},
        "player_state": {"location_id": "loc:here"}}}
    _, _, seen = world_tick(campaign, needs=None, minutes=10, turn_key="turn:4")
    assert seen == []  # 09:00 to 09:10: no hour crossed, so the pressures did not move
    changes, receipt, seen = world_tick(campaign, needs=None, minutes=3 * 60, turn_key="turn:4")
    # The hero's region first, at most two: it grew worse, and the world held it in check the next hour (Q-10); the
    # word is where it ended, not both. Then the next of the others.
    assert seen == ["Word comes: Danger in region:a is held in check.", "Word comes: Danger in region:b is held in check."]
    [ticked] = [change for change in changes if change.type == "world_ticked"]
    assert ticked.simulation["causal_world_runtime"]["last_tick"] == 3  # three hours: three moves


def test_a_close_look_tells_what_the_world_says_of_the_thing() -> None:
    from app.apps.rpg.session.turn.planning import PlannedAction
    from app.apps.rpg.session.turn.resolvers import outcome_lines

    document = {"simulation_state": {
        "world_model": {"npcs": {"npc:liora": {"name": "Liora Fen", "role": "guide", "description": "A foxkin warden."}},
                        "locations": {"loc:grove": {"name": "The Grove"}}},
        "player_state": {"location_id": "loc:grove", "inventory_state": {"items": [
            {"item_id": "iron_dagger", "name": "Iron Dagger", "description": "Nicked, but sharp."}]}}}}
    assert outcome_lines(PlannedAction(mechanic="look", target_id="npc:liora"), document) == [
        "You look closely at Liora Fen, the guide: A foxkin warden."]
    assert outcome_lines(PlannedAction(mechanic="look", target_id="iron_dagger"), document) == [
        "You look over your Iron Dagger: Nicked, but sharp."]
