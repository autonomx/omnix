"""Playthrough: a pressure running high raises a side quest, and doing it pushes the pressure back (RQ-5.4;
docs/rpg/design/quests.md). Aurelia's roads are dangerous from the start (severity 70); Captain Rhea Sunward keeps
the peace in Starfall March."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
ROADS = "pressure:roads:starfall-march"
TITLE = "Danger on the roads of Starfall March"
FIRST = "quest:pressure:roads:starfall-march:1"


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
    assert quest["objective"] == "Defeat 3 Sky Mantas" and hunt == {"defeat": "creature:sky-manta", "count": 3}  # fits
    assert 'Captain Rhea Sunward asks for your help: "Danger on the roads of Starfall March".' in play.model.told()
    play.turn(f"I accept the quest {TITLE}.")
    assert _quest(play)["status"] == "active"
    assert [row["quest_id"] for row in play.public()["quests"] if row["title"] == TITLE] == [FIRST]  # one at a time

    for _ in range(3):
        before = _severity(play)
        play.turn("I attack the Sky Manta.")
        for _ in range(30):
            if not play.combat().get("active"):
                break
            play.turn("I attack the Sky Manta.")
        assert _severity(play) < before + 8  # the manta felled pushed the danger back (the clock adds a little)
    quest = _quest(play)
    assert quest["progress"]["stage"] == 1 and quest["objective"] == "Tell Captain Rhea Sunward it is done", quest

    purse = play.purse()
    play.turn("I tell Captain Rhea Sunward the mantas are dealt with.")
    assert _quest(play)["status"] == "completed"
    assert play.purse() == purse + 100  # 10 silver
    if _severity(play) >= 60:  # the roads are still dangerous: the next one is offered
        assert _quest(play, FIRST.replace(":1", ":2"))["status"] == "available"
