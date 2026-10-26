"""The hero's record in the simulation, filled from the sheet once: when a campaign is created (its first save,
``new_game._save_created_session``), imported, or upgraded to version 9. A turn's load reads it as stored."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.state import access as _sections


def hydrate_hero(document: dict[str, Any]) -> dict[str, Any]:
    """The document with the simulation's hero given what the sheet has and it lacks (purse, resources, stats,
    skills, place, name, pack, worn gear, environment, quests), and the progression fields it has from birth."""
    from app.apps.rpg.rules.player.player_progression_state import (
        ensure_player_progression_state,
        skills_for_genre,
    )
    from app.apps.rpg.session.public_state_bridge import hydrate_simulation_player

    document = hydrate_simulation_player(document)
    simulation = _sections.simulation_state_of(document)
    if isinstance(simulation, dict):
        hero = _sections.player_state_of(simulation) or {}
        setup = document.get("setup_payload") if isinstance(document.get("setup_payload"), dict) else {}
        if not hero.get("skills"):  # a new hero's skills are those of their world's kind
            skills = skills_for_genre(str(setup.get("genre") or ""))
            if skills:
                hero["skills"] = skills
        simulation["player_state"] = ensure_player_progression_state(hero)
    return document


__all__ = ["hydrate_hero"]
