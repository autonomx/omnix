"""Safe current-visibility projection for one or more map observers."""
from __future__ import annotations

from typing import Iterable

from .map_grid_contracts import GridMapDefinition, GridPoint
from .map_instance_runtime import CampaignMapInstanceSnapshot
from .map_observer_runtime import (
    ObserverMapKnowledge,
    ObserverPerceptionPolicy,
    observe_map,
    project_observer_knowledge,
)


def _sorted_cells(values: set[GridPoint]) -> tuple[GridPoint, ...]:
    return tuple(sorted(values, key=lambda cell: (cell[1], cell[0])))


def project_current_observers(
    definition: GridMapDefinition,
    snapshot: CampaignMapInstanceSnapshot,
    observer_actor_ids: Iterable[str],
    *,
    policy: ObserverPerceptionPolicy | None = None,
) -> dict[str, object]:
    """Project only cells and entities currently visible to the observer group."""

    observer_ids = tuple(sorted(set(observer_actor_ids)))
    perception = policy or ObserverPerceptionPolicy()
    if not observer_ids:
        empty = ObserverMapKnowledge(
            campaign_id=snapshot.campaign_id,
            map_instance_id=snapshot.map_instance_id,
            observer_actor_id="observer:none",
            policy=perception,
        )
        return project_observer_knowledge(definition, snapshot, empty)

    visible_cells: set[GridPoint] = set()
    detected_actor_ids: set[str] = set()
    known_portal_ids: set[str] = set()
    known_spawn_ids: set[str] = set()
    known_zone_ids: set[str] = set()
    for observer_actor_id in observer_ids:
        knowledge, _ = observe_map(
            definition,
            snapshot,
            observer_actor_id=observer_actor_id,
            policy=perception,
        )
        visible_cells.update(knowledge.visible_cells)
        detected_actor_ids.update(knowledge.detected_actor_ids)
        known_portal_ids.update(knowledge.known_portal_ids)
        known_spawn_ids.update(knowledge.known_spawn_point_ids)
        known_zone_ids.update(knowledge.known_zone_ids)
    group = ObserverMapKnowledge(
        campaign_id=snapshot.campaign_id,
        map_instance_id=snapshot.map_instance_id,
        observer_actor_id="observer-group:" + ",".join(observer_ids),
        knowledge_revision=0,
        observation_sequence=0,
        observed_map_state_revision=snapshot.map_state_revision,
        policy=perception,
        visible_cells=_sorted_cells(visible_cells),
        known_cells=_sorted_cells(visible_cells),
        detected_actor_ids=tuple(sorted(detected_actor_ids)),
        known_portal_ids=tuple(sorted(known_portal_ids)),
        known_spawn_point_ids=tuple(sorted(known_spawn_ids)),
        known_zone_ids=tuple(sorted(known_zone_ids)),
    )
    return project_observer_knowledge(definition, snapshot, group)
