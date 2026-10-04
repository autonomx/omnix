from __future__ import annotations

from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import create_map_instance_snapshot
from app.rpg.npc_spatial_simulation import (
    NpcSpatialGoal,
    NpcSpatialSimulationContext,
    NpcSpatialSimulationPolicy,
    advance_npc_spatial_tick,
)


def _definition() -> GridMapDefinition:
    rows = (
        "########",
        "#......#",
        "#......#",
        "#......#",
        "#......#",
        "#......#",
        "#......#",
        "########",
    )
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="interior:rusty_flagon:ground_floor",
            level="interior",
            definition_revision=1,
            world_id="world:ashen_coast",
            world_revision=1,
            width=8,
            height=8,
            terrain_palette=(
                TerrainRule(
                    code=".",
                    terrain_id="wood_floor",
                    walkable=True,
                    movement_cost=10,
                ),
                TerrainRule(
                    code="#",
                    terrain_id="stone_wall",
                    walkable=False,
                    movement_cost=10,
                    blocks_sight=True,
                ),
            ),
            terrain_rows=rows,
        )
    )


def _snapshot(*actors: GridActorPlacement):
    return create_map_instance_snapshot(
        map_instance_id="campaign:42:map:rusty_flagon:1",
        campaign_id="campaign:42",
        location_id="location:rusty_flagon",
        definition=_definition(),
        actors=actors,
    )


def _goal(
    actor_id: str,
    target_cell: tuple[int, int],
    *,
    goal_id: str | None = None,
    priority: int = 0,
    issued_tick: int = 0,
) -> NpcSpatialGoal:
    return NpcSpatialGoal(
        goal_id=goal_id or f"goal:{actor_id}",
        actor_id=actor_id,
        map_instance_id="campaign:42:map:rusty_flagon:1",
        target_cell=target_cell,
        priority=priority,
        issued_tick=issued_tick,
    )


def test_active_npc_goal_emits_authoritative_replayable_movement() -> None:
    definition = _definition()
    initial = _snapshot(GridActorPlacement(actor_id="npc:xylvanna", cell=(1, 1)))
    result = advance_npc_spatial_tick(
        definition,
        initial,
        (_goal("npc:xylvanna", (5, 1)),),
        world_tick=12,
        context=NpcSpatialSimulationContext(
            active_map_instance_ids=(initial.map_instance_id,)
        ),
    )

    assert result.tier == "active"
    assert len(result.events) == 1
    assert result.events[0].event_type == "actor_moved"
    assert result.events[0].path == ((1, 1), (2, 1), (3, 1), (4, 1), (5, 1))
    assert result.snapshot.actor("npc:xylvanna").cell == (5, 1)
    assert result.decisions[0].status == "moved"
    assert result.decisions[0].command_id == (
        "npc-spatial:campaign:42:map:rusty_flagon:1:12:"
        "npc:xylvanna:goal:npc:xylvanna:r1"
    )
    assert result.replay(initial) == result.snapshot


def test_coarse_map_uses_lower_frequency_cadence() -> None:
    definition = _definition()
    initial = _snapshot(GridActorPlacement(actor_id="npc:bran", cell=(1, 2)))
    context = NpcSpatialSimulationContext(
        coarse_map_instance_ids=(initial.map_instance_id,)
    )
    policy = NpcSpatialSimulationPolicy(coarse_tick_interval=5)

    deferred = advance_npc_spatial_tick(
        definition,
        initial,
        (_goal("npc:bran", (5, 2)),),
        world_tick=3,
        context=context,
        policy=policy,
    )
    advanced = advance_npc_spatial_tick(
        definition,
        initial,
        (_goal("npc:bran", (5, 2)),),
        world_tick=5,
        context=context,
        policy=policy,
    )

    assert deferred.events == ()
    assert deferred.snapshot == initial
    assert deferred.decisions[0].status == "deferred_cadence"
    assert advanced.snapshot.actor("npc:bran").cell == (5, 2)
    assert advanced.decisions[0].status == "moved"


def test_dormant_map_performs_no_mutation_work() -> None:
    definition = _definition()
    initial = _snapshot(GridActorPlacement(actor_id="npc:aldric", cell=(2, 2)))
    result = advance_npc_spatial_tick(
        definition,
        initial,
        (_goal("npc:aldric", (5, 5)),),
        world_tick=20,
        context=NpcSpatialSimulationContext(),
    )

    assert result.tier == "dormant"
    assert result.events == ()
    assert result.snapshot == initial
    assert result.decisions[0].status == "dormant"


def test_goal_selection_and_actor_budget_are_deterministic() -> None:
    definition = _definition()
    initial = _snapshot(
        GridActorPlacement(actor_id="npc:bran", cell=(1, 1)),
        GridActorPlacement(actor_id="npc:xylvanna", cell=(1, 3)),
    )
    result = advance_npc_spatial_tick(
        definition,
        initial,
        (
            _goal(
                "npc:bran",
                (4, 1),
                goal_id="goal:bran:low",
                priority=1,
            ),
            _goal(
                "npc:bran",
                (5, 1),
                goal_id="goal:bran:high",
                priority=10,
            ),
            _goal("npc:xylvanna", (5, 3)),
        ),
        world_tick=21,
        context=NpcSpatialSimulationContext(
            active_map_instance_ids=(initial.map_instance_id,)
        ),
        policy=NpcSpatialSimulationPolicy(active_actor_budget=1),
    )

    assert [decision.actor_id for decision in result.decisions] == [
        "npc:bran",
        "npc:xylvanna",
    ]
    assert result.decisions[0].goal_id == "goal:bran:high"
    assert result.decisions[0].status == "moved"
    assert result.decisions[1].status == "deferred_budget"
    assert result.snapshot.actor("npc:bran").cell == (5, 1)
    assert result.snapshot.actor("npc:xylvanna").cell == (1, 3)


def test_blocked_goal_is_reported_without_corrupting_snapshot() -> None:
    definition = _definition()
    initial = _snapshot(
        GridActorPlacement(actor_id="npc:bran", cell=(1, 1)),
        GridActorPlacement(actor_id="npc:xylvanna", cell=(5, 1)),
    )
    result = advance_npc_spatial_tick(
        definition,
        initial,
        (_goal("npc:bran", (5, 1)),),
        world_tick=22,
        context=NpcSpatialSimulationContext(
            active_map_instance_ids=(initial.map_instance_id,)
        ),
    )

    assert result.events == ()
    assert result.snapshot == initial
    assert result.decisions[0].status == "blocked"
    assert result.decisions[0].error_code == "destination_occupied"
