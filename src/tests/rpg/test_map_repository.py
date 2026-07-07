from __future__ import annotations

import pytest

from app.rpg.map_contracts import MapContractError, MapDefinition
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID, NORTHERN_PASS_MAP_ID, starter_map_definitions
from app.rpg.map_repository import MapDefinitionNotFound, MapDefinitionRepository, default_map_repository


def test_starter_repository_contains_region_and_settlement() -> None:
    repository = default_map_repository()

    assert [item.map_id for item in repository.list()] == [
        NORTHERN_PASS_MAP_ID,
        FROST_HAVEN_MAP_ID,
    ]
    assert repository.get(FROST_HAVEN_MAP_ID).parent_map_id == NORTHERN_PASS_MAP_ID


def test_starter_settlement_is_revisioned_and_has_vertical_slice_content() -> None:
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)

    assert definition.definition_revision.startswith("sha256:")
    assert len(definition.objects) == 12
    assert len(definition.route_geometry) == 4
    assert definition.background.asset_id == "asset:rpg-map:frost-haven-base"
    assert definition.objects[0].location_id == "rusty_flagon_tavern"
    assert all(item.hitbox is not None for item in definition.objects)
    assert all(item.footprint is not None for item in definition.objects)


def test_region_routes_reference_stable_canonical_ids() -> None:
    definition = default_map_repository().get(NORTHERN_PASS_MAP_ID)

    assert [route.route_id for route in definition.route_geometry] == [
        "route:northern_pass:frostpine_frost_haven",
        "route:northern_pass:frost_haven_glimmerdeep",
        "route:northern_pass:frost_haven_quarry",
        "route:northern_pass:glimmerdeep_watch",
    ]


def test_repository_rejects_conflicting_definition_for_same_id() -> None:
    first = starter_map_definitions()[0]
    repository = MapDefinitionRepository((first,))
    conflicting = MapDefinition(
        map_id=first.map_id,
        level=first.level,
        bounds=first.bounds,
        seed=first.seed + 1,
    )

    with pytest.raises(MapContractError, match="map_definition_id_collision"):
        repository.register(conflicting)


def test_repository_raises_typed_not_found() -> None:
    with pytest.raises(MapDefinitionNotFound) as error:
        default_map_repository().get("map:missing")

    assert error.value.map_id == "map:missing"


def test_starter_definition_revisions_are_stable_across_repositories() -> None:
    left = MapDefinitionRepository(starter_map_definitions()).revisions()
    right = MapDefinitionRepository(starter_map_definitions()).revisions()

    assert left == right
