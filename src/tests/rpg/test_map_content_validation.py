from __future__ import annotations

import json

from app.rpg.map_content_validation import validate_map_content
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_repository import default_map_repository
from app.rpg.map_serialization import canonical_map_json


def _definition() -> dict[str, object]:
    return json.loads(canonical_map_json(default_map_repository().get(FROST_HAVEN_MAP_ID)))


def test_fixture_validation_is_stable() -> None:
    definition = _definition()

    first = validate_map_content(definition)
    second = validate_map_content(json.loads(json.dumps(definition)))

    assert first.ok is True
    assert first.revision == second.revision
    assert first.canonical_json == second.canonical_json
    assert first.revision.startswith("sha256:")


def test_context_rejects_unknown_references() -> None:
    report = validate_map_content(
        _definition(),
        canonical_route_ids=["route:not-used"],
        known_map_ids=[FROST_HAVEN_MAP_ID],
        allowed_asset_ids=["asset:not-used"],
    )

    codes = {issue.code for issue in report.issues}
    assert report.ok is False
    assert "unknown_canonical_route_id" in codes
    assert "unknown_parent_map_id" in codes
    assert "asset_id_not_allowed" in codes


def test_shape_errors_include_paths() -> None:
    definition = _definition()
    definition["objects"][0]["hitbox"] = {"kind": "polygon", "points": [[0, 0], [1, 1]]}
    definition["route_geometry"][0]["points"] = [[0, "bad"]]

    report = validate_map_content(definition)

    assert report.ok is False
    assert any(issue.code == "degenerate_polygon" and ".hitbox.points" in issue.path for issue in report.issues)
    assert any(issue.code == "point_requires_integer_coordinates" for issue in report.issues)
    assert any(issue.code == "route_geometry_too_short" for issue in report.issues)
