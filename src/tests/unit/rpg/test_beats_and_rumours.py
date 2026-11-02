"""People who act on their goals, and the word that goes about (evolution roadmap EV-4): beats reached on the days
the clock crosses, seeded and bounded; what a beat sets, where it takes its person, and the rumour it sends about;
the hero hearing it by asking for news, by paying for it, or by being there; the game master's beats and rumours;
and the version that brings the state in."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.consequences import consequences
from app.apps.rpg.rules.dialogue.plan import build_plan, plan_changes, speaker_topics
from app.apps.rpg.rules.economy.trade import buy
from app.apps.rpg.rules.rumours import NEWS, fold_rumour, news_here, rumours, spread
from app.apps.rpg.session.campaign_state import upcast_campaign_document

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
GROVE, VILLAGE, GUILD = "location:aurelia:arrival-grove", "location:aurelia:starfall-village", "location:aurelia:wayfarer-guild"
RHEA, LIORA, MIRI = "npc:captain-rhea-sunward", "npc:liora-fen", "npc:miri-kestrel"
DAY = 24 * 60


def _beats() -> list[dict]:
    return [
        {"npc_id": RHEA, "goals": [{"goal_id": "traitor", "summary": "expose a traitor in the guard", "beats": [
            {"id": "suspects", "chance": 1.0, "told_at": [VILLAGE, GROVE], "rumour": "The captain doubts the watch.",
             "sets": [{"fact": "rhea_doubts", "value": True}]},
            {"id": "names", "chance": 1.0, "when": {"rhea_doubts": True}, "told_at": [VILLAGE],
             "rumour": "The captain named the guardsman.", "sets": [{"fact": "guardsman_named", "value": True}]},
            {"id": "flees", "chance": 1.0, "when": {"guardsman_named": True}, "after_day": 4,
             "move": {"location": "location:aurelia:cinderhold", "activity": "riding hard"}},
        ]}]},
        {"npc_id": LIORA, "goals": [{"goal_id": "lanterns", "summary": "keep new arrivals alive", "beats": [
            {"id": "lantern-path", "chance": 1.0, "told_at": [GROVE], "rumour": "Blue lanterns mark the grove path."},
        ]}]},
    ]


def _document(world_routines: list[dict] | None = None) -> dict:
    document = upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))
    document["simulation_state"]["world_model"]["routines"] = _beats() if world_routines is None else world_routines
    return document


def _tick(document: dict, days: int = 1) -> tuple[dict, list, list[str]]:
    simulation = document["simulation_state"]
    now = int(simulation["environment"]["absolute_minutes"])
    made, lines = routines.daily_beats(simulation, before=now, after=now + days * DAY)
    after, _ = reduce(document, [*made, c.WorldTicked(simulation={"environment": {
        **simulation["environment"], "absolute_minutes": now + days * DAY}})])
    return after, made, lines


def test_a_new_day_brings_each_goals_next_ready_beat_once_and_the_roll_is_the_campaigns() -> None:
    document, made, lines = _tick(_document())
    reached = [(change.person_id, change.beat) for change in made if isinstance(change, c.BeatAdvanced)]
    assert reached == [(RHEA, "suspects"), (LIORA, "lantern-path")]  # one beat a goal a day, in order
    assert routines.reached(document["simulation_state"], RHEA, "traitor") == ["suspects"]
    # The hero stands in the grove, where both are told: they hear them as they happen.
    assert lines == ["The captain doubts the watch.", "Blue lanterns mark the grove path."]
    assert document["simulation_state"]["world_facts"]["rhea_doubts"]["known"] is True
    assert routines.daily_beats(_document()["simulation_state"], before=540, after=540 + DAY)[0] == made  # seeded
    second, made, _ = _tick(document)
    assert [change.beat for change in made if isinstance(change, c.BeatAdvanced)] == ["names"]  # it waited on a fact
    third, made, _ = _tick(second)
    assert not [change for change in made if isinstance(change, c.BeatAdvanced)]  # "flees" waits for day 4


def test_a_beats_chance_and_the_days_limit_hold() -> None:
    never = [{"npc_id": LIORA, "goals": [{"goal_id": "g", "summary": "s", "beats": [{"id": "b", "chance": 0.0}]}]}]
    assert routines.daily_beats(_document(never)["simulation_state"], before=540, after=540 + 3 * DAY) == ([], [])
    many = [{"npc_id": LIORA, "goals": [{"goal_id": f"g{index}", "summary": "s", "beats": [{"id": "b", "chance": 1.0}]}
                                       for index in range(5)]}]
    made, _ = routines.daily_beats(_document(many)["simulation_state"], before=540, after=540 + DAY)
    assert len([change for change in made if isinstance(change, c.BeatAdvanced)]) == routines.BEATS_PER_DAY


def test_a_beat_moves_its_person_but_never_a_protected_one() -> None:
    document = _document()
    for _ in range(4):
        document, _, _ = _tick(document)
    simulation = document["simulation_state"]
    assert routines.reached(simulation, RHEA, "traitor") == ["suspects", "names", "flees"]
    assert routines.whereabouts(simulation, routines.clock(simulation))[RHEA].location_id == "location:aurelia:cinderhold"
    guarded = _document()
    for _ in range(3):
        guarded, _, _ = _tick(guarded)
    guarded, _ = reduce(guarded, [c.CompanionJoined(npc_id=RHEA, name="Rhea")])
    _, made, _ = _tick(guarded)
    assert not [change for change in made if isinstance(change, c.BeatAdvanced)]  # a companion is not taken away


def test_word_is_told_by_someone_of_the_place_asked_for_news_and_then_it_is_heard() -> None:
    document, _ = reduce(_document(), [c.LocationChanged(location_id=GUILD, location_name="Wayfarers' Guild")])
    document, made, lines = _tick(document)
    assert lines == []  # the hero was not where it was told
    document, _ = reduce(document, [c.LocationChanged(location_id=VILLAGE, location_name="Starfall Village")])
    simulation = document["simulation_state"]
    assert [row["place_id"] for row in rumours(simulation)] == [VILLAGE, GROVE, GROVE]
    assert (NEWS, "news, rumours, what is going about") in speaker_topics(simulation, RHEA)
    plan = build_plan(simulation, RHEA, "Any news?", topics=(NEWS,))
    assert plan.news == ("The captain doubts the watch.",) and "news_to_tell" in plan.context()
    told = plan_changes(plan)
    assert [change.rumour_id for change in told if isinstance(change, c.RumourHeard)] == [
        "beat:npc:captain-rhea-sunward:traitor:suspects@location:aurelia:starfall-village",
        "beat:npc:captain-rhea-sunward:traitor:suspects@location:aurelia:arrival-grove"]  # every place's copy
    after, _ = reduce(document, told)
    assert after["state"]["word_heard"] == ["The captain doubts the watch."]
    assert after["simulation_state"]["world_facts"]["rhea_doubts"]["known"] is True
    assert news_here(after["simulation_state"], VILLAGE) == []
    assert (NEWS, "news, rumours, what is going about") not in speaker_topics(after["simulation_state"], RHEA)


def test_paid_information_sells_the_word_going_about_and_refuses_when_there_is_none() -> None:
    document, _ = reduce(_document(), [c.LocationChanged(location_id=GUILD, location_name="Wayfarers' Guild"),
                                       c.PresenceChanged(location_id=GUILD, present_npc_ids=(MIRI,))])
    offer = f"{MIRI}:information"
    nothing = buy(document["simulation_state"], offer, MIRI)
    assert nothing.refused and nothing.lines == ["Miri Kestrel has nothing new to tell you."]
    document, _ = reduce(document, spread("rumour:x", "The grove path is lit.", [GUILD]))
    sold = buy(document["simulation_state"], offer, MIRI)
    assert not sold.refused and "Miri Kestrel tells you: The grove path is lit." in sold.lines
    assert any(isinstance(change, c.RumourHeard) for change in sold.changes)


def test_a_beats_fact_fires_the_worlds_effects_of_it() -> None:
    document = _document()
    document["simulation_state"]["world_model"]["fact_effects"] = [
        {"when": {"rhea_doubts": True}, "place": {"location": GROVE, "line": "Guards walk the grove in pairs."},
         "told": "The guard is on edge."}]
    after, made, _ = _tick(document)
    _, lines = consequences(after["simulation_state"], made)
    assert "The guard is on edge." in lines


def test_the_game_master_brings_a_ready_beat_forward_and_sends_word_about() -> None:
    document = _document()
    folded = routines.fold_beat(document, {"npc_id": RHEA, "goal_id": "traitor"})
    assert not folded.refused and folded.changes[0] == c.BeatAdvanced(person_id=RHEA, goal_id="traitor", beat="suspects",
                                                                     source="game_master")
    assert routines.fold_beat(document, {"npc_id": LIORA, "goal_id": "nothing"}).refused == "no such goal with beats"
    document, _ = reduce(document, folded.changes)
    assert routines.fold_beat(document, {"npc_id": RHEA, "goal_id": "traitor"}).changes[0].beat == "names"  # it is ready:
    # "suspects" set the fact it waits on
    assert fold_rumour(document, {"location_id": VILLAGE, "told": ""}).refused == "a rumour needs a line, and names no secret"
    word = fold_rumour(document, {"location_id": VILLAGE, "told": "A stranger asks after the hero."})
    assert not word.refused and word.changes[0].place_id == VILLAGE
    assert fold_rumour(document, {"location_id": "location:nowhere", "told": "x"}).refused == "no such place in this world"


def test_version_14_keeps_rumours_of_the_new_shape_only() -> None:
    raw = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    raw["simulation_state"]["active_rumors"] = [{"rumor_id": "old", "text": "an old rumour"},
                                                {"rumour_id": "r@x", "place_id": GROVE, "text": "new"}]
    document = upcast_campaign_document(raw)
    assert document["simulation_state"]["active_rumors"] == [{"rumour_id": "r@x", "place_id": GROVE, "text": "new"}]
    assert document["simulation_state"]["npc_goal_state"] == {}


def test_a_fact_already_so_fires_its_effects_once_and_a_moved_person_stays_moved() -> None:
    """Review: a beat re-setting a fact to its value fired its one-time effect again; a game master's move was undone
    by the person's own day at the next hour; rumours of the game master's shared one id past the list's cap."""
    document = _document()
    document, _ = reduce(document, [c.FactSet(fact_id="rhea_doubts", value=True)])
    made, _ = routines.advance(document["simulation_state"], RHEA, _beats()[0]["goals"][0],
                               _beats()[0]["goals"][0]["beats"][0], source="day:1")
    assert not [change for change in made if isinstance(change, c.FactSet)]
    moved = routines.fold_move(document, {"npc_id": LIORA, "location_id": VILLAGE, "activity": "waiting"})
    document, _ = reduce(document, moved.changes)
    simulation = document["simulation_state"]
    assert routines.whereabouts(simulation, routines.clock(simulation) + 300)[LIORA].location_id == VILLAGE
    first = fold_rumour(document, {"location_id": VILLAGE, "told": "One word."}).changes[0].rumour_id
    second = fold_rumour(document, {"location_id": VILLAGE, "told": "Another word."}).changes[0].rumour_id
    assert first != second
