"""Playthrough: combat depth (evolution roadmap EV-2) in Aurelia. Its Echo Wolves lose their nerve to what they are
weak to (contradictory commands, bells), and a companion ordered to guard the hero stands guard in the fight."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def _wolf_fight(play) -> dict:
    play.to_the_wild()
    play.turn("I attack the Echo Wolf.")
    combat = play.combat()
    assert combat["active"] is True
    return combat


def test_an_echo_wolf_loses_its_nerve_to_contradictory_commands(launch) -> None:
    play = launch("aurelia")
    play.turn("I accept the quest Voices in the Phone.")
    _wolf_fight(play)
    for _ in range(12):
        play.turn("I attack the Echo Wolf with contradictory commands.")
        combat = play.combat()
        if any(row.get("kind") == "weakness" for row in combat.get("combat_log") or ()):
            break
    used = [row for row in combat["combat_log"] if row.get("kind") == "weakness"]
    assert used and used[0]["effect"] == "morale"
    assert "contradictory commands is its weakness" in play.model.told() or "bells" in play.model.told()
    assert combat["active"] is False and combat["ended_reason"] == "enemy_fled"  # it fled the field


def test_a_companion_ordered_to_guard_stands_guard_in_the_fight(launch) -> None:
    play = launch("aurelia")
    play.turn("I ask Liora Fen to join my party as a companion.")
    combat = _wolf_fight(play)
    assert combat["participants"]["npc:liora-fen"].get("guards") is None
    play.turn("Liora, guard me.")  # an order in a fight: the companion rule's, read by the fight
    party = (play.player_state().get("party_state") or {}).get("companions") or []
    assert party[0].get("stance") == "guard"
    play.turn("I attack the Echo Wolf.")
    combat = play.combat()
    if combat.get("active"):
        assert combat["participants"]["npc:liora-fen"]["guards"] == "player"
    offered = [row["label"] for row in play.turn("I defend myself.")["outcome"]["presentation"]["suggestions"]]
    if play.combat().get("active"):
        assert "Liora Fen: guard me" in offered and "Break away" in offered  # its cards: orders, and a way out
