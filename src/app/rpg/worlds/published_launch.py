"""Fast deterministic campaign launch from certified world releases."""
from __future__ import annotations

from typing import Any, Mapping

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session
from app.rpg.session.service import archive_session, save_session

from .lifecycle_service import require_scenario_writable
from .postgres_service import load_published_resources, load_release_definitions
from .progressive_materialization_job_service import (
    schedule_campaign_predictive_materialization,
)
from .semantic_validation import (
    initialize_starting_map_snapshot,
    validate_scenario_against_release,
)
from .service import resolve_campaign_binding


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def launch_published_scenario(
    *,
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

    context = bootstrap_local_tenant(database)
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
    request = RpgNewGameRequest.model_validate(
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
    created = create_new_game_session(request)
    session_id = str(created.get("session_id") or "")
    session = created.get("session") if isinstance(created.get("session"), dict) else None
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
    saved = save_session(session, compact=True)

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
                    },
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
        archive_session(session_id)
        raise

    try:
        materialization_schedule = schedule_campaign_predictive_materialization(
            session_id,
            current_location_id=scenario.starting_location_id,
            database=database,
            kick_worker=True,
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
