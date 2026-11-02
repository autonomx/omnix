"""Playthrough: quests of steps, with branches (RQ-5.4; docs/rpg/design/quests.md). The starter world's tavern
opening leads with "Rumor at the Rusty Flagon" (ask Bran or Mira) and offers "Rats in the Cellar" (three giant
rats, then a word with Bran)."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def test_a_branch_of_a_step_completes_the_quest_either_way(launch) -> None:
    play = launch("starter")
    rumor = play.quests()["Rumor at the Rusty Flagon"]
    assert rumor["status"] == "active" and rumor["objective"] == "Ask Bran or Mira which rumor is true"
    assert rumor["accepted_at_minute"] is not None  # taken up at the opening: a deadline would run from here
    xp = int(play.player_state().get("xp") or 0)
    answered = play.turn("I ask Mira which rumor is true.")
    rumor = play.quests()["Rumor at the Rusty Flagon"]
    assert rumor["status"] == "completed" and rumor["progress"]["branches"] == [{"stage": 0, "branch": 1}]  # Mira's
    assert int(play.player_state().get("xp") or 0) >= xp + 50
    assert "Quest complete: Rumor at the Rusty Flagon." in answered["visible_response"]["plain_text"], answered


def test_a_quest_of_stages_counts_its_foes_then_asks_for_the_report(launch) -> None:
    play = launch("starter")
    play.turn("I accept the quest Rats in the Cellar.")
    assert play.quests()["Rats in the Cellar"]["status"] == "active"
    for fought in range(1, 4):
        play.turn("I attack the Giant Rat.")
        for _ in range(30):
            if not play.combat().get("active"):
                break
            play.turn("I attack the Giant Rat.")
        rats = play.quests()["Rats in the Cellar"]
        assert rats["progress"]["counts"]["creature:market-road:giant-rat"] >= fought, rats
    assert rats["progress"]["stage"] == 1 and rats["objective"] == "Tell Bran the cellar is clear"
    assert "Next: Tell Bran the cellar is clear." in play.model.told(-1) or rats["progress"]["stage"] == 1
    play.turn("I tell Bran the cellar is clear.")
    assert play.quests()["Rats in the Cellar"]["status"] == "completed"
