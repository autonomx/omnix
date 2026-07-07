from __future__ import annotations

from dataclasses import replace

from app.rpg.map_contracts import (
    MapBounds,
    MapDefinition,
    MapMarker,
    MapObjectDefinition,
    MapOverlay,
    MapPolygon,
    MapRenderOrder,
)
from app.rpg.map_overlay_projection import MapDynamicOverlay, MapFogPolygon
from app.rpg.map_performance import MapRenderBudget, assess_map_renderer
from app.rpg.map_repository import default_map_repository


def test_default_curated_maps_remain_within_svg_budget() -> None:
    for definition in default_map_repository().list():
        decision = assess_map_renderer(definition)

        assert decision.renderer == "svg"
        assert decision.within_svg_budget is True
        assert decision.reasons == ()
        assert decision.metrics.objects == len(definition.objects)


def test_object_marker_and_fog_thresholds_trigger_explicit_pixi_reasons() -> None:
    definition = default_map_repository().get("settlement:frost_haven")
    overlay = MapOverlay(
        map_id=definition.map_id,
        session_id="session:test",
        definition_revision=definition.definition_revision,
        overlay_revision=1,
        session_turn_index=1,
        current_location_id="rusty_flagon_tavern",
        markers=tuple(MapMarker(f"marker:{index}", "event", index, index) for index in range(4)),
    )
    dynamic = MapDynamicOverlay(
        fog_polygons=tuple(
            MapFogPolygon(f"fog:{index}", ((0, 0), (10, 0), (10, 10), (0, 10)))
            for index in range(3)
        )
    )
    decision = assess_map_renderer(
        definition,
        overlay,
        dynamic,
        budget=MapRenderBudget(max_objects=5, max_markers=2, max_fog_polygons=1),
    )

    assert decision.renderer == "pixi"
    assert decision.within_svg_budget is False
    assert "objects_exceeds_svg_budget:12>5" in decision.reasons
    assert "markers_exceeds_svg_budget:4>2" in decision.reasons
    assert "fog_polygons_exceeds_svg_budget:3>1" in decision.reasons


def test_definition_size_budget_is_measured_from_canonical_bytes() -> None:
    polygon = MapPolygon(points=((-10, -10), (10, -10), (10, 10), (-10, 10)))
    base = MapObjectDefinition(
        id="object:0",
        kind="building",
        x=50,
        y=50,
        render_order=MapRenderOrder(layer="structures", sort_y=50),
        hitbox=polygon,
    )
    definition = MapDefinition(
        map_id="map:large-contract",
        level="settlement",
        bounds=MapBounds(width=100, height=100),
        objects=(replace(base, description="x" * 6000),),
    )

    decision = assess_map_renderer(definition, budget=MapRenderBudget(max_definition_bytes=1000))

    assert decision.renderer == "pixi"
    assert decision.metrics.definition_bytes > 1000
    assert decision.reasons[0].startswith("definition_bytes_exceeds_svg_budget:")


def test_renderer_decision_payload_is_deterministic() -> None:
    definition = default_map_repository().get("region:northern_pass")

    assert assess_map_renderer(definition).as_dict() == assess_map_renderer(definition).as_dict()
