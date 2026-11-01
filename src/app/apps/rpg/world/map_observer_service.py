"""Transactional observer knowledge and safe map projection services."""
from __future__ import annotations

from typing import Any

from app.security.tenant_context import current_tenant
from app.persistence.unit_of_work import unit_of_work

from app.apps.rpg.world.map_grid_contracts import GridMapDefinition
from app.apps.rpg.world.map_instance_runtime import CampaignMapInstanceSnapshot
from app.apps.rpg.world.tactical_spatial import foes_on_grid, grid_turn_summary
from app.apps.rpg.world.map_observer_runtime import (
    ObserverMapKnowledge,
    ObserverPerceptionPolicy,
    observe_map,
    project_observer_knowledge,
)


def _knowledge_model(row: dict[str, Any]) -> ObserverMapKnowledge:
    return ObserverMapKnowledge.model_validate(
        {
            "campaign_id": row["campaign_id"],
            "map_instance_id": row["map_instance_id"],
            "observer_actor_id": row["observer_actor_id"],
            "knowledge_revision": row["knowledge_revision"],
            "observation_sequence": row["observation_sequence"],
            "observed_map_state_revision": row["observed_map_state_revision"],
            "policy": row["policy"],
            "visible_cells": row["visible_cells"],
            "known_cells": row["known_cells"],
            "detected_actor_ids": row["detected_actor_ids"],
            "known_portal_ids": row["known_portal_ids"],
            "known_spawn_point_ids": row["known_spawn_point_ids"],
            "known_zone_ids": row["known_zone_ids"],
        }
    )


def _load_map(
    work: Any,
    context: Any,
    map_instance_id: str,
    *,
    for_update: bool = False,
) -> tuple[CampaignMapInstanceSnapshot, GridMapDefinition]:
    instance = work.map_instances.get_instance(
        context,
        map_instance_id,
        for_update=for_update,
    )
    if instance is None:
        raise KeyError(f"map_instance_not_found:{map_instance_id}")
    definition_row = work.map_instances.get_definition(
        context,
        str(instance["map_id"]),
        int(instance["definition_revision"]),
    )
    if definition_row is None:
        raise KeyError(
            f"map_definition_not_found:{instance['map_id']}:"
            f"{instance['definition_revision']}"
        )
    return (
        CampaignMapInstanceSnapshot.model_validate(instance["snapshot"]),
        GridMapDefinition.model_validate(definition_row["document"]),
    )


def _campaign_turn(work: Any, context: Any, campaign_id: str, observer_actor_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The campaign revision a tactical command must name and the observer's tactical turn (read-only), and the
    campaign's fight as it stands."""
    campaign = work.rpg.get_campaign(context, campaign_id)
    if campaign is None:
        return {"campaign_revision": None, "tactical": {"combat_active": False}}, {}
    simulation = dict(dict(campaign.get("state") or {}).get("simulation_state") or {})
    combat = simulation.get("combat_state") if isinstance(simulation.get("combat_state"), dict) else {}
    return {
        "campaign_revision": int(campaign["revision"]),
        "tactical": grid_turn_summary(simulation, campaign_id, observer_actor_id),
    }, combat


def _with_foes(projection: dict[str, Any], snapshot: CampaignMapInstanceSnapshot, combat: dict[str, Any]) -> dict[str, Any]:
    """The projection with the fight's foes standing in a square the observer sees (the fight keeps where they stand,
    not the map)."""
    visible = {tuple(cell) for cell in projection.get("visible_cells") or ()}
    shown = {str(actor.get("actor_id")) for actor in projection.get("actors") or ()}
    on_map = {actor.actor_id for actor in snapshot.actors}
    foes = [actor.model_dump(mode="json") for actor in foes_on_grid(snapshot, combat).actors
            if actor.actor_id not in on_map and actor.actor_id not in shown and actor.cell in visible]
    return {**projection, "actors": [*(projection.get("actors") or ()), *foes]} if foes else projection


def observe_campaign_map(
    map_instance_id: str,
    *,
    observer_actor_id: str,
    policy: ObserverPerceptionPolicy | None = None,
    expected_knowledge_revision: int | None = None,
    database: Any | None = None,
) -> dict[str, Any]:
    context = current_tenant()
    with unit_of_work(database) as work:
        snapshot, definition = _load_map(
            work,
            context,
            map_instance_id,
            for_update=True,
        )
        turn, combat = _campaign_turn(work, context, snapshot.campaign_id, observer_actor_id)
        previous_row = work.observers.get_knowledge(
            context,
            campaign_id=snapshot.campaign_id,
            map_instance_id=map_instance_id,
            observer_actor_id=observer_actor_id,
            for_update=True,
        )
        previous = _knowledge_model(previous_row) if previous_row is not None else None
        expected = previous.knowledge_revision if previous is not None else 0
        if expected_knowledge_revision is not None and int(
            expected_knowledge_revision
        ) != expected:
            raise ValueError(
                "observer_knowledge_revision_conflict:"
                f"{map_instance_id}:{observer_actor_id}:"
                f"{expected_knowledge_revision}:{expected}"
            )
        perception = policy or (
            previous.policy if previous is not None else ObserverPerceptionPolicy()
        )
        if (
            previous is not None
            and previous.observed_map_state_revision == snapshot.map_state_revision
            and previous.policy == perception
        ):
            work.rollback()
            return {
                "ok": True,
                **turn,
                "status": "current",
                "reused": True,
                "knowledge": previous.model_dump(mode="json"),
                "projection": _with_foes(project_observer_knowledge(
                    definition,
                    snapshot,
                    previous,
                ), snapshot, combat),
                "event": None,
            }
        knowledge, event = observe_map(
            definition,
            snapshot,
            observer_actor_id=observer_actor_id,
            previous=previous,
            policy=perception,
        )
        stored = work.observers.put_observation(
            context,
            knowledge=knowledge,
            event=event,
            expected_knowledge_revision=expected,
        )
        work.commit()
    stored_knowledge = _knowledge_model(stored)
    return {
        "ok": True,
        **turn,
        "status": "observed",
        "reused": False,
        "knowledge": stored_knowledge.model_dump(mode="json"),
        "projection": _with_foes(project_observer_knowledge(
            definition,
            snapshot,
            stored_knowledge,
        ), snapshot, combat),
        "event": event.model_dump(mode="json"),
    }


def load_campaign_observer_projection(
    map_instance_id: str,
    *,
    observer_actor_id: str,
    database: Any | None = None,
) -> dict[str, Any]:
    context = current_tenant()
    with unit_of_work(database) as work:
        snapshot, definition = _load_map(work, context, map_instance_id)
        turn, combat = _campaign_turn(work, context, snapshot.campaign_id, observer_actor_id)
        row = work.observers.get_knowledge(
            context,
            campaign_id=snapshot.campaign_id,
            map_instance_id=map_instance_id,
            observer_actor_id=observer_actor_id,
        )
        events = work.observers.list_events(
            context,
            campaign_id=snapshot.campaign_id,
            map_instance_id=map_instance_id,
            observer_actor_id=observer_actor_id,
            limit=20,
        )
        work.rollback()
    if row is None:
        raise KeyError(
            f"observer_knowledge_not_found:{map_instance_id}:{observer_actor_id}"
        )
    knowledge = _knowledge_model(row)
    return {
        "ok": True,
        **turn,
        "stale": knowledge.observed_map_state_revision != snapshot.map_state_revision,
        "knowledge": knowledge.model_dump(mode="json"),
        "projection": _with_foes(project_observer_knowledge(definition, snapshot, knowledge), snapshot, combat),
        "recent_events": events,
    }
