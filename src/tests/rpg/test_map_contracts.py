from __future__ import annotations

import pytest

from app.rpg.map_contracts import (
    MapBackground,
    MapBounds,
    MapContractError,
    MapDefinition,
    MapObjectDefinition,
    MapOverlay,
    MapPolygon,
    MapRenderOrder,
    MapRouteGeometry,
    point_in_polygon,
)


def _square() -> MapPolygon:
    return MapPolygon(points=((-10, -10), (10, -10), (10, 10), (-10, 10)))


def _object(object_id: str = "building:inn", *, x: int = 50, y: int = 60) -> MapObjectDefinition:
    return MapObjectDefinition(
        id=object_id,
        kind="building",
        x=x,
        y=y,
        location_id="location:inn",
        render_order=MapRenderOrder(layer="structures", sort_y=y),
        footprint=_square(),
        hitbox=_square(),
    )


def test_polygon_normalizes_winding_and_boundary_is_inside() -> None:
    polygon = _square()

    assert polygon.points == ((-10, 10), (10, 10), (10, -10), (-10, -10))
    assert point_in_polygon((0, 0), polygon) is True
    assert point_in_polygon((10, 0), polygon) is True
    assert point_in_polygon((20, 0), polygon) is False


def test_polygon_rejects_self_intersection() -> None:
    with pytest.raises(MapContractError, match="self_intersecting_polygon"):
        MapPolygon(points=((0, 0), (10, 10), (0, 10), (10, 0)))


def test_definition_rejects_duplicate_and_out_of_bounds_objects() -> None:
    bounds = MapBounds(width=100, height=100)

    with pytest.raises(MapContractError, match="duplicate_map_object_id"):
        MapDefinition(map_id="map:test", level="settlement", bounds=bounds, objects=(_object(), _object()))

    with pytest.raises(MapContractError, match="map_object_out_of_bounds"):
        MapDefinition(map_id="map:test", level="settlement", bounds=bounds, objects=(_object(x=101),))


def test_definition_requires_exact_background_mapping() -> None:
    bounds = MapBounds(width=100, height=100)
    background = MapBackground(asset_id="asset:map", destination_bounds=MapBounds(width=80, height=100))

    with pytest.raises(MapContractError, match="background_bounds_mismatch"):
        MapDefinition(map_id="map:test", level="settlement", bounds=bounds, background=background)


def test_definition_sorts_objects_by_layer_y_offset_and_id() -> None:
    bounds = MapBounds(width=100, height=100)
    high = _object("building:high", y=80)
    low = _object("building:low", y=20)
    route = MapRouteGeometry(route_id="route:test", points=((0, 0), (100, 100)))
    definition = MapDefinition(
        map_id="map:test",
        level="settlement",
        bounds=bounds,
        objects=(high, low),
        route_geometry=(route,),
    )

    assert [item.id for item in definition.sorted_objects()] == ["building:low", "building:high"]


def test_overlay_requires_truthful_current_location_when_ready() -> None:
    with pytest.raises(MapContractError, match="ready_overlay_missing_current_location"):
        MapOverlay(
            map_id="map:test",
            session_id="session:test",
            definition_revision="sha256:test",
            overlay_revision=1,
            session_turn_index=2,
        )


def test_unavailable_overlay_requires_reason_but_not_location() -> None:
    overlay = MapOverlay(
        map_id="map:test",
        session_id="session:test",
        definition_revision="sha256:test",
        overlay_revision=1,
        session_turn_index=2,
        availability="unavailable",
        unavailable_reason="current_location_unavailable",
    )

    assert overlay.current_location_id is None
    assert overlay.availability == "unavailable"
