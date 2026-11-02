"""Playthrough: the storyteller (the model provider) down or too slow (RQ-8.8; roadmap §4.6).

Every model call fails. Commands the grammar reads still play by the rules, the turn is told plainly in the game's
own words, the play screen is told the storyteller is unavailable, and nothing the player sees is a profile card or
an error code.
"""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES


def _down(*_args, **_kwargs):
    raise ConnectionError("the provider is down")


def _said(response) -> str:
    assert response.status_code == 200, response.text[:300]
    return response.json()["visible_response"]["plain_text"]


def test_with_the_storyteller_down_plain_commands_play_and_the_player_is_told(launch) -> None:
    from app.apps.rpg.edge.api.turn_pipeline import STORYTELLER_UNAVAILABLE
    from app.apps.rpg.narration.presentation.visible_response import NOTHING_COMES_OF_IT

    play = launch("aurelia")
    calm = play.post_turn("look around")
    assert calm.status_code == 200 and not calm.json().get("notices")  # the storyteller answers: no notice
    for role in Role:
        play.model.answer(role, _down)
    play.model.write_narrative = _down

    looked = play.post_turn("look around")
    assert _said(looked).startswith("You look around Starfall Grove.")
    assert looked.json()["notices"] == [{"kind": "storyteller_unavailable", "message": STORYTELLER_UNAVAILABLE}]
    travelled = play.post_turn("go to Starfall Village")
    assert "You travel to Starfall Village" in _said(travelled)
    assert play.location() == "location:aurelia:starfall-village"  # the rules moved the hero
    asked = _said(play.post_turn("I ask Orik Stonewake about the newcomers."))
    assert "Orik Stonewake" in asked and not any(field in asked for field in ("Id:", "Name:", "Role:", "Goals:"))
    pondered = play.post_turn("Hmm, I ponder the meaning of the stars and hum a tune")
    assert _said(pondered) == NOTHING_COMES_OF_IT and pondered.json()["notices"]
    assert play.turn_count() == 5
