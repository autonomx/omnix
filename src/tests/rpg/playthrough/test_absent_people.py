"""Playthrough: someone the world knows but who is not here (N1, 2026-10-31).

On Vesper-9's docks, "examine Nadi Vale" (Nadi at the night market) was planned as a look and failed the turn with a
server error: her lore is not part of the scene's. Since EV-9 a reading may name anyone the world knows; a look at, or
talk with, someone away is told where their day has them, and no time passes.
"""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def test_a_person_away_is_told_where_they_are_not_looked_at(launch) -> None:
    from app.apps.rpg.foundation.state import access as sections

    play = launch("vesper")
    simulation = play.simulation()
    here = simulation.get("current_location_id")
    away = next(npc for npc, row in sections.world_model_of(simulation)["npcs"].items()
                if "nadi" in npc and row.get("location_id") != here)
    card = play.client.post(f"/api/rpg/sessions/{play.session_id}/turn",
                            json={"command": "examine Nadi Vale", "card": {"family": "look", "target_id": away}})
    assert card.status_code == 200, card.text[:300]
    told = (card.json().get("visible_response") or {}).get("plain_text") or ""
    assert told.startswith("Inspector Nadi Vale is not here"), told
    for line in ("examine Nadi Vale", "talk to Nadi Vale"):
        response = play.client.post(f"/api/rpg/sessions/{play.session_id}/turn", json={"command": line})
        assert response.status_code == 200, (line, response.text[:300])
