"""Deterministic RPG map render-budget assessment and renderer decision gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.rpg.map_contracts import MapDefinition, MapOverlay
from app.rpg.map_serialization import canonical_map_bytes

RendererKind = Literal["svg", "pixi"]


@dataclass(frozen=True)
class MapRenderBudget:
    max_definition_bytes: int = 1_500_000
    max_fog_polygons: int = 96
    max_labels: int = 240
    max_markers: int = 320
    max_objects: int = 320
    max_route_points: int = 5_000
    max_routes: int = 180


@dataclass(frozen=True)
class MapRenderMetrics:
    definition_bytes: int
    fog_polygons: int
    labels: int
    markers: int
    objects: int
    route_points: int
    routes: int


@dataclass(frozen=True)
class MapRendererDecision:
    renderer: RendererKind
    within_svg_budget: bool
    reasons: tuple[str, ...]
    metrics: MapRenderMetrics
    budget: MapRenderBudget
    decision_version: int = 1

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_MAP_RENDER_BUDGET = MapRenderBudget()


def assess_map_renderer(
    definition: MapDefinition,
    overlay: MapOverlay | None = None,
    budget: MapRenderBudget = DEFAULT_MAP_RENDER_BUDGET,
) -> MapRendererDecision:
    metrics = MapRenderMetrics(
        definition_bytes=len(canonical_map_bytes(definition)),
        fog_polygons=len(getattr(overlay, "fog_polygons", ()) or ()),
        labels=len(definition.labels),
        markers=len(overlay.markers) if overlay else 0,
        objects=len(definition.objects),
        route_points=sum(len(route.points) for route in definition.route_geometry),
        routes=len(definition.route_geometry),
    )
    reasons = tuple(_budget_reasons(metrics, budget))
    return MapRendererDecision(
        renderer="pixi" if reasons else "svg",
        within_svg_budget=not reasons,
        reasons=reasons,
        metrics=metrics,
        budget=budget,
    )


def _budget_reasons(metrics: MapRenderMetrics, budget: MapRenderBudget) -> list[str]:
    checks = (
        ("definition_bytes", metrics.definition_bytes, budget.max_definition_bytes),
        ("fog_polygons", metrics.fog_polygons, budget.max_fog_polygons),
        ("labels", metrics.labels, budget.max_labels),
        ("markers", metrics.markers, budget.max_markers),
        ("objects", metrics.objects, budget.max_objects),
        ("route_points", metrics.route_points, budget.max_route_points),
        ("routes", metrics.routes, budget.max_routes),
    )
    return [f"{name}_exceeds_svg_budget:{actual}>{limit}" for name, actual, limit in checks if actual > limit]
