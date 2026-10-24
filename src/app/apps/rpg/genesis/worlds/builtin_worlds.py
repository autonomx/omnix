"""The worlds Omnix ships with, installed into a workspace's library the first time a campaign needs one.

Every campaign plays from a world (roadmap §4.4). The classic new game is an opening of The Market Road, the
starter world, which ships as readable source under ``resources/examples/rpg/world-bundles/``. Its bundle is built
from that source (``world_source.py``, deterministic) and installed like any shared world: imported and adopted on
first use, under an id that names the bundle's content, so a newer source installs beside the older one and
campaigns already bound to the older one keep their world. Engine code holds none of its
content: which opening a starting place means is the world's own scenario metadata.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from app.runtime.paths import resources_root

BUNDLES_DIR = ("examples", "rpg", "world-bundles")


@dataclass(frozen=True)
class BuiltinWorld:
    key: str
    bundle: str  # the source's folder under resources/examples/rpg/world-bundles/


STARTER = BuiltinWorld(key="starter", bundle="the-market-road")


@lru_cache(maxsize=None)
def bundle_bytes(world: BuiltinWorld) -> bytes:
    """The world's bundle, built from its ``world.source.json``."""
    from .world_source import build_bundle

    source = resources_root().joinpath(*BUNDLES_DIR, world.bundle, "world.source.json")
    return build_bundle(json.loads(source.read_text(encoding="utf-8")))


def installed_world_id(world: BuiltinWorld) -> str:
    """The id the bundle installs under: one world per bundle content."""
    return f"world:{world.bundle}-{hashlib.sha256(bundle_bytes(world)).hexdigest()[:12]}"


def ensure_builtin_world(world: BuiltinWorld, *, database: Any | None = None) -> str:
    """Import and adopt ``world``'s bundle in this workspace unless it already is; its world id."""
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    from .world_adoption import adopt_shared_world, shared_world_state
    from .world_bundle_import import WorldBundleImportConflict, import_world_bundle

    world_id = installed_world_id(world)
    with unit_of_work(database) as work:
        stored = work.world_scenarios.get_world(current_tenant(), world_id)
        work.rollback()
    if stored is not None and shared_world_state(stored)["adopted"]:
        return world_id
    content = bundle_bytes(world)
    if stored is None:
        try:
            import_world_bundle(content, target_world_id=world_id, database=database)
        except WorldBundleImportConflict:
            pass  # another campaign's launch installed it first; adoption below is idempotent
    adopt_shared_world(world_id, bundle_sha256=hashlib.sha256(content).hexdigest(), database=database)
    return world_id


def _opening(world_id: str, starting_place: str, *, database: Any | None) -> dict[str, Any]:
    """The opening whose scenario names ``starting_place`` (else the world's default), as its latest revision."""
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    context = current_tenant()
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id) or {}
        default = str(dict(world.get("metadata") or {}).get("default_scenario_id") or "")
        scenarios = list(work.world_library.iter_scenarios(context, world_id=world_id))
        chosen = (next((row for row in scenarios
                        if dict(row.get("metadata") or {}).get("starting_place_key") == starting_place), None)
                  or next((row for row in scenarios if str(row.get("id")) == default), None)
                  or min(scenarios, key=lambda row: str(row.get("id"))))
        revisions = work.world_library.list_scenario_revisions(context, str(chosen["id"]))
        work.rollback()
    return dict(revisions[0]["document"])


def _lead_seed_id(revision_seeds: Any, opening_hook: str) -> str:
    """The opening's story seed for the hook the player chose (``tavern_rumor``), when the world has one."""
    for seed in revision_seeds or ():
        if isinstance(seed, Mapping) and opening_hook and seed.get("opening_hook") == opening_hook:
            return str(seed.get("id") or "")
    return ""


def launch_starter(request: Any, *, opening_hook: str = "", database: Any | None = None) -> dict[str, Any]:
    """The classic new game: the starter world's opening for the request's starting place, its hero as made."""
    from app.apps.rpg.session.service import SESSION_CAMPAIGN_SESSIONS

    from .postgres_service import load_published_resources
    from .published_launch import launch_published_scenario

    world_id = ensure_builtin_world(STARTER, database=database)
    document = _opening(world_id, str(getattr(request, "starting_location", "") or ""), database=database)
    revision, _, _ = load_published_resources(
        world_id=world_id, world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]), scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]), database=database,
    )
    made = request.model_dump(mode="json", exclude={"starting_location"})
    return launch_published_scenario(
        sessions=SESSION_CAMPAIGN_SESSIONS,
        world_id=world_id,
        world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]),
        scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]),
        player=made.get("player"),
        gameplay={key: made.get(key) for key in ("difficulty", "world_activity", "economy_pressure",
                                                 "combat_lethality", "companions_enabled", "permadeath")},
        features=made.get("features"),
        new_game=made,
        lead_seed_id=_lead_seed_id(revision.adventure_seeds, opening_hook),
        database=database,
    )


__all__ = ["STARTER", "BuiltinWorld", "ensure_builtin_world", "installed_world_id", "launch_starter"]
