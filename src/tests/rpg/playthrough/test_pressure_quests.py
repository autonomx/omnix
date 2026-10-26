"""Playthrough: a pressure running high raises a side quest, and doing it pushes the pressure back (RQ-5.4;
docs/rpg/design/quests.md). Aurelia's author makes the March roads dangerous from the start (Echo beasts, severity 62,
play-sections.json); Captain Rhea Sunward keeps the peace in Starfall March."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
ROADS = "pressure:echo-beasts"
TITLE = "Echo beasts on the March roads"
FIRST = "quest:pressure:echo-beasts:1"


def _quest(play, quest_id: str = FIRST) -> dict:
    return next(quest for quest in play.public()["quests"] if quest.get("quest_id") == quest_id)


def _severity(play) -> float:
    cells = play.simulation()["causal_world_runtime"]["state"]["cells"]
    return float(cells[ROADS]["values"]["pressure_severity"])


def test_a_side_quest_from_a_pressure_is_offered_done_and_eases_it(launch) -> None:
    play = launch("aurelia")
    play.turn("look around")
    assert not any(row["title"] == TITLE for row in play.public()["quests"])  # no one to ask in the grove
    play.turn("go to Starfall Village")
    quest = _quest(play)
    assert quest["status"] == "available" and quest["offered_by"] == "npc:captain-rhea-sunward", quest
    hunt = quest["steps"][0]["all_of"][0]
    assert quest["objective"] == "Defeat 3 Echo Wolves" and hunt == {"defeat": "creature:echo-wolf", "count": 3}  # fits
    assert 'Captain Rhea Sunward asks for your help: "Echo beasts on the March roads".' in play.model.told()
    play.turn(f"I accept the quest {TITLE}.")
    assert _quest(play)["status"] == "active"
    assert [row["quest_id"] for row in play.public()["quests"] if row["title"] == TITLE] == [FIRST]  # one at a time

    play.turn("go to Skybridge Pass")  # wolves are met on the road, where no one lives (encounters.md)
    for _ in range(8):  # a wolf may get away (encounters.md): hunt until three have fallen
        before, felled = _severity(play), (_quest(play).get("progress") or {}).get("counts", {}).get("creature:echo-wolf", 0)
        play.turn("I attack the Echo Wolf.")
        for _ in range(30):
            if not play.combat().get("active"):
                break
            play.turn("I attack the Echo Wolf.")
        if play.combat().get("ended_reason") == "enemy_side_defeated":
            assert _severity(play) < before + 8  # the wolf felled pushed the danger back (the clock adds a little)
        if (_quest(play).get("progress") or {}).get("stage") == 1:
            break
        assert felled <= 3
    quest = _quest(play)
    assert quest["progress"]["stage"] == 1 and quest["objective"] == "Tell Captain Rhea Sunward it is done", quest

    play.turn("go to Starfall Village")
    purse = play.purse()
    play.turn("I tell Captain Rhea Sunward the wolves are dealt with.")
    assert _quest(play)["status"] == "completed"
    assert play.purse() == purse + 100  # 10 silver
    assert not any(row["quest_id"] == FIRST.replace(":1", ":2") for row in play.public()["quests"])  # a day apart
    # A day from when it ended, not from when it was offered (the playtest: paid for one, asked for the next at once).
    clock = play.simulation()["environment"]["absolute_minutes"]
    assert _quest(play)["ended_at_minute"] == clock
