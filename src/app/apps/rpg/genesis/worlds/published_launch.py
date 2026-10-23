"""Fast deterministic campaign launch from certified world releases."""
from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Mapping

from app.security.tenant_context import current_tenant
from app.apps.rpg.foundation.persistence.rpg_campaign_bible_repository import campaign_bible_hash
from app.persistence.unit_of_work import unit_of_work

from .lifecycle_service import require_scenario_writable
from .postgres_service import load_published_resources, load_release_definitions
from .progressive_materialization_job_service import (
    schedule_campaign_predictive_materialization,
)
from .published_canon_projection import project_published_canon
from .published_world_setup import (
    creator_setup,
    location_label,
    opening_kit,
    opening_quests,
    session_world_model,
)
from .semantic_validation import (
    initialize_starting_map_snapshot,
    validate_scenario_against_release,
)
from .service import resolve_campaign_binding

if TYPE_CHECKING:
    from app.apps.rpg.genesis.contracts import CampaignSessions


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


_BIBLE_PROJECTION_KEYS = (
    "documents",
    "entities",
    "facts",
    "retrieval_cards",
    "relationships",
    "knowledge_rules",
    "mechanics_catalog",
    "story_threads",
    "indexes",
    "discovery_state",
)


def _attach_published_canon(
    session: dict[str, Any],
    canon: Mapping[str, Any],
    *,
    campaign_id: str,
    topology: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Attach immutable world canon as the new campaign's initial Bible."""

    bible = project_published_canon(
        canon,
        campaign_id=campaign_id,
        canon_revision=int(canon.get("canon_revision") or 1),
        topology=topology,
    )
    revision = int(bible.get("canon_revision") or 1)
    digest = campaign_bible_hash(bible)
    projection = {
        key: deepcopy(
            bible.get(
                key,
                {}
                if key in {
                    "entities",
                    "indexes",
                    "discovery_state",
                    "mechanics_catalog",
                }
                else [],
            )
        )
        for key in _BIBLE_PROJECTION_KEYS
    }
    projection.update(
        {
            "schema_version": str(bible.get("schema_version") or "rpg_campaign_bible_v2"),
            "manifest": deepcopy(_record(bible.get("manifest"))),
            "content_hash": digest,
            "canon_revision": revision,
        }
    )
    session["campaign_bible_projection"] = projection

    state = _record(session.get("state"))
    state["campaign_bible"] = {
        "schema_version": projection["schema_version"],
        "canon_revision": revision,
        "content_hash": digest,
        "manifest": deepcopy(projection["manifest"]),
        "discovery_state": deepcopy(projection["discovery_state"]),
    }
    session["state"] = state
    runtime = _record(session.get("runtime_state"))
    runtime["campaign_bible_revision"] = revision
    runtime["campaign_bible_content_hash"] = digest
    session["runtime_state"] = runtime
    manifest = _record(session.get("manifest"))
    manifest["campaign_bible_revision"] = revision
    manifest["campaign_bible_content_hash"] = digest
    session["manifest"] = manifest
    return session, bible, digest


def _resources_from_kit(resources: Mapping[str, Any], kit: Mapping[str, Any]) -> dict[str, Any]:
    """The player's HP and mana from the opening's health and aether, when the opening sets them."""
    result = deepcopy(dict(resources))
    for key, value in (("hp", int(kit.get("health") or 0)), ("mana", int(kit.get("aether") or 0))):
        if value > 0:
            result[key] = {"max": value, "current": value}
    return result


def _opening_environment(
    session: Mapping[str, Any],
    *,
    location_id: str,
    location: Mapping[str, Any],
    location_name: str,
    epoch: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A live environment (weather, calendar, light) for the opening's own place and region."""
    from app.apps.rpg.session.environment import DEFAULT_REGION_ID, build_initial_environment_seed_state

    state = _record(session.get("state"))
    metadata = _record(state.get("metadata"))
    seeded = build_initial_environment_seed_state(
        campaign_seed=int(metadata.get("seed") or 0),
        campaign_contract={"location_id": location_id},
        location_id=location_id,
        location={"time_label": epoch, "location": location_name, "weather": "clear"},
    )
    region_id = str(location.get("region_id") or DEFAULT_REGION_ID)
    environment = {
        **seeded["environment"],
        "region_id": region_id,
        "region_name": str(location.get("region_name") or ""),
    }
    for event in environment.get("active_events") or ():
        if isinstance(event, dict):
            event["region_id"] = region_id
    context = {
        **seeded["scene_environment_context"],
        "region_id": region_id,
        "location_id": location_id,
        "location_label": location_name,
    }
    return environment, context


def _apply_published_opening_state(
    session: dict[str, Any],
    *,
    revision: Any,
    scenario: Any,
    world: Mapping[str, Any],
    present_at_start: tuple[str, ...],
) -> None:
    """Replace the new-game bootstrap with the published world: its place, people, kit, quests and weather."""

    location_id = str(scenario.starting_location_id)
    world_model = session_world_model(revision, scenario, present_at_start=present_at_start)
    locations = _record(world_model.get("locations"))
    location = _record(locations.get(location_id))
    location_name = location_label(revision, location_id)
    description = str(location.get("description") or f"You arrive at {location_name}.")
    epoch = str(scenario.starting_epoch or "Day 1, 08:00")
    state = _record(session.get("state"))
    player = _record(state.get("player"))
    kit = opening_kit(
        revision,
        scenario,
        equipment=[_record(item) for item in player.get("equipment") or ()],
        inventory=[_record(item) for item in player.get("inventory") or ()],
    )
    player.update(
        {
            "inventory": kit["inventory"],
            "currency": kit["currency"],
            "resources": _resources_from_kit(_record(player.get("resources")), kit),
            "location_id": location_id,
        }
    )
    if kit["knowledge"]:
        player["knowledge"] = kit["knowledge"]
    present = [_record(npc) for npc in location.get("present_npcs") or ()]
    exits = sorted(
        str(_record(locations.get(target)).get("name") or target)
        for target in _record(location.get("exits")).values()
    )
    quick_actions = [f"Look around {location_name}"]
    quick_actions += [f"Talk to {npc['name']}" for npc in present[:2]]
    quick_actions += [f"Travel to {name}" for name in exits[:1]]
    quick_actions.append("Check my quests")
    arrival = {
        "turn": 0,
        "time": epoch,
        "title": f"Arrived at {location_name}",
        "detail": description,
        "kind": "published_opening",
    }
    environment, scene_context = _opening_environment(
        session, location_id=location_id, location=location, location_name=location_name, epoch=epoch
    )
    state.update(
        {
            "title": f"{player.get('name') or 'Player'} — {location_name}",
            "player": player,
            "location": location_name,
            "current_location": location_name,
            "current_location_id": location_id,
            "current_location_name": location_name,
            "summary": description,
            "quests": opening_quests(revision, scenario),
            "relationships": [],
            "party": [],
            "quick_actions": quick_actions,
            "timeline": [arrival],
            "journal": {"entries": [arrival]},
            "scene": {**_record(state.get("scene")), "environment_context": scene_context},
        }
    )
    state.pop("environment_snapshot", None)
    state["world"] = {
        **_record(state.get("world")),
        "time": epoch,
        "region": str(location.get("region_name") or ""),
        "environment": environment,
        "current_location_id": location_id,
        "current_location_name": location_name,
    }
    state["narrative_affordances"] = {
        **_record(state.get("narrative_affordances")),
        "opening_story": {
            "title": f"Arrival at {location_name}",
            "summary": description,
            "source": "published_scenario",
        },
        "suggested_actions": quick_actions,
    }
    metadata = _record(state.get("metadata"))
    state["metadata"] = {
        **metadata,
        "starting_location_id": location_id,
        "starting_location_name": location_name,
        "opening_source": "published_scenario",
        "opening_hook": "published_opening",
    }
    session["state"] = state
    setup = creator_setup(revision, scenario, world_model, world)
    first_quest = _record((state.get("quests") or [{}])[0])
    setup["opening"] = {
        "location_id": location_id,
        "location_name": location_name,
        "scene_frame": description,
        "immediate_problem": str(first_quest.get("hook") or first_quest.get("objective") or ""),
        "player_involvement_reason": str(first_quest.get("objective") or ""),
        "present_npc_ids": list(setup["starting_npc_ids"]),
        "first_choices": quick_actions,
    }
    # The turn engine reads its world from the creator setup each turn; without the world's own setup it fills in
    # its built-in starter town.
    session["setup_payload"] = {**_record(session.get("setup_payload")), **setup}
    # Who is here from the very first turn: the world's people, and the opening scene with those present.
    present_ids = [str(npc.get("id")) for npc in present]
    runtime = _record(session.get("runtime_state"))
    runtime.update(
        {
            "current_location_id": location_id,
            "current_location_name": location_name,
            "current_scene": {
                "scene_id": f"scene:{location_id}:opening",
                "location_id": location_id,
                "location_name": location_name,
                "summary": description,
                "present_npc_ids": present_ids,
            },
        }
    )
    session["runtime_state"] = runtime
    simulation = _record(session.get("simulation_state"))
    player_state = _record(simulation.get("player_state"))
    player_state["location_id"] = location_id
    simulation.update(
        {
            "world_model": world_model,
            "npc_index": {
                str(npc_id): {**_record(npc), "npc_id": str(npc_id)}
                for npc_id, npc in _record(world_model.get("npcs")).items()
            },
            "present_npc_state": {"location_id": location_id, "present_npc_ids": present_ids},
            "player_state": player_state,
            "location_id": location_id,
            "current_location_id": location_id,
            "location_name": location_name,
            "travel_state": {
                **_record(simulation.get("travel_state")),
                "current_location_id": location_id,
            },
            "location_state": {
                **_record(simulation.get("location_state")),
                "current_location_id": location_id,
                "location_name": location_name,
            },
        }
    )
    session["simulation_state"] = simulation


def launch_published_scenario(
    *,
    sessions: CampaignSessions,
    world_id: str,
    world_revision: int,
    world_release: int,
    scenario_id: str,
    scenario_revision: int,
    player: Mapping[str, Any] | None = None,
    gameplay: Mapping[str, Any] | None = None,
    features: Mapping[str, Any] | None = None,
    database: Any | None = None,
) -> dict[str, Any]:
    """Create a playable campaign without invoking World Forge or any model provider."""

    revision, release, scenario = load_published_resources(
        world_id=world_id,
        world_revision=world_revision,
        world_release=world_release,
        scenario_id=scenario_id,
        scenario_revision=scenario_revision,
        database=database,
    )
    definitions = load_release_definitions(revision, release, database=database)
    starting_definition = validate_scenario_against_release(
        scenario,
        release,
        definitions,
    )
    certification = _record(release.certification)
    if not bool(certification.get("launch_ready")):
        raise ValueError(
            "world_release_not_launch_ready:"
            + ",".join(
                str(item) for item in certification.get("missing_requirements") or ()
            )
        )

    context = current_tenant()
    with unit_of_work(database) as work:
        require_scenario_writable(work, context, scenario_id)
        world = work.world_scenarios.get_world(context, world_id)
        work.rollback()
    if world is None:
        raise KeyError(f"world_not_found:{world_id}")

    canon = _record(revision.canon)
    gameplay_payload = dict(gameplay or {})
    player_payload = dict(player or {})
    player_payload.setdefault("name", "Alyndra")
    player_payload.setdefault("pronouns", "they/them")
    player_payload.setdefault("background", "World Traveler")
    player_payload.setdefault("build", "balanced_adventurer")
    request = sessions.new_game_request(
        {
            "campaign_template": str(
                canon.get("campaign_template") or "classic_fantasy"
            ),
            "genre": str(world.get("genre") or "classic_fantasy"),
            "tone": str(world.get("tone") or "heroic adventure"),
            "background": str(player_payload.get("background") or "World Traveler"),
            "starting_location": scenario.starting_location_id,
            "player": player_payload,
            "difficulty": str(gameplay_payload.get("difficulty") or "normal"),
            "world_activity": str(
                gameplay_payload.get("world_activity") or "standard"
            ),
            "economy_pressure": str(
                gameplay_payload.get("economy_pressure") or "normal"
            ),
            "combat_lethality": str(
                gameplay_payload.get("combat_lethality") or "normal"
            ),
            "companions_enabled": bool(
                gameplay_payload.get("companions_enabled", True)
            ),
            "permadeath": bool(gameplay_payload.get("permadeath", False)),
            "seed": int(world.get("seed") or 0),
            "features": dict(features or {}),
        }
    )
    created = sessions.create_new_game(request)
    session_id = str(created.get("session_id") or "")
    session = raw_session if isinstance(raw_session := created.get("session"), dict) else None
    if not session_id or session is None:
        raise RuntimeError("published_scenario_session_creation_failed")

    binding = resolve_campaign_binding(
        campaign_id=session_id,
        world_revision=revision,
        world_release=release,
        scenario_revision=scenario,
    )
    map_instance_id = f"{session_id}:map:{starting_definition.map_id}:1"
    protagonist_actor_id = f"player:{session_id}"
    starting_snapshot = initialize_starting_map_snapshot(
        map_instance_id=map_instance_id,
        campaign_id=session_id,
        protagonist_actor_id=protagonist_actor_id,
        scenario=scenario,
        definition=starting_definition,
    )

    _apply_published_opening_state(
        session,
        revision=revision,
        scenario=scenario,
        world=world,
        present_at_start=tuple(
            actor.actor_id for actor in starting_snapshot.actors if actor.actor_id != protagonist_actor_id
        ),
    )

    state = _record(session.get("state"))
    manifest = _record(session.get("manifest"))
    runtime = _record(session.get("runtime_state"))
    setup = _record(session.get("setup_payload"))
    state["world_binding"] = binding.model_dump(mode="json")
    state["current_map_instance_id"] = map_instance_id
    state["published_world"] = {
        "world_id": revision.world_id,
        "world_revision": revision.revision,
        "world_release": release.release,
        "title": revision.title,
        "starting_location_id": scenario.starting_location_id,
        "starting_epoch": scenario.starting_epoch,
        "activated_conflict_ids": list(scenario.activated_conflict_ids),
        "initial_npc_ids": list(scenario.initial_npc_ids),
        "opening_seed_ids": list(scenario.opening_seed_ids),
        "starting_resources": dict(scenario.starting_resources),
        "starting_map_instance_id": map_instance_id,
    }
    manifest["world_id"] = revision.world_id
    manifest["world_revision"] = revision.revision
    manifest["world_release"] = release.release
    manifest["scenario_id"] = scenario.scenario_id
    manifest["scenario_revision"] = scenario.revision
    manifest["title"] = str(state.get("title") or revision.title)
    manifest["creation_status"] = "completed"
    manifest["created_from"] = "published_scenario"
    runtime["campaign_launch_gate"] = {
        "ready": True,
        "required_before_first_turn": True,
        "missing_requirements": [],
    }
    runtime["published_scenario_initialization"] = {
        "status": "applied",
        "map_instance_id": map_instance_id,
        "operation_ids": list(starting_snapshot.initialization_operation_ids),
    }
    runtime["starting_map_snapshot"] = starting_snapshot.model_dump(mode="json")
    setup["published_world_binding"] = binding.model_dump(mode="json")
    session["state"] = state
    session["manifest"] = manifest
    session["runtime_state"] = runtime
    session["setup_payload"] = setup
    session, campaign_bible, campaign_bible_digest = _attach_published_canon(
        session,
        canon,
        campaign_id=session_id,
        topology=revision.topology,
    )
    state = _record(session.get("state"))
    manifest = _record(session.get("manifest"))
    saved = sessions.save(session, compact=True)

    try:
        with unit_of_work(database) as work:
            campaign = work.rpg.get_campaign(context, session_id, for_update=True)
            if campaign is None:
                work.rpg.create_campaign(
                    context,
                    campaign_id=session_id,
                    title=str(state.get("title") or revision.title),
                    state=state,
                    engine_version="published-world-launch-v1",
                    schema_version=str(
                        manifest.get("schema_version") or "rpg-session-v1"
                    ),
                    seed=str(world.get("seed") or 0),
                    metadata={
                        "launch_mode": "published_scenario",
                        "world_id": revision.world_id,
                        "world_revision": revision.revision,
                        "world_release": release.release,
                        "scenario_id": scenario.scenario_id,
                        "scenario_revision": scenario.revision,
                        "starting_map_instance_id": map_instance_id,
                        "campaign_bible_content_hash": campaign_bible_digest,
                    },
                )
            stored_bible = work.campaign_bibles.get(
                context,
                session_id,
                for_update=True,
            )
            if stored_bible is None:
                stored_bible = work.campaign_bibles.put(
                    context,
                    campaign_id=session_id,
                    document=campaign_bible,
                    expected_revision=0,
                    provenance={
                        "source": "published_world_release",
                        "world_id": revision.world_id,
                        "world_revision": revision.revision,
                        "world_release": release.release,
                    },
                    consistency_report=_record(certification.get("consistency_report")),
                    completeness=_record(certification.get("completeness")),
                )
            elif str(stored_bible.get("content_hash") or "") != campaign_bible_digest:
                raise RuntimeError(
                    f"published_campaign_bible_conflict:{session_id}"
                )
            stored_binding = work.world_scenarios.bind_campaign(
                context,
                campaign_id=session_id,
                world_id=binding.world_id,
                world_revision=binding.world_revision,
                world_release=binding.world_release,
                scenario_id=binding.scenario_id,
                scenario_revision=binding.scenario_revision,
                binding=binding.model_dump(mode="json"),
            )
            stored_map_instance = work.map_instances.create_instance(
                context,
                map_instance_id=starting_snapshot.map_instance_id,
                campaign_id=starting_snapshot.campaign_id,
                location_id=starting_snapshot.location_id,
                map_id=starting_snapshot.map_id,
                definition_revision=starting_snapshot.definition_revision,
                definition_hash=starting_snapshot.definition_hash,
                snapshot=starting_snapshot.model_dump(mode="json"),
            )
            work.commit()
    except Exception:
        sessions.archive(session_id)
        raise

    try:
        materialization_schedule = schedule_campaign_predictive_materialization(
            session_id,
            current_location_id=scenario.starting_location_id,
            database=database,
            kick_worker=database is None,
            allow_missing_plan=True,
        )
    except Exception as exc:
        materialization_schedule = {
            "ok": False,
            "status": "deferred",
            "scheduled": [],
            "worker_started": False,
            "error": str(exc),
        }

    return {
        "ok": True,
        "status": "ready",
        "session_id": session_id,
        "session": saved,
        "game": saved.get("state", {}),
        "binding": stored_binding,
        "map_instance": stored_map_instance,
        "materialization_schedule": materialization_schedule,
        "launch_mode": "published_scenario",
        "world_forge_invoked": False,
    }
