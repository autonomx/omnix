"""A campaign's world model without its world's secrets, once: version 11 (the ninth review). A campaign begun from a
world written as lore kept each person's and place's hidden truth in their descriptions, which a close look, an arrival
and the narrator read. The upgrade takes them out with the secrets the campaign's own canon holds
(``rules/secrets.py``); a campaign begun since starts without them (``genesis/worlds/lore_sections.public_text``)."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.rules.contracts import public_canon


def keep_secrets_to_themselves(document: dict[str, Any]) -> dict[str, Any]:
    """The document with its world model's text, a sentence telling a secret of its canon or of its people aside."""
    simulation = _sections.simulation_state_of(document)
    world = _sections.world_model_of(simulation) if isinstance(simulation, dict) else None
    if not isinstance(world, dict):
        return document
    canon = document.get("campaign_bible_projection") if isinstance(document.get("campaign_bible_projection"), dict) else {}
    simulation["world_model"] = public_canon({"canon": canon, "world": world})["world"]
    return document


__all__ = ["keep_secrets_to_themselves"]
