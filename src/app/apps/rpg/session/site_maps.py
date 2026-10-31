"""The grids of a campaign's own sites (evolution roadmap EV-10): stored at the commit of the turn that filled them in.

A site's rooms are laid out by code when the site is filled in (``rules/exploration.room_grid``), and the layout is
kept in the campaign's lore layer, so it replays exactly. A room's grid becomes a map definition here, at the commit,
under a map id that names the campaign and tied to it (migration 0191), so the local map meets it as any other place's
and it is deleted with the campaign; an imported campaign has them rebuilt from its document before its map instances.
Storing one again is a no-op.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections

_PALETTE = ({"code": ".", "terrain_id": "floor", "walkable": True, "blocks_sight": False, "movement_cost": 10},
            {"code": "#", "terrain_id": "wall", "walkable": False, "blocks_sight": True, "movement_cost": 99})


def definition_of(grid: Mapping[str, Any], *, world_id: str, world_revision: int) -> Any:
    """A room's grid as a map definition, with its hashes."""
    from app.apps.rpg.world.map_grid_contracts import GridMapDefinition, with_grid_definition_hashes

    arrival = list(grid.get("arrival") or (1, 1))
    location_id = _s(grid.get("location_id"))
    return with_grid_definition_hashes(GridMapDefinition.model_validate({
        "map_id": _s(grid.get("map_id")), "level": "dungeon", "definition_revision": 1, "world_id": world_id,
        "world_revision": world_revision, "width": int(grid.get("width") or 7), "height": int(grid.get("height") or 7),
        "terrain_palette": list(_PALETTE), "terrain_rows": list(grid.get("rows") or ()), "portals": [],
        "spawn_points": [{"spawn_point_id": f"spawn:{location_id}:arrival", "cell": arrival,
                          "tags": ["player", "arrival"], "secret": False}],
        "zones": [{"zone_id": f"zone:{location_id}:room", "name": "Room", "cells": [arrival], "secret": False}],
        "metadata": {"location_id": location_id, "presentation_fallback": "semantic_grid_placeholder",
                     "art_optional": True, "campaign_scoped": True}}))


def store_site_maps(work: Any, context: Any, *, campaign_id: str, document: Mapping[str, Any],
                    folded: Mapping[str, Any] | None) -> int:
    """At the commit of a turn that folded a site in: its rooms' grids stored as the campaign's map definitions."""
    if not any(_s(_d(row).get("kind")) in {"gm_area", "gm_invent"} for row in _d(folded).get("folded") or ()):
        return 0
    return store_all_site_maps(work, context, campaign_id=campaign_id, document=document)


def store_all_site_maps(work: Any, context: Any, *, campaign_id: str, document: Mapping[str, Any]) -> int:
    """Every grid of the campaign's sites stored as its map definitions (a campaign imported, or a site folded in):
    they are the campaign document's own, so they are rebuilt from it, exactly."""
    from app.apps.rpg.rules.exploration import site_maps

    manifest = _d(document.get("manifest"))
    world_id, world_revision = _s(manifest.get("world_id")), int(manifest.get("world_revision") or 0)
    if not world_id or world_revision < 1:
        return 0
    stored = 0
    for grid in site_maps(_d(_sections.simulation_state_of(document))):
        definition = definition_of(grid, world_id=world_id, world_revision=world_revision)
        work.map_instances.put_definition(
            context, map_id=definition.map_id, definition_revision=definition.definition_revision, world_id=world_id,
            world_revision=world_revision, document=definition.model_dump(mode="json"),
            definition_hash=definition.definition_hash, semantic_interface_hash=definition.semantic_interface_hash,
            campaign_id=campaign_id)
        stored += 1
    return stored


__all__ = ["definition_of", "store_all_site_maps", "store_site_maps"]
