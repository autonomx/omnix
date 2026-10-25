"""RQ-2.4 part 3: the loadout's abilities are turns (combat.md, progression.md).

Out of a fight an ability is paid for and begins its cooldown, its heal heals and what it restores comes back; a
striking one needs a foe. The hotbar holds the hero's active abilities, one to a slot. An ability is learned as a
level's choice, so only when one is waiting.
"""
from __future__ import annotations


def _ability(play, action: str, **fields):
    return play.client.post(f"/api/rpg/sessions/{play.session_id}/loadout-action", json={"action": action, **fields})


def test_an_ability_out_of_a_fight_is_paid_for_and_what_it_restores_comes_back(launch) -> None:
    play = launch("aurelia")
    sensed = play.turn("use Trail Sense")
    assert sensed["outcome"]["planned_action"] == "ability"
    assert play.public()["player"]["resources"]["stamina"]["current"] == 95

    camp = _ability(play, "use_ability", ability_name="Make Camp")  # from the ability tree: the same rule
    assert camp.status_code == 200, camp.text[:300]
    assert "12 stamina comes back to you." in camp.json()["event"]["detail"]
    assert play.public()["player"]["resources"]["stamina"]["current"] == 100  # its pool keeps its maximum
    assert play.stored()["state"]["ability_state"]["cooldowns"] == {"survival_make_camp": 4}

    again = _ability(play, "use_ability", ability_name="Make Camp")
    assert again.status_code == 409 and "not ready yet" in again.json()["detail"]["detail"]

    aimed = _ability(play, "use_ability", ability_name="Aimed Shot")
    assert aimed.status_code == 409
    assert aimed.json()["detail"]["detail"] == "Aimed Shot needs a foe to aim at."
    assert play.public()["player"]["resources"]["stamina"]["current"] == 100  # nothing was paid


def test_the_hotbar_holds_the_heros_active_abilities(launch) -> None:
    play = launch("aurelia")
    revision = play.revision()
    put = _ability(play, "assign_hotbar", ability_name="Make Camp", hotbar_slot="7")
    assert put.status_code == 200, put.text[:300]
    state = play.stored()["state"]
    assert state["hotbar"]["7"] == "survival_make_camp" == state["ability_state"]["hotbar"]["7"]
    assert play.revision() == revision + 1  # committed as a turn, with no time passing
    assert play.stored()["state"]["turn_count"] == state["turn_count"]

    cleared = _ability(play, "remove_hotbar", hotbar_slot="7")
    assert cleared.status_code == 200
    assert "7" not in play.stored()["state"]["hotbar"]

    unknown = _ability(play, "assign_hotbar", ability_name="Volley", hotbar_slot="8")  # in the tree, not learned
    assert unknown.status_code == 409 and unknown.json()["detail"]["detail"] == "You do not know that ability."
    outside = _ability(play, "assign_hotbar", ability_name="Make Camp", hotbar_slot="11")
    assert outside.status_code == 409 and outside.json()["detail"]["detail"] == "The hotbar has slots 1 to 10."


def test_an_ability_is_learned_as_a_levels_choice(launch) -> None:
    from app.apps.rpg.session.service import load_session, save_session

    play = launch("aurelia")
    early = _ability(play, "unlock_ability", ability_id="recon_volley")
    assert early.status_code == 409
    assert early.json()["detail"]["detail"] == "You have no level's choice to make yet."

    session = load_session(play.session_id)
    session["simulation_state"]["player_state"].update(level=2, level_choices_pending=1)
    save_session(session, compact=False)
    learned = _ability(play, "unlock_ability", ability_id="recon_volley", ability_name="Volley")
    assert learned.status_code == 200, learned.text[:300]
    assert learned.json()["event"]["detail"] == "You learn Volley."
    assert "recon_volley" in play.stored()["state"]["ability_state"]["unlocked"]
    assert play.player_state()["level_choices_pending"] == 0
