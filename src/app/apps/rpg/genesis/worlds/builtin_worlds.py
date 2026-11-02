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
from app.caching.bounded_cache import bounded_lru_cache
from typing import Any, Mapping

from app.runtime.paths import resources_root

BUNDLES_DIR = ("examples", "rpg", "world-bundles")


@dataclass(frozen=True)
class BuiltinWorld:
    key: str
    bundle: str  # the source's folder under resources/examples/rpg/world-bundles/


STARTER = BuiltinWorld(key="starter", bundle="the-market-road")
# The preset a campaign made before worlds were bound was launched from as the demo (the document upcast reads it).
LEGACY_DEMO_PRESET_ID = "demo_glimmerdeep_pass_lvl14"


@bounded_lru_cache(max_entries=8, ttl_seconds=3600.0)
def _source_text(world: BuiltinWorld) -> str:
    return resources_root().joinpath(*BUNDLES_DIR, world.bundle, "world.source.json").read_text(encoding="utf-8")


def world_source(world: BuiltinWorld) -> dict[str, Any]:
    """The world's readable source (a fresh copy)."""
    return json.loads(_source_text(world))


@bounded_lru_cache(max_entries=8, ttl_seconds=3600.0)
def bundle_bytes(world: BuiltinWorld) -> bytes:
    """The world's bundle, built from its ``world.source.json``."""
    from .world_source import build_bundle

    return build_bundle(world_source(world))


def legacy_ids(world: BuiltinWorld) -> dict[str, str]:
    """The ids the engine's own copies of this world used (``loc_tavern``, ``npc:Bran``), and the world's for each."""
    return {str(old): str(new) for old, new in dict(world_source(world).get("legacy_ids") or {}).items()}


@bounded_lru_cache(max_entries=8, ttl_seconds=3600.0)
def _revision(world: BuiltinWorld) -> Any:
    from .contracts import WorldRevisionDocument
    from .world_source import compile_world

    [row] = compile_world(world_source(world))["world_revisions"]
    return WorldRevisionDocument.model_validate(row["document"])


def builtin_world_model(world: BuiltinWorld, location_id: str) -> dict[str, Any]:
    """The world model a campaign of ``world`` plays from, for a hero at ``location_id``: built from the source
    alone (no library), for a campaign made before the world was a bundle (the v7 upgrade binds it)."""
    from types import SimpleNamespace

    from .published_world_setup import session_world_model

    model = session_world_model(_revision(world), SimpleNamespace(starting_location_id=location_id))
    return {**model, "world_id": installed_world_id(world)}


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


def _with_ids(value: Any, ids: Mapping[str, str]) -> Any:
    """``value`` with every string that is one of ``ids`` (a whole value or key, never part of one) replaced."""
    if isinstance(value, dict):
        return {(ids.get(key, key) if isinstance(key, str) else key): _with_ids(child, ids) for key, child in value.items()}
    if isinstance(value, list):
        return [_with_ids(child, ids) for child in value]
    if isinstance(value, str):
        return ids.get(value, value)
    return value


def _default_start(world: BuiltinWorld) -> str:
    source = world_source(world)
    default = str(source["world"]["metadata"].get("default_scenario_id") or "")
    return next(str(row["starting_location_id"]) for row in source["scenarios"] if row["scenario_id"] == default)


def bind_to_starter_world(document: dict[str, Any]) -> dict[str, Any]:
    """A campaign made in the starter town before it was a world, playing from the starter world: its places and
    people named by the world's ids, the world model for where the hero stands, who is present there, and its
    binding naming the world. A campaign that already plays from a world is returned as it is; one World Forge made
    (``setup_payload.genesis``), which the version 6 upgrade also marked "starter", is marked as its own."""
    state = raw_state if isinstance(raw_state := document.get("state"), dict) else {}
    binding = raw_world_binding if isinstance(raw_world_binding := state.get("world_binding"), dict) else {}
    simulation = raw_simulation_state if isinstance(raw_simulation_state := document.get("simulation_state"), dict) else {}
    if binding.get("kind") != "starter" or binding.get("world_id") or simulation.get("world_model"):
        return document
    setup = raw_setup_payload if isinstance(raw_setup_payload := document.get("setup_payload"), dict) else {}
    if setup.get("genesis") or setup.get("compiled_genesis"):
        return {**document, "state": {**state, "world_binding": {"kind": "genesis"}}}
    bound = _with_ids(document, legacy_ids(STARTER))
    simulation, state = dict(bound.get("simulation_state") or {}), dict(bound.get("state") or {})
    player = dict(simulation.get("player_state") or {})
    here = str(player.get("location_id") or simulation.get("location_id") or state.get("current_location_id") or "")
    model = builtin_world_model(STARTER, here)
    if here not in model["locations"]:
        here = _default_start(STARTER)
        model = builtin_world_model(STARTER, here)
    place = model["locations"][here]
    player.update(location_id=here, current_location_id=here)
    simulation.update(
        world_model=model, player_state=player, location_id=here, current_location_id=here,
        present_npc_state={**dict(simulation.get("present_npc_state") or {}), "location_id": here,
                           "present_npc_ids": [npc["id"] for npc in place["present_npcs"]]},
    )
    present = [npc["id"] for npc in place["present_npcs"]]
    runtime = dict(bound.get("runtime_state") or {})
    scene = dict(runtime.get("current_scene") or {})
    runtime["current_scene"] = {  # the scene the narrator and the scene readers build on, as presence writes it
        **scene, "scene_id": f"scene:{here}", "location_id": here, "location_name": place["name"],
        "title": place["name"], "summary": place["description"], "present_npc_ids": present,
        "actors": [npc["name"] for npc in place["present_npcs"]],
    }
    state.update(current_location_id=here,
                 world_binding={"kind": "starter", "world_id": installed_world_id(STARTER), "source": "builtin_world"})
    return {**bound, "simulation_state": simulation, "state": state, "runtime_state": runtime}


def _opening(world_id: str, starting_place: str = "", *, preset: str = "", database: Any | None) -> dict[str, Any]:
    """The opening whose scenario names ``starting_place`` or ``preset`` (else the world's default), as its latest
    revision."""
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    context = current_tenant()
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id) or {}
        default = str(dict(world.get("metadata") or {}).get("default_scenario_id") or "")
        scenarios = list(work.world_library.iter_scenarios(context, world_id=world_id))
        named = [row for row in scenarios
                 if (starting_place and dict(row.get("metadata") or {}).get("starting_place_key") == starting_place)
                 or (preset and dict(row.get("metadata") or {}).get("preset_id") == preset)]
        chosen = (next(iter(named), None)
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


def launch_starter(request: Any, *, sessions: Any, opening_hook: str = "", prepare: Any = None,
                   database: Any | None = None) -> dict[str, Any]:
    """The classic new game: the starter world's opening for the request's starting place, its hero as made
    (``sessions`` creates and saves the campaign, as for any published launch; ``prepare`` adds the caller's own
    records before that save)."""
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
        sessions=sessions,
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
        prepare=prepare,
        database=database,
    )


def presets(world: BuiltinWorld = STARTER) -> list[dict[str, Any]]:
    """The campaigns already under way a player can start from the world (its openings that name a preset)."""
    source = world_source(world)
    places = {row["id"]: row["name"] for row in source["revision"]["topology"]["locations"]}
    return [
        {"preset_id": opening["metadata"]["preset_id"], "name": opening["title"], "description": opening["description"],
         "kind": opening["metadata"].get("kind") or "in_progress", "level": int(opening["starting_resources"].get("level") or 1),
         "location": places.get(opening["starting_location_id"], ""), "clone_on_start": True}
        for opening in source["scenarios"] if opening.get("metadata", {}).get("preset_id")
    ]


def launch_preset(preset_id: str, *, sessions: Any, database: Any | None = None) -> dict[str, Any]:
    """A campaign already under way, as the world's preset opening has it: its hero, kit, party and journal."""
    from .postgres_service import load_published_resources
    from .published_launch import launch_published_scenario

    world_id = ensure_builtin_world(STARTER, database=database)
    document = _opening(world_id, preset=preset_id, database=database)
    _, _, scenario = load_published_resources(
        world_id=world_id, world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]), scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]), database=database,
    )
    hero = dict(next(iter(scenario.protagonist_options), {}))
    player = {key: hero[key] for key in ("name", "pronouns", "background", "build") if hero.get(key)}
    made = {key: hero[key] for key in ("primary_capability", "secondary_capabilities", "power_source",
                                       "generated_class_name") if hero.get(key)}
    launched = launch_published_scenario(
        sessions=sessions,
        world_id=world_id,
        world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]),
        scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]),
        player=player,
        new_game={**made, "player": player},
        database=database,
    )
    return launched


__all__ = ["STARTER", "BuiltinWorld", "bind_to_starter_world", "builtin_world_model", "ensure_builtin_world", "installed_world_id",
           "launch_preset", "launch_starter", "legacy_ids", "presets", "world_source"]
