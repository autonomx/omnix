"""The turn route returns the turn's TurnOutcome: what it changed, its narration, its timings and model calls (RQ-1.3)."""
from __future__ import annotations

import pytest

from app.apps.rpg.session.campaign_state import CURRENT_SCHEMA_VERSION
from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def _facts(document: dict) -> dict:
    from app.apps.rpg.foundation.state import CampaignStateView

    view = CampaignStateView(document)
    return {
        "purse": view.inventory.purse.total_copper if view.inventory.purse else None,
        "pack": sorted((item.item_id or item.name, item.quantity) for item in view.inventory.items),
        "ground": {place: sorted((item.item_id or item.name, item.quantity) for item in stacks)
                   for place, stacks in view.inventory.ground.items() if stacks},
        "hp": view.player.hp,
        "location": view.location.location_id,
        "present": view.npcs.present_npc_ids,
        "party": [companion.npc_id for companion in view.party.companions],
        "quests": {quest.quest_id: (quest.status, sorted(quest.visited_locations)) for quest in view.quests.quests},
        "needs": (view.survival.hunger, view.survival.thirst, view.survival.fatigue),
        "turns": view.time.turn_count,
    }


def test_each_turn_reports_its_outcome_and_the_changes_replay_its_facts(launch) -> None:
    from app.apps.rpg.foundation.state import parse_changes, reduce
    from app.apps.rpg.narration.presentation.turn_outcome import TurnOutcome
    from app.apps.rpg.narration.presentation.turn_response import RpgTurnResponse

    play = launch("aurelia")
    expected = {
        "look around": {"turn_counted"},
        "I ask Liora Fen to join my party as a companion.": {"companion_joined", "turn_counted"},
        "go to Starfall Village": {"location_changed", "presence_changed", "quest_place_reached"},
        "I buy a Healing Potion from Brindle Gearwing.": {"purse_changed", "item_added"},
        "I drop one Lantern Bread on the ground.": {"item_dropped"},
        "I pick up the Lantern Bread.": {"item_picked_up"},
        "I attack the Echo Wolf.": {"combat_started", "hp_changed"},
        "I flee from the Echo Wolf.": {"combat_ended"},
        "I ask Orik Stonewake what he thinks of the newcomers.": {"turn_counted"},
    }
    for command, kinds in expected.items():
        before = play.stored()
        calls = len(play.model.calls)
        body = play.turn(command)
        RpgTurnResponse.model_validate(body)
        outcome = TurnOutcome.model_validate(body["outcome"])
        types = {change.type for change in outcome.applied_changes}
        assert kinds <= types, (command, types)
        assert outcome.kind == "player_text" and outcome.document_version == CURRENT_SCHEMA_VERSION
        assert outcome.revision == play.revision()
        # Every model call the turn made is counted, by kind.
        assert outcome.model_calls.total == len(play.model.calls) - calls, (command, outcome.model_calls)
        assert "pipeline_before_encode_ms" in outcome.timings
        assert set(outcome.presentation.changed_sections) <= set(body["state"]["changed_domains"])
        assert body["state"]["changed"] is True  # every turn counts, so every turn changes the campaign
        # Reducing the reported changes onto the document before gives the facts the turn committed.
        replayed, _ = reduce(before, parse_changes([change.model_dump() for change in outcome.applied_changes]))
        assert _facts(replayed) == _facts(play.stored()), command

    dialogue = play.turn("I ask Orik Stonewake what he thinks of the newcomers.")
    outcome = TurnOutcome.model_validate(dialogue["outcome"])
    assert outcome.model_calls.by_kind == {"provider": 1}  # one short call writes the line
    assert "npc:orik-stonewake" in outcome.narration.speaker_ids
    look = TurnOutcome.model_validate(play.turn("look around")["outcome"])
    assert look.model_calls.by_kind == {"narrative_writer": 1} and look.narration.response_id


@pytest.mark.parametrize("world", ["starter", "vesper"])
def test_the_outcome_is_reported_in_every_world(launch, world) -> None:
    from app.apps.rpg.narration.presentation.turn_outcome import TurnOutcome

    play = launch(world)
    outcome = TurnOutcome.model_validate(play.turn("Practice swordsmanship with a careful training drill.")["outcome"])
    progressed = [change for change in outcome.applied_changes if change.type == "skill_progressed"]
    assert [(change.skill_id, change.xp) for change in progressed] == [("swordsmanship", 10)]


@pytest.mark.parametrize("world", ["aurelia", "starter", "vesper"])
def test_look_and_wait_run_on_the_turn_pipeline(launch, world, monkeypatch) -> None:
    """RQ-1.4: look and wait are planned, resolved to changes, reduced and ticked on the pipeline; the changes the
    turn reports are all it changed in the campaign's facts, and the world's causal clock ticks with them."""
    from app.apps.rpg.foundation.state import parse_changes, reduce
    from app.apps.rpg.narration.presentation.turn_outcome import TurnOutcome

    play = launch(world)
    for command in ("look around", "wait", "where am I?"):
        before = play.stored()
        outcome = TurnOutcome.model_validate(play.turn(command)["outcome"])
        types = [change.type for change in outcome.applied_changes]
        assert outcome.planned_action == ("wait" if command == "wait" else "look"), (command, outcome)
        placed = [kind for kind in types if kind != "location_changed"]  # the starter town places the hero first
        assert placed[:2] == ["turn_counted", "time_advanced"] and types[-1] == "journal_written", types
        assert "world_ticked" in types, types  # the clock moves with the turn's minutes
        replayed, _ = reduce(before, parse_changes([change.model_dump() for change in outcome.applied_changes]))
        after = play.stored()
        assert _facts(replayed) == _facts(after), command
        [ticked] = [change for change in outcome.applied_changes if change.type == "world_ticked"]
        assert not ticked.simulation  # the outcome names what the tick replaced; the turn's patch carries it
        assert "environment" in ticked.summary["sections"]
        assert ("causal_world_runtime" in ticked.summary["sections"]) == (world in {"aurelia", "starter"})  # pressures
        assert replayed["runtime_state"]["player_journal"] == after["runtime_state"]["player_journal"]

    monkeypatch.setenv("OMNIX_RPG_TURN_PIPELINE_OFF", "look")  # kept off, look takes the older path
    outcome = TurnOutcome.model_validate(play.turn("look around")["outcome"])
    assert outcome.planned_action is None


def test_the_campaign_reaches_the_browser_without_the_worlds_secrets(launch) -> None:
    """A person's secrets, the campaign bible and the world model stay on the server (RQ-2.2, RQ-8)."""
    play = launch("aurelia")
    play.turn("look around")
    stored = play.stored()
    liora = stored["simulation_state"]["world_model"]["npcs"]["npc:liora-fen"]
    assert liora["secrets"] and liora["speech_style"]  # dialogue has them
    shown = play.client.get(f"/api/rpg/sessions/{play.session_id}").json()["session"]
    text = str(shown)
    assert all(secret not in text for secret in liora["secrets"])
    assert "world_model" not in shown["simulation_state"] and "campaign_bible" not in shown["state"]
    assert "setup_payload" not in shown and shown["simulation_state"]["player_state"]
