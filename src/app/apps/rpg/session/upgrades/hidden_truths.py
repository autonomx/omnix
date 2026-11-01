"""A campaign's world model without its world's secrets, once: version 11 (the ninth review). A campaign begun from a
world written as lore kept each person's and place's hidden truth in their descriptions, which a close look, an arrival
and the narrator read. The upgrade takes the sentences that tell one, in its own words, out of those descriptions,
with the secrets the campaign's canon and people hold (``rules/secrets.py``); a campaign begun since starts without
them (``genesis/worlds/lore_sections.public_text``). Nothing else is touched: a quest's objective, a pressure or what
someone knows is played as stored (the eleventh review: the starter town's quest objective shares nouns with its
innkeeper's secret)."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.rules.contracts import secrets_held, without_secrets


def keep_secrets_to_themselves(document: dict[str, Any]) -> dict[str, Any]:
    """The document with its people's and places' descriptions, a sentence telling a secret aside."""
    simulation = _sections.simulation_state_of(document)
    world = _sections.world_model_of(simulation) if isinstance(simulation, dict) else None
    if not isinstance(world, dict):
        return document
    canon = document.get("campaign_bible_projection") if isinstance(document.get("campaign_bible_projection"), dict) else {}
    secrets = [*secrets_held(canon), *secrets_held(world.get("npcs"))]
    if not secrets:
        return document
    for section in ("npcs", "locations"):
        rows = world.get(section)
        for row in (rows.values() if isinstance(rows, dict) else ()):
            if isinstance(row, dict) and isinstance(row.get("description"), str):
                row["description"] = without_secrets(row["description"], secrets)
    return document


__all__ = ["keep_secrets_to_themselves"]
