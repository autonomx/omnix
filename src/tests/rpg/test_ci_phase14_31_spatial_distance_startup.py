from __future__ import annotations

from types import SimpleNamespace


def test_spatial_package_exports_euclidean_distance() -> None:
    from app.rpg.spatial import euclidean_distance

    assert euclidean_distance({"x": 0, "y": 0}, {"x": 3, "y": 4}) == 5.0
    assert euclidean_distance((0, 0), (6, 8)) == 10.0
    assert euclidean_distance(SimpleNamespace(x=1, y=1), SimpleNamespace(x=4, y=5)) == 5.0


def test_goap_state_builder_imports_without_spatial_error() -> None:
    from app.rpg.ai.goap import state_builder

    assert callable(state_builder.euclidean_distance)
    assert state_builder.euclidean_distance({"x": 2, "y": 2}, {"x": 2, "y": 2}) == 0.0
