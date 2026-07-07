from __future__ import annotations

from dataclasses import replace

from app.rpg.map_contracts import (
    MapBounds,
    MapDefinition,
    MapObjectDefinition,
    MapOverlay,
    MapPolygon,
    MapRenderOrder,
)
from app.rpg.map_serialization import (
    canonical_map_json,
    definition_revision,
    overlay_content_revision,
    resource_envelope_payload,
    with_definition_revision,
)


def _definition() -> MapDefinition:
    polygon = MapPolygon(points=((-10, -10), (10, -10), (10, 10), (-10, 10)))
    return MapDefinition(
        map_id="map:test",
        level="settlement",
        bounds=MapBounds(width=100, height=100),
        objects=(
            MapObjectDefinition(
                id="building:inn",
                kind="building",
                x=50,
                y=60,
                location_id="location:inn",
                render_order=MapRenderOrder(layer="structures", sort_y=60),
                footprint=polygon,
                hitbox=polygon,
            ),
        ),
    )


def _overlay(revision: str) -> MapOverlay:
    return MapOverlay(
        map_id="map:test",
        session_id="session:test",
        definition_revision=revision,
        overlay_revision=3,
        session_turn_index=7,
        current_location_id="location:inn",
        discovered_object_ids=("building:inn",),
        visible_object_ids=("building:inn",),
        environment={"weather": "clear", "season": "spring"},
    )


def test_definition_revision_is_stable_and_ignores_revision_field() -> None:
    definition = _definition()
    first = definition_revision(definition)
    second = definition_revision(replace(definition, definition_revision="sha256:ignored"))

    assert first == second
    assert first.startswith("sha256:")


def test_canonical_json_is_stable_for_mapping_order() -> None:
    left = canonical_map_json({"b": 2, "a": {"z": 1, "y": 2}})
    right = canonical_map_json({"a": {"y": 2, "z": 1}, "b": 2})

    assert left == right == '{"a":{"y":2,"z":1},"b":2}'


def test_envelope_omits_definition_when_revision_is_known() -> None:
    definition = with_definition_revision(_definition())
    overlay = _overlay(definition.definition_revision)

    cold = resource_envelope_payload(definition, overlay)
    warm = resource_envelope_payload(
        definition,
        overlay,
        known_definition_revision=definition.definition_revision,
    )

    assert cold["definition"] is not None
    assert warm["definition"] is None
    assert warm["definition_revision"] == definition.definition_revision
    assert warm["overlay_revision"] == 3
    assert warm["session_turn_index"] == 7


def test_overlay_content_revision_changes_with_authoritative_turn() -> None:
    definition = with_definition_revision(_definition())
    overlay = _overlay(definition.definition_revision)

    assert overlay_content_revision(overlay) != overlay_content_revision(
        replace(overlay, session_turn_index=8, overlay_revision=4)
    )
