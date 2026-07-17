"""Transactional services for authoritative campaign map instances."""
from __future__ import annotations

from typing import Any, Iterable

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .map_grid_contracts import GridActorPlacement, GridMapDefinition
from .map_instance_runtime import (
    ActorMovedEvent,
    CampaignMapInstanceSnapshot,
    MoveActorCommand,
    create_map_instance_snapshot,
    project_observer_map,
    resolve_move_command,
)


def persist_grid_definition(
    definition: GridMapDefinition,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        stored = work.map_instances.put_definition(
            context,
            map_id=definition.map_id,
            definition_revision=definition.definition_revision,
            world_id=definition.world_id,
            world_revision=definition.world_revision,
            document=definition.model_dump(mode="json"),
            definition_hash=definition.definition_hash,
            semantic_interface_hash=definition.semantic_interface_hash,
        )
        work.commit()
    return stored


def create_campaign_map_instance(
    *,
    map_instance_id: str,
    campaign_id: str,
    location_id: str,
    definition: GridMapDefinition,
    actors: Iterable[GridActorPlacement] = (),
    database: Any | None = None,
) -> CampaignMapInstanceSnapshot:
    snapshot = create_map_instance_snapshot(
        map_instance_id=map_instance_id,
        campaign_id=campaign_id,
        location_id=location_id,
        definition=definition,
        actors=actors,
    )
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        work.map_instances.create_instance(
            context,
            map_instance_id=map_instance_id,
            campaign_id=campaign_id,
            location_id=location_id,
            map_id=definition.map_id,
            definition_revision=definition.definition_revision,
            definition_hash=definition.definition_hash,
            snapshot=snapshot.model_dump(mode="json"),
        )
        work.commit()
    return snapshot


def move_actor_on_map(
    map_instance_id: str,
    command: MoveActorCommand,
    *,
    database: Any | None = None,
) -> tuple[ActorMovedEvent, CampaignMapInstanceSnapshot]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        stored_instance = work.map_instances.get_instance(
            context, map_instance_id, for_update=True
        )
        if stored_instance is None:
            raise KeyError(f"map_instance_not_found:{map_instance_id}")
        stored_definition = work.map_instances.get_definition(
            context,
            stored_instance["map_id"],
            stored_instance["definition_revision"],
        )
        if stored_definition is None:
            raise KeyError(
                "map_definition_not_found:"
                f"{stored_instance['map_id']}:{stored_instance['definition_revision']}"
            )
        definition = GridMapDefinition.model_validate(stored_definition["document"])
        snapshot = CampaignMapInstanceSnapshot.model_validate(
            stored_instance["snapshot"]
        )
        event, updated = resolve_move_command(definition, snapshot, command)
        work.map_instances.append_event(
            context,
            map_instance_id=map_instance_id,
            command_id=event.command_id,
            event_id=event.event_id,
            event_type=event.event_type,
            event_sequence=event.event_sequence,
            revision_before=event.map_state_revision_before,
            revision_after=event.map_state_revision_after,
            event=event.model_dump(mode="json"),
            snapshot=updated.model_dump(mode="json"),
        )
        work.commit()
    return event, updated


def load_map_instance_projection(
    map_instance_id: str,
    *,
    observer_actor_id: str,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        stored_instance = work.map_instances.get_instance(context, map_instance_id)
        if stored_instance is None:
            raise KeyError(f"map_instance_not_found:{map_instance_id}")
        stored_definition = work.map_instances.get_definition(
            context,
            stored_instance["map_id"],
            stored_instance["definition_revision"],
        )
        work.rollback()
    if stored_definition is None:
        raise KeyError("map_definition_not_found")
    definition = GridMapDefinition.model_validate(stored_definition["document"])
    snapshot = CampaignMapInstanceSnapshot.model_validate(stored_instance["snapshot"])
    return project_observer_map(
        definition,
        snapshot,
        observer_actor_id=observer_actor_id,
    )
